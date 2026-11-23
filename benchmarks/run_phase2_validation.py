"""Phase 2 3-Pillar Validation Benchmark: Copernicus DEM, NREL PVDAQ #2107, and ModelChain."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pvlib
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.pvsystem import PVSystem

from heliostack.ess_optimizer import run_full_simulation
from heliostack.formats import parse_ond, parse_pan
from heliostack.models import SiteConfig
from heliostack.pv_engine import derive_pvsyst_single_diode_params
from heliostack.telemetry import evaluate_field_validation, fetch_and_prepare_pvdaq_2107_2024
from heliostack.terrain import (
    compare_horizon_profiles,
    fetch_copernicus_dem_horizon,
    fetch_pvgis_horizon,
)
from heliostack.weather import fetch_pvgis_pvcalc, fetch_pvgis_tmy

ROOT = Path(__file__).resolve().parent.parent
WEATHER_DIR = ROOT / "fixtures" / "weather"
TELEMETRY_CSV = ROOT / "fixtures" / "telemetry" / "pvdaq_2107_2024_hourly.csv"
RAW_OEDI_CACHE = ROOT / "outputs" / "oedi_cache"
RESULTS_PATH = ROOT / "results" / "phase2_validation_v02.json"

ALPINE_SITES = [
    {"id": "innsbruck", "name": "Innsbruck, Austria (Alps)", "lat": 47.2692, "lon": 11.4041, "tilt": 35.0},
    {"id": "bolzano", "name": "Bolzano, Italy (Dolomites)", "lat": 46.4983, "lon": 11.3548, "tilt": 34.0},
    {"id": "zermatt", "name": "Zermatt, Switzerland (Matterhorn Valley)", "lat": 46.0207, "lon": 7.7491, "tilt": 35.0},
]


def _run_alpine_terrain_pillar(mod, inv) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for meta in ALPINE_SITES:
        # Use horizon-free PVGIS TMY (usehorizon=0) so flat vs terrain horizon avoids double-counting
        weather, prov = fetch_pvgis_tmy(
            meta["lat"], meta["lon"], cache_dir=WEATHER_DIR, use_horizon=False
        )
        elev = float(prov.get("elevation_m") or 400.0)
        h_cop, meta_cop = fetch_copernicus_dem_horizon(meta["lat"], meta["lon"], cache_dir=WEATHER_DIR)
        h_pvgis, meta_pvgis = fetch_pvgis_horizon(meta["lat"], meta["lon"], cache_dir=WEATHER_DIR)
        hor_cmp = compare_horizon_profiles(h_cop, h_pvgis)

        pvcalc_flat = fetch_pvgis_pvcalc(
            meta["lat"], meta["lon"], 100.0, 14.0, meta["tilt"], 180.0,
            cache_dir=WEATHER_DIR, use_horizon=False,
        )
        pvcalc_hor = fetch_pvgis_pvcalc(
            meta["lat"], meta["lon"], 100.0, 14.0, meta["tilt"], 180.0,
            cache_dir=WEATHER_DIR, use_horizon=True,
        )
        pvcalc_loss_pct = (
            (pvcalc_hor["specific_yield_kwh_kwp"] - pvcalc_flat["specific_yield_kwh_kwp"])
            / pvcalc_flat["specific_yield_kwh_kwp"]
            * 100.0
        )

        base_cfg = SiteConfig(
            site_name=meta["name"],
            latitude=meta["lat"],
            longitude=meta["lon"],
            elevation_m=elev,
            surface_tilt_deg=meta["tilt"],
            surface_azimuth_deg=180.0,
            dc_kwp=100.0,
            gcr=0.40,
            use_3d_shading=True,
            mounting_mode="open_rack",
            grid_export_limit_kw=100.0,
        )
        res_flat = run_full_simulation(weather, prov, base_cfg, mod, inv)
        res_cop = run_full_simulation(weather, prov, replace(base_cfg, horizon_elev_deg_36=h_cop), mod, inv)
        res_pvg = run_full_simulation(weather, prov, replace(base_cfg, horizon_elev_deg_36=h_pvgis), mod, inv)

        y_flat = res_flat.loss_waterfall.specific_yield_kwh_kwp
        y_cop = res_cop.loss_waterfall.specific_yield_kwh_kwp
        y_pvg = res_pvg.loss_waterfall.specific_yield_kwh_kwp
        mountain_loss_pct = (y_cop - y_flat) / y_flat * 100.0
        cop_vs_pvgis_yield_pct = (y_cop - y_pvg) / y_pvg * 100.0

        rows.append(
            {
                "id": meta["id"],
                "name": meta["name"],
                "latitude": meta["lat"],
                "longitude": meta["lon"],
                "elevation_m": elev,
                "horizon_comparison": hor_cmp,
                "copernicus_horizon_deg_36": h_cop,
                "pvgis_horizon_deg_36": h_pvgis,
                "flat_yield_kwh_kwp": y_flat,
                "copernicus_yield_kwh_kwp": y_cop,
                "pvgis_horizon_yield_kwh_kwp": y_pvg,
                "mountain_shading_loss_pct": round(mountain_loss_pct, 2),
                "copernicus_vs_pvgis_yield_delta_pct": round(cop_vs_pvgis_yield_pct, 2),
                "pvgis_pvcalc_flat_yield_kwh_kwp": round(pvcalc_flat["specific_yield_kwh_kwp"], 1),
                "pvgis_pvcalc_horizon_yield_kwh_kwp": round(pvcalc_hor["specific_yield_kwh_kwp"], 1),
                "pvgis_pvcalc_mountain_loss_pct": round(pvcalc_loss_pct, 2),
                "copernicus_monthly_ac_kwh": [round(v, 1) for v in res_cop.monthly_ac_kwh],
                "flat_monthly_ac_kwh": [round(v, 1) for v in res_flat.monthly_ac_kwh],
            }
        )
        print(
            f"[Alpine {meta['id']}] MAE={hor_cmp['mae_deg']:.2f} deg | Flat={y_flat:.1f} vs "
            f"Copernicus={y_cop:.1f} ({mountain_loss_pct:+.2f}%) vs PVGIS-Hor={y_pvg:.1f} "
            f"(yield delta {cop_vs_pvgis_yield_pct:+.2f}% | EU PVcalc terrain {pvcalc_loss_pct:+.2f}%)"
        )
    return rows


def _run_modelchain_parity_pillar(mod_mono, inv) -> list[dict[str, Any]]:
    """Compare HelioStack directly against canonical pvlib ModelChain on identical 99 kWp string plant."""
    i_l_ref, i_o_ref = derive_pvsyst_single_diode_params(mod_mono)
    # Standardize stc single-diode calibration
    il_s, io_s, rs_s, rsh_s, nns_s = pvlib.pvsystem.calcparams_pvsyst(
        1000.0, 25.0, mod_mono.alpha_sc_a_per_c, mod_mono.gamma_ref, mod_mono.mu_gamma,
        i_l_ref, i_o_ref, mod_mono.r_sh_ref_ohm, mod_mono.r_sh_0_ohm, mod_mono.r_s_ohm,
        mod_mono.cells_in_series, mod_mono.r_sh_exp, mod_mono.eg_ref_ev,
    )
    _ = pvlib.pvsystem.singlediode(il_s, io_s, rs_s, rsh_s, nns_s)

    n_series, n_strings = 18, 10  # 180 * 550 W = 99.0 kWp
    dc_kwp = n_series * n_strings * mod_mono.p_nom_w / 1000.0
    mod_params = {
        "alpha_sc": mod_mono.alpha_sc_a_per_c,
        "gamma_ref": mod_mono.gamma_ref,
        "mu_gamma": mod_mono.mu_gamma,
        "I_L_ref": i_l_ref,
        "I_o_ref": i_o_ref,
        "R_sh_ref": mod_mono.r_sh_ref_ohm,
        "R_sh_0": mod_mono.r_sh_0_ohm,
        "R_s": mod_mono.r_s_ohm,
        "cells_in_series": mod_mono.cells_in_series,
        "R_sh_exp": mod_mono.r_sh_exp,
        "EgRef": mod_mono.eg_ref_ev,
        "irrad_ref": 1000.0,
        "temp_ref": 25.0,
        "a_r": 0.16,
    }
    inv_params = {"pdc0": dc_kwp * 1000.0 / 0.988, "eta_inv_nom": 0.988, "eta_inv_ref": 0.988}
    loss_params = {
        "soiling": 2.0, "shading": 0.0, "snow": 0.0, "mismatch": 1.5,
        "wiring": 1.5, "connections": 0.0, "lid": 0.0, "nameplate_rating": 0.0, "availability": 1.0,
    }

    checks = []
    for meta in [
        {"id": "amsterdam", "name": "Amsterdam, NL", "lat": 52.37, "lon": 4.90, "tilt": 35.0},
        {"id": "seville", "name": "Seville, ES", "lat": 37.39, "lon": -5.98, "tilt": 32.0},
    ]:
        weather, prov = fetch_pvgis_tmy(meta["lat"], meta["lon"], cache_dir=WEATHER_DIR)
        elev = float(prov.get("elevation_m") or 10.0)

        cfg = SiteConfig(
            site_name=meta["name"], latitude=meta["lat"], longitude=meta["lon"], elevation_m=elev,
            surface_tilt_deg=meta["tilt"], surface_azimuth_deg=180.0, dc_kwp=dc_kwp,
            gcr=0.05, use_3d_shading=False, soiling_loss_frac=0.02, dc_wiring_loss_frac=0.015,
            mismatch_loss_frac=0.015, availability_frac=0.99, mounting_mode="open_rack", grid_export_limit_kw=dc_kwp,
        )
        res_hs = run_full_simulation(weather, prov, cfg, mod_mono, inv)

        system = PVSystem(
            surface_tilt=meta["tilt"], surface_azimuth=180.0, albedo=0.20,
            module_parameters=mod_params, temperature_model_parameters={"u0": 25.0, "u1": 6.84},
            modules_per_string=n_series, strings_per_inverter=n_strings,
            inverter_parameters=inv_params, losses_parameters=loss_params,
        )
        loc = Location(meta["lat"], meta["lon"], altitude=elev, tz="UTC")
        mc = ModelChain(
            system, loc, transposition_model="perez", dc_model="pvsyst",
            ac_model="pvwatts", aoi_model="martin_ruiz", spectral_model="no_loss",
            temperature_model="faiman", losses_model="pvwatts",
        )
        mc_in = weather[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].copy()
        mc.run_model(mc_in)
        mc_ac_kwh = float(np.maximum(0.0, mc.results.ac.fillna(0.0).to_numpy()).sum() / 1000.0)
        mc_yield = mc_ac_kwh / dc_kwp
        hs_yield = res_hs.loss_waterfall.specific_yield_kwh_kwp
        delta = (hs_yield - mc_yield) / mc_yield * 100.0

        # Canonical 12-step PVsyst loss tree summary
        wf = res_hs.loss_waterfall
        loss_tree = [
            {"step": "1. Horizontal Global (GHI)", "value": f"{wf.ghi_kwh_m2:.1f} kWh/m2"},
            {"step": "2. Transposition to Collector Plane (Perez)", "value": f"{wf.transposition_gain_pct:+.2f}%"},
            {"step": "3. Near & Horizon Shading + SVF", "value": f"-{wf.shading_loss_pct:.2f}%"},
            {"step": "4. Incidence Angle Modifier (IAM Martin-Ruiz)", "value": f"-{wf.iam_loss_pct:.2f}%"},
            {"step": "5. Soiling Loss", "value": f"-{wf.soiling_loss_pct:.2f}%"},
            {"step": "6. Bifacial Rear Irradiance Gain", "value": f"+{wf.bifacial_gain_pct:.2f}%"},
            {"step": "7. Thermal Loss (Cell Temperature Model)", "value": f"-{wf.thermal_loss_pct:.2f}%"},
            {"step": "8. DC Wiring + Mismatch + Availability", "value": f"-{wf.mismatch_wiring_loss_pct:.2f}%"},
            {"step": "9. Inverter Efficiency Curve (.OND)", "value": f"-{wf.inverter_eff_loss_pct:.2f}%"},
            {"step": "10. Inverter AC Overpower Clipping", "value": f"-{wf.clipping_loss_pct:.2f}%"},
            {"step": "11. Net Annual Specific Yield (P50)", "value": f"{wf.specific_yield_kwh_kwp:.1f} kWh/kWp/yr"},
            {"step": "12. P90 Bankable Exceedance (4.4% sigma)", "value": f"{wf.p90_kwh_yr/dc_kwp:.1f} kWh/kWp/yr"},
        ]
        checks.append(
            {
                "id": meta["id"],
                "name": meta["name"],
                "dc_kwp": round(dc_kwp, 2),
                "pvlib_modelchain_yield_kwh_kwp": round(mc_yield, 2),
                "heliostack_yield_kwh_kwp": round(hs_yield, 2),
                "modelchain_delta_pct": round(delta, 2),
                "loss_tree_12_steps": loss_tree,
            }
        )
        print(f"[ModelChain {meta['id']}] pvlib={mc_yield:.1f} vs HS={hs_yield:.1f} kWh/kWp ({delta:+.2f}%)")
    return checks


def main() -> None:
    t0 = time.perf_counter()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    mod_550, _ = parse_pan(ROOT / "fixtures" / "equipment" / "ref_550w_bifacial.pan")
    inv_250, _ = parse_ond(ROOT / "fixtures" / "equipment" / "ref_250kw_inverter.ond")
    mod_310, _ = parse_pan(ROOT / "fixtures" / "equipment" / "hyundai_his_m310ti.pan")
    inv_27, _ = parse_ond(ROOT / "fixtures" / "equipment" / "abb_trio_27_6.ond")
    assert mod_550 and inv_250 and mod_310 and inv_27

    mod_550_mono = replace(mod_550, bifaciality_factor=0.0)

    # Pillar A: Alpine DEM terrain vs EU PVGIS printhorizon
    alpine = _run_alpine_terrain_pillar(mod_550, inv_250)

    # Pillar B: Real 892.8 kWp plant 2024 telemetry (US DOE / NREL PVDAQ #2107)
    df_2107, meta_2107 = fetch_and_prepare_pvdaq_2107_2024(RAW_OEDI_CACHE, TELEMETRY_CSV)
    site_2107 = SiteConfig(
        site_name="US DOE PVDAQ #2107 Farm Solar Array (Arbuckle, CA)",
        latitude=38.996306,
        longitude=-122.134111,
        elevation_m=10.0,
        surface_tilt_deg=25.0,
        surface_azimuth_deg=180.0,
        dc_kwp=892.8,  # 24 * 120 modules * 310 W
        gcr=0.45,
        albedo=0.20,
        soiling_loss_frac=0.025,
        dc_wiring_loss_frac=0.015,
        mismatch_loss_frac=0.015,
        availability_frac=1.0,  # outages isolated cleanly in telemetry filter
        use_3d_shading=False,
    )
    field_val = evaluate_field_validation(df_2107, site_2107, mod_310, inv_27, inverter_count=24, plant_age_years=7.0)
    field_val["data_provenance"] = meta_2107
    for m_name, m_stats in field_val["models"].items():
        print(
            f"[PVDAQ #2107 {m_name}] valid_hrs={field_val['valid_operating_hours']}/{field_val['total_daylight_hours']} | "
            f"Meas={m_stats['measured_mwh']} vs Mod={m_stats['modeled_mwh']} MWh | "
            f"MBE={m_stats['mbe_pct']:+.2f}%, nRMSE={m_stats['nrmse_pct']:.2f}%, R2={m_stats['r2']:.4f}"
        )

    # Pillar C: Canonical pvlib ModelChain + 12-step PVsyst loss tree
    mc_parity = _run_modelchain_parity_pillar(mod_550_mono, inv_250)

    out = {
        "engine_version": "0.2.0",
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "pillar_a_alpine_terrain": alpine,
        "pillar_b_pvdaq_2107_field": field_val,
        "pillar_c_modelchain_parity": mc_parity,
    }
    RESULTS_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Saved Phase 2 validation to {RESULTS_PATH} in {out['elapsed_s']}s")


if __name__ == "__main__":
    main()
