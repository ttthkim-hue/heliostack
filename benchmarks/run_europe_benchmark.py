"""Live 4-site European Commission PVGIS v5.3 cross-validation & scenario benchmark."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from heliostack.ess_optimizer import run_full_simulation
from heliostack.formats import parse_ond, parse_pan
from heliostack.models import ObstacleBox3D, SiteConfig
from heliostack.weather import fetch_pvgis_pvcalc, fetch_pvgis_tmy, save_tmy_csv

ROOT = Path(__file__).resolve().parent.parent
WEATHER_DIR = ROOT / "fixtures" / "weather"
RESULTS_PATH = ROOT / "results" / "europe_benchmark_v01.json"

SITES: list[dict[str, Any]] = [
    {"id": "amsterdam", "name": "Amsterdam, Netherlands", "lat": 52.37, "lon": 4.90, "tilt": 35.0, "az": 180.0},
    {"id": "munich", "name": "Munich, Germany", "lat": 48.14, "lon": 11.58, "tilt": 35.0, "az": 180.0},
    {"id": "seville", "name": "Seville, Spain", "lat": 37.39, "lon": -5.98, "tilt": 32.0, "az": 180.0},
    {"id": "busan", "name": "Busan, South Korea", "lat": 35.18, "lon": 129.08, "tilt": 32.0, "az": 180.0},
]


def main() -> None:
    t_all = time.perf_counter()
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    mod, mod_issues = parse_pan(ROOT / "fixtures" / "equipment" / "ref_550w_bifacial.pan")
    inv, inv_issues = parse_ond(ROOT / "fixtures" / "equipment" / "ref_250kw_inverter.ond")
    if mod is None or inv is None:
        raise RuntimeError(f"Equipment parse failure: {mod_issues + inv_issues}")

    mod_mono = replace(mod, bifaciality_factor=0.0)
    site_results: list[dict[str, Any]] = []

    for meta in SITES:
        t_site = time.perf_counter()
        weather, prov = fetch_pvgis_tmy(meta["lat"], meta["lon"], cache_dir=WEATHER_DIR)
        if meta["id"] == "amsterdam":
            save_tmy_csv(weather, WEATHER_DIR / "amsterdam_pvgis_tmy_2023.csv")

        elev = float(prov.get("elevation_m") or 10.0)
        pvcalc_ref = fetch_pvgis_pvcalc(
            latitude=meta["lat"],
            longitude=meta["lon"],
            peakpower_kw=100.0,
            loss_pct=10.0,
            tilt_deg=meta["tilt"],
            surface_azimuth_deg=meta["az"],
            cache_dir=WEATHER_DIR,
        )

        # (a) Open-rack monofacial parity check against EU PVGIS PVcalc (loss=10%)
        cfg_mono = SiteConfig(
            site_name=meta["name"],
            latitude=meta["lat"],
            longitude=meta["lon"],
            elevation_m=elev,
            surface_tilt_deg=meta["tilt"],
            surface_azimuth_deg=meta["az"],
            dc_kwp=100.0,
            gcr=0.40,
            use_3d_shading=False,
            soiling_loss_frac=0.025,
            dc_wiring_loss_frac=0.02,
            mismatch_loss_frac=0.02,
            availability_frac=0.985,
            mounting_mode="open_rack",
            grid_export_limit_kw=100.0,
        )
        res_mono = run_full_simulation(weather, prov, cfg_mono, mod_mono, inv)

        # (b) Standard bifacial land (open_rack) vs Floating PV thermal comparison
        cfg_land = SiteConfig(
            site_name=meta["name"],
            latitude=meta["lat"],
            longitude=meta["lon"],
            elevation_m=elev,
            surface_tilt_deg=meta["tilt"],
            surface_azimuth_deg=meta["az"],
            dc_kwp=100.0,
            gcr=0.45,
            use_3d_shading=True,
            mounting_mode="open_rack",
            grid_export_limit_kw=100.0,
        )
        res_land = run_full_simulation(weather, prov, cfg_land, mod, inv)

        cfg_fpv = replace(cfg_land, mounting_mode="floating_pv", albedo=0.08)
        res_fpv = run_full_simulation(weather, prov, cfg_fpv, mod, inv)

        # Also isolate pure thermal cooling gain on monofacial (same optics, pure cooling effect)
        cfg_land_mono = replace(cfg_land, mounting_mode="open_rack")
        res_land_mono = run_full_simulation(weather, prov, cfg_land_mono, mod_mono, inv)
        cfg_fpv_mono = replace(cfg_land, mounting_mode="floating_pv", albedo=0.20)
        res_fpv_mono = run_full_simulation(weather, prov, cfg_fpv_mono, mod_mono, inv)

        # (c) 3D Obstacle near-shading scenario (realistic nearby parapet/building)
        obstacle = ObstacleBox3D(
            name="South-West Building Block",
            center_east_m=-7.5,
            center_north_m=-10.0,
            width_east_m=12.0,
            depth_north_m=5.0,
            height_m=7.5,
        )
        cfg_shaded = replace(cfg_land, obstacles=[obstacle])
        res_shaded = run_full_simulation(weather, prov, cfg_shaded, mod, inv)

        # (d) 65% Grid Export Cap + LiFePO4 ESS (200 kWh / 50 kW) HiGHS LP Optimization
        cfg_ess = replace(
            cfg_land,
            grid_export_limit_kw=65.0,
            ess_energy_kwh=200.0,
            ess_power_kw=50.0,
        )
        res_ess = run_full_simulation(weather, prov, cfg_ess, mod, inv)

        hs_yield_mono = res_mono.loss_waterfall.specific_yield_kwh_kwp
        pvcalc_yield = pvcalc_ref["specific_yield_kwh_kwp"]
        delta_pct = (hs_yield_mono - pvcalc_yield) / pvcalc_yield * 100.0
        pvcalc_hiy = pvcalc_ref["h_i_y_kwh_m2"]
        poa_delta_pct = (res_land.loss_waterfall.poa_global_kwh_m2 - pvcalc_hiy) / pvcalc_hiy * 100.0

        delta_t_cell = res_fpv.loss_waterfall.mean_cell_temp_day_c - res_land.loss_waterfall.mean_cell_temp_day_c
        fpv_gain_pct = (
            (res_fpv.loss_waterfall.specific_yield_kwh_kwp - res_land.loss_waterfall.specific_yield_kwh_kwp)
            / res_land.loss_waterfall.specific_yield_kwh_kwp
            * 100.0
        )
        fpv_pure_thermal_pct = (
            (res_fpv_mono.loss_waterfall.specific_yield_kwh_kwp - res_land_mono.loss_waterfall.specific_yield_kwh_kwp)
            / res_land_mono.loss_waterfall.specific_yield_kwh_kwp
            * 100.0
        )

        site_entry = {
            "id": meta["id"],
            "name": meta["name"],
            "latitude": meta["lat"],
            "longitude": meta["lon"],
            "elevation_m": elev,
            "tilt_deg": meta["tilt"],
            "radiation_db": prov.get("radiation_db"),
            "pvcalc_radiation_db": pvcalc_ref.get("radiation_db"),
            "tmy_sha256": prov.get("payload_sha256"),
            "ghi_kwh_m2": res_land.loss_waterfall.ghi_kwh_m2,
            "pvgis_hiy_kwh_m2": round(pvcalc_hiy, 2),
            "hs_poa_kwh_m2": res_land.loss_waterfall.poa_global_kwh_m2,
            "poa_delta_pct": round(poa_delta_pct, 2),
            "pvgis_pvcalc_yield_kwh_kwp": round(pvcalc_yield, 2),
            "heliostack_mono_yield_kwh_kwp": round(hs_yield_mono, 2),
            "pvcalc_delta_pct": round(delta_pct, 2),
            "land_bifacial_yield_kwh_kwp": res_land.loss_waterfall.specific_yield_kwh_kwp,
            "land_pr": res_land.loss_waterfall.performance_ratio,
            "land_mean_cell_day_c": res_land.loss_waterfall.mean_cell_temp_day_c,
            "fpv_yield_kwh_kwp": res_fpv.loss_waterfall.specific_yield_kwh_kwp,
            "fpv_mean_cell_day_c": res_fpv.loss_waterfall.mean_cell_temp_day_c,
            "fpv_delta_cell_c": round(delta_t_cell, 2),
            "fpv_pure_thermal_gain_pct": round(fpv_pure_thermal_pct, 2),
            "fpv_yield_delta_pct": round(fpv_gain_pct, 2),
            "shaded_3d_loss_pct": res_shaded.loss_waterfall.shading_loss_pct,
            "shaded_3d_svf": res_shaded.loss_waterfall.diffuse_svf,
            "shaded_3d_yield_kwh_kwp": res_shaded.loss_waterfall.specific_yield_kwh_kwp,
            "ess_curtailed_no_ess_kwh": res_ess.ess_metrics.curtailed_no_ess_kwh_yr,
            "ess_curtailed_with_ess_kwh": res_ess.ess_metrics.curtailed_with_ess_kwh_yr,
            "ess_recovery_pct": res_ess.ess_metrics.curtailment_recovery_pct,
            "ess_cycles_yr": res_ess.ess_metrics.annual_cycles,
            "ess_revenue_uplift_eur_yr": res_ess.ess_metrics.revenue_uplift_eur_yr,
            "ess_lcoe_eur_kwh": res_ess.ess_metrics.lcoe_eur_kwh,
            "ess_lp_solve_s": res_ess.ess_metrics.solve_time_s,
            "ess_conservation_err_kw": res_ess.ess_metrics.max_hourly_conservation_err_kw,
            "land_waterfall": res_land.loss_waterfall.to_dict(),
            "monthly_land_ac_kwh": [round(v, 1) for v in res_land.monthly_ac_kwh],
            "monthly_fpv_ac_kwh": [round(v, 1) for v in res_fpv.monthly_ac_kwh],
            "monthly_curt_no_ess_kwh": [round(v, 1) for v in res_ess.monthly_curtailed_no_ess_kwh],
            "monthly_curt_with_ess_kwh": [round(v, 1) for v in res_ess.monthly_curtailed_with_ess_kwh],
            "site_elapsed_s": round(time.perf_counter() - t_site, 2),
        }
        site_results.append(site_entry)
        print(
            f"[{meta['id']}] PVGIS={pvcalc_yield:.1f} vs HS-mono={hs_yield_mono:.1f} ({delta_pct:+.2f}%) | "
            f"FPV dT={delta_t_cell:+.2f}C ({fpv_gain_pct:+.2f}%) | "
            f"3D-Shade={res_shaded.loss_waterfall.shading_loss_pct:.2f}% | "
            f"ESS Rec={res_ess.ess_metrics.curtailment_recovery_pct:.1f}% ({res_ess.ess_metrics.solve_time_s:.3f}s)"
        )

    out_payload = {
        "engine_version": "0.1.0",
        "total_elapsed_s": round(time.perf_counter() - t_all, 2),
        "sites": site_results,
    }
    RESULTS_PATH.write_text(json.dumps(out_payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved benchmark results to {RESULTS_PATH} in {out_payload['total_elapsed_s']}s")


if __name__ == "__main__":
    main()
