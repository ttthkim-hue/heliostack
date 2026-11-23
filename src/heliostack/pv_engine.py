"""8,760-hour deterministic photovoltaic physics, loss waterfall, and P50/P90 engine."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pvlib

from heliostack.models import (
    InverterSpec,
    LossWaterfall,
    PVModuleSpec,
    SiteConfig,
)
from heliostack.shading import compute_near_shading
from heliostack.thermal import compute_cell_temperature

_KB_EV = 8.617333262e-5  # eV / K
_T_REF_K = 298.15


def derive_pvsyst_single_diode_params(module: PVModuleSpec) -> tuple[float, float]:
    """Derive STC photocurrent I_L_ref and diode saturation current I_o_ref from module specs."""
    v_th = _KB_EV * _T_REF_K
    n_ns_vth = module.gamma_ref * module.cells_in_series * v_th
    i_l_ref = module.i_sc_a * (1.0 + module.r_s_ohm / max(1e-6, module.r_sh_ref_ohm))
    exp_voc = math.exp(min(80.0, module.v_oc_v / max(1e-6, n_ns_vth)))
    i_o_ref = max(1e-14, (i_l_ref - module.v_oc_v / max(1e-6, module.r_sh_ref_ohm)) / max(1.0, exp_voc - 1.0))
    return float(i_l_ref), float(i_o_ref)


def _inverter_efficiency_fraction(load_frac: np.ndarray, inverter: InverterSpec) -> np.ndarray:
    """Interpolate inverter efficiency (0..1) from .OND curve across normalized load fraction."""
    curve = inverter.efficiency_curve_pct
    if not curve:
        return np.full_like(load_frac, inverter.eff_euro_pct / 100.0, dtype=float)
    xp = np.array([pt[0] / 100.0 for pt in curve], dtype=float)
    fp = np.array([pt[1] / 100.0 for pt in curve], dtype=float)
    return np.interp(np.clip(load_frac, 0.0, 1.5), xp, fp)


def _solve_single_diode_pmp(
    effective_irradiance: float | np.ndarray,
    temp_cell: float | np.ndarray,
    module: PVModuleSpec,
    i_l_ref: float,
    i_o_ref: float,
) -> float | np.ndarray:
    """Evaluate single-diode maximum power P_mp (W per module) via pvlib PVsyst model."""
    il, io, rs, rsh, nns = pvlib.pvsystem.calcparams_pvsyst(
        effective_irradiance=effective_irradiance,
        temp_cell=temp_cell,
        alpha_sc=module.alpha_sc_a_per_c,
        gamma_ref=module.gamma_ref,
        mu_gamma=module.mu_gamma,
        I_L_ref=i_l_ref,
        I_o_ref=i_o_ref,
        R_sh_ref=module.r_sh_ref_ohm,
        R_sh_0=module.r_sh_0_ohm,
        R_s=module.r_s_ohm,
        cells_in_series=module.cells_in_series,
        R_sh_exp=module.r_sh_exp,
        EgRef=module.eg_ref_ev,
    )
    sd = pvlib.pvsystem.singlediode(il, io, rs, rsh, nns)
    if isinstance(effective_irradiance, np.ndarray):
        return np.maximum(0.0, np.asarray(sd["p_mp"], dtype=float))
    return max(0.0, float(sd["p_mp"]))


def _evaluate_dc_ac_stage(
    eff_irrad: np.ndarray,
    t_cell: np.ndarray,
    site: SiteConfig,
    module: PVModuleSpec,
    inverter: InverterSpec,
    dc_aging_factor: float = 1.0,
    inverter_count_override: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Shared deterministic single-diode DC + .OND inverter AC pipeline."""
    i_l_ref, i_o_ref = derive_pvsyst_single_diode_params(module)
    stc_p_mp = float(_solve_single_diode_pmp(1000.0, 25.0, module, i_l_ref, i_o_ref))
    stc_scale = module.p_nom_w / max(1e-6, stc_p_mp)

    active = eff_irrad > 1.0
    dc_stc_temp_kw = np.zeros_like(eff_irrad)
    dc_actual_kw = np.zeros_like(eff_irrad)
    if np.any(active):
        scale_kw = stc_scale * (site.dc_kwp / module.p_nom_w) * dc_aging_factor
        t_iso = np.full(int(np.sum(active)), 25.0)
        dc_stc_temp_kw[active] = _solve_single_diode_pmp(eff_irrad[active], t_iso, module, i_l_ref, i_o_ref) * scale_kw
        dc_actual_kw[active] = _solve_single_diode_pmp(eff_irrad[active], t_cell[active], module, i_l_ref, i_o_ref) * scale_kw

    dc_after_losses_kw = (
        dc_actual_kw
        * (1.0 - site.dc_wiring_loss_frac)
        * (1.0 - site.mismatch_loss_frac)
        * site.availability_frac
    )

    if inverter_count_override is not None:
        n_inv = max(1, int(inverter_count_override))
    elif site.dc_kwp > inverter.p_max_ac_kw * 1.3:
        n_inv = max(1, round(site.dc_kwp / (inverter.p_nom_ac_kw * 1.15)))
    else:
        n_inv = 1

    inv_nom_total_kw = n_inv * inverter.p_nom_ac_kw
    inv_max_total_kw = n_inv * inverter.p_max_ac_kw
    p_thresh_total = n_inv * inverter.p_threshold_kw
    night_loss_total = n_inv * inverter.night_loss_kw

    running = dc_after_losses_kw > p_thresh_total
    load_frac = np.where(running, dc_after_losses_kw / max(1e-6, inv_nom_total_kw), 0.0)
    eff_curve = _inverter_efficiency_fraction(load_frac, inverter)
    ac_unclipped_kw = np.where(running, dc_after_losses_kw * eff_curve, 0.0)
    ac_net_kw = np.where(running, np.minimum(ac_unclipped_kw, inv_max_total_kw), 0.0)
    return (
        dc_stc_temp_kw,
        dc_actual_kw,
        dc_after_losses_kw,
        ac_unclipped_kw,
        ac_net_kw,
        running,
        night_loss_total,
        inv_max_total_kw,
    )


def run_pv_simulation(
    weather: pd.DataFrame,
    site: SiteConfig,
    module: PVModuleSpec,
    inverter: InverterSpec,
) -> tuple[LossWaterfall, np.ndarray, np.ndarray, np.ndarray]:
    """Execute full 8,760-hour PV simulation returning waterfall, hourly AC kW, POA, and T_cell."""
    times = weather.index
    loc = pvlib.location.Location(
        latitude=site.latitude,
        longitude=site.longitude,
        altitude=site.elevation_m,
        tz="UTC",
    )
    solpos = loc.get_solarposition(
        times,
        pressure=weather["pressure"],
        temperature=weather["temp_air"],
    )
    zenith = solpos["apparent_zenith"]
    azimuth = solpos["azimuth"]
    elevation = 90.0 - zenith

    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    airmass = pvlib.atmosphere.get_relative_airmass(zenith.clip(upper=89.5))

    albedo_eff = site.albedo
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=site.surface_tilt_deg,
        surface_azimuth=site.surface_azimuth_deg,
        solar_zenith=zenith,
        solar_azimuth=azimuth,
        dni=weather["dni"],
        ghi=weather["ghi"],
        dhi=weather["dhi"],
        dni_extra=dni_extra,
        airmass=airmass,
        albedo=albedo_eff,
        model="perez",
        diffuse_components=True,
    )

    sun_up = elevation.to_numpy(dtype=float) > 0.0
    poa_beam = np.where(sun_up, np.nan_to_num(poa["poa_direct"].to_numpy(dtype=float), nan=0.0), 0.0)
    poa_sky_diff = np.where(sun_up, np.nan_to_num(poa["poa_sky_diffuse"].to_numpy(dtype=float), nan=0.0), 0.0)
    poa_ground_diff = np.where(sun_up, np.nan_to_num(poa["poa_ground_diffuse"].to_numpy(dtype=float), nan=0.0), 0.0)
    poa_beam = np.maximum(0.0, poa_beam)
    poa_sky_diff = np.maximum(0.0, poa_sky_diff)
    poa_ground_diff = np.maximum(0.0, poa_ground_diff)
    poa_global_unshaded = poa_beam + poa_sky_diff + poa_ground_diff

    # Incidence Angle Modifier (Martin-Ruiz) applied to beam and weighted diffuse
    aoi = pvlib.irradiance.aoi(
        surface_tilt=site.surface_tilt_deg,
        surface_azimuth=site.surface_azimuth_deg,
        solar_zenith=zenith,
        solar_azimuth=azimuth,
    )
    a_r = 0.16 if module.iam_b0 <= 0.055 else min(0.30, 0.12 + 0.8 * module.iam_b0)
    iam_beam = np.where(aoi < 90.0, pvlib.iam.martin_ruiz(aoi.clip(0.0, 90.0), a_r=a_r), 0.0)
    iam_diff = float(pvlib.iam.martin_ruiz(60.0, a_r=a_r))

    # 3D near-shading & diffuse Sky-View Factor
    if site.use_3d_shading:
        shade = compute_near_shading(
            solar_elevation_deg=elevation.to_numpy(dtype=float),
            solar_azimuth_deg=azimuth.to_numpy(dtype=float),
            surface_tilt_deg=site.surface_tilt_deg,
            surface_azimuth_deg=site.surface_azimuth_deg,
            array_height_m=site.array_height_m,
            row_length_m=site.row_length_m,
            row_depth_m=site.row_depth_m,
            gcr=site.gcr,
            obstacles=site.obstacles,
            horizon_elev_deg_36=site.horizon_elev_deg_36,
            beam_irradiance_weight=poa_beam,
        )
        beam_factor = 1.0 - shade.beam_shaded_fraction
        svf_ratio = shade.diffuse_svf / max(1e-6, 0.5 * (1.0 + math.cos(math.radians(site.surface_tilt_deg))))
        svf_ratio = min(1.0, max(0.2, svf_ratio))
        diffuse_svf = shade.diffuse_svf
        rear_vf = shade.rear_view_factor
    else:
        beam_factor = np.ones_like(poa_beam)
        svf_ratio = 1.0
        diffuse_svf = 0.5 * (1.0 + math.cos(math.radians(site.surface_tilt_deg)))
        rear_vf = 0.15

    # Step-by-step irradiance accounting for clean waterfall
    poa_after_shade = poa_beam * beam_factor + poa_sky_diff * svf_ratio + poa_ground_diff
    poa_after_iam = poa_beam * beam_factor * iam_beam + (poa_sky_diff * svf_ratio + poa_ground_diff) * iam_diff
    soil_factor = 1.0 - site.soiling_loss_frac
    poa_front_eff = poa_after_iam * soil_factor

    # Rear-side bifacial gain (ground-reflected GHI + diffuse sky spill behind row)
    ghi_arr = np.maximum(0.0, weather["ghi"].to_numpy(dtype=float))
    rear_irrad = ghi_arr * albedo_eff * rear_vf * (1.0 - 0.35 * site.gcr) * iam_diff * soil_factor
    bifi_eff_added = rear_irrad * module.bifaciality_factor
    eff_irrad = np.maximum(0.0, poa_front_eff + bifi_eff_added)

    # Cell temperature from selected mounting mode (open_rack | convective_land | floating_pv)
    poa_for_temp = pd.Series(poa_after_shade + rear_irrad, index=times)
    t_cell = compute_cell_temperature(
        poa_global=poa_for_temp,
        temp_air=weather["temp_air"],
        wind_speed=weather["wind_speed"],
        wind_direction=weather["wind_direction"],
        site=site,
    ).to_numpy(dtype=float)

    # Shared Single-Diode DC + .OND Inverter AC Stage
    dc_nominal_kw = site.dc_kwp * (eff_irrad / 1000.0)
    (
        dc_stc_temp_kw,
        dc_actual_kw,
        dc_after_losses_kw,
        ac_unclipped_kw,
        ac_net_kw,
        running,
        night_loss_total,
        _,
    ) = _evaluate_dc_ac_stage(eff_irrad, t_cell, site, module, inverter)

    # Loss waterfall aggregation (kWh/m^2 or %)
    ghi_sum = float(np.sum(ghi_arr)) / 1000.0
    poa_sum = float(np.sum(poa_global_unshaded)) / 1000.0
    poa_shade_sum = float(np.sum(poa_after_shade)) / 1000.0
    poa_iam_sum = float(np.sum(poa_after_iam)) / 1000.0
    poa_front_sum = float(np.sum(poa_front_eff)) / 1000.0
    poa_eff_sum = float(np.sum(eff_irrad)) / 1000.0

    trans_gain_pct = ((poa_sum / max(1e-6, ghi_sum)) - 1.0) * 100.0
    shade_loss_pct = (1.0 - poa_shade_sum / max(1e-6, poa_sum)) * 100.0
    iam_loss_pct = (1.0 - poa_iam_sum / max(1e-6, poa_shade_sum)) * 100.0
    soil_loss_pct = (1.0 - poa_front_sum / max(1e-6, poa_iam_sum)) * 100.0
    bifi_gain_pct = ((poa_eff_sum / max(1e-6, poa_front_sum)) - 1.0) * 100.0

    dc_25_sum = float(np.sum(dc_stc_temp_kw))
    dc_act_sum = float(np.sum(dc_actual_kw))
    dc_after_sum = float(np.sum(dc_after_losses_kw))
    ac_unclip_sum = float(np.sum(ac_unclipped_kw))
    ac_net_raw_sum = float(np.sum(ac_net_kw))
    # Subtract idle night tare proportionally only when producing grid-connected power
    night_hours = float(np.sum(~running))
    ac_net_sum = max(0.0, ac_net_raw_sum - night_hours * night_loss_total)

    thermal_loss_pct = (1.0 - dc_act_sum / max(1e-6, dc_25_sum)) * 100.0
    mismatch_wiring_pct = (1.0 - dc_after_sum / max(1e-6, dc_act_sum)) * 100.0
    inv_eff_loss_pct = (1.0 - ac_unclip_sum / max(1e-6, dc_after_sum)) * 100.0
    clipping_loss_pct = (1.0 - ac_net_raw_sum / max(1e-6, ac_unclip_sum)) * 100.0

    day_mask = poa_global_unshaded > 50.0
    mean_cell_day = float(np.mean(t_cell[day_mask])) if np.any(day_mask) else float(np.mean(t_cell))
    spec_yield = ac_net_sum / max(1e-6, site.dc_kwp)
    pr = ac_net_sum / max(1e-6, site.dc_kwp * poa_sum)

    # P50 / P75 / P90 / P99 annual uncertainty (interannual irradiance 3.5% + model/transposition 2.2% + soiling/degradation 1.5%)
    sigma_total = math.sqrt(0.035**2 + 0.022**2 + 0.015**2)  # ~4.40% combined 1-sigma
    p50 = ac_net_sum
    p75 = p50 * (1.0 - 0.67449 * sigma_total)
    p90 = p50 * (1.0 - 1.28155 * sigma_total)
    p99 = p50 * (1.0 - 2.32635 * sigma_total)

    waterfall = LossWaterfall(
        ghi_kwh_m2=round(ghi_sum, 2),
        poa_global_kwh_m2=round(poa_sum, 2),
        poa_effective_kwh_m2=round(poa_eff_sum, 2),
        transposition_gain_pct=round(trans_gain_pct, 2),
        iam_loss_pct=round(iam_loss_pct, 2),
        shading_loss_pct=round(shade_loss_pct, 2),
        diffuse_svf=round(diffuse_svf, 4),
        soiling_loss_pct=round(soil_loss_pct, 2),
        bifacial_gain_pct=round(bifi_gain_pct, 2),
        thermal_loss_pct=round(thermal_loss_pct, 2),
        mean_cell_temp_day_c=round(mean_cell_day, 2),
        dc_nominal_kwh_yr=round(float(np.sum(dc_nominal_kw)), 2),
        dc_after_losses_kwh_yr=round(dc_after_sum, 2),
        mismatch_wiring_loss_pct=round(mismatch_wiring_pct, 2),
        inverter_eff_loss_pct=round(inv_eff_loss_pct, 2),
        clipping_loss_pct=round(clipping_loss_pct, 2),
        net_ac_before_curtail_kwh_yr=round(ac_net_sum, 2),
        specific_yield_kwh_kwp=round(spec_yield, 2),
        performance_ratio=round(pr, 4),
        p50_kwh_yr=round(p50, 2),
        p75_kwh_yr=round(p75, 2),
        p90_kwh_yr=round(p90, 2),
        p99_kwh_yr=round(p99, 2),
    )
    return waterfall, ac_net_kw, poa_global_unshaded, t_cell


def run_pv_from_measured_poa(
    times: pd.DatetimeIndex,
    poa_global: np.ndarray,
    temp_air: np.ndarray,
    wind_speed: np.ndarray,
    wind_direction: np.ndarray,
    site: SiteConfig,
    module: PVModuleSpec,
    inverter: InverterSpec,
    dc_aging_factor: float = 1.0,
    inverter_count_override: int | None = None,
) -> dict[str, np.ndarray | float]:
    """Run deterministic PV DC/AC pipeline directly from measured POA telemetry."""
    loc = pvlib.location.Location(site.latitude, site.longitude, altitude=site.elevation_m, tz="UTC")
    solpos = loc.get_solarposition(times)
    aoi = pvlib.irradiance.aoi(
        surface_tilt=site.surface_tilt_deg,
        surface_azimuth=site.surface_azimuth_deg,
        solar_zenith=solpos["apparent_zenith"],
        solar_azimuth=solpos["azimuth"],
    )
    a_r = 0.16 if module.iam_b0 <= 0.055 else min(0.30, 0.12 + 0.8 * module.iam_b0)
    iam_beam = np.where(aoi < 90.0, pvlib.iam.martin_ruiz(aoi.clip(0.0, 90.0), a_r=a_r), 0.0)
    iam_diff = float(pvlib.iam.martin_ruiz(60.0, a_r=a_r))
    iam_eff = np.where(solpos["apparent_zenith"] < 87.0, 0.85 * iam_beam + 0.15 * iam_diff, iam_diff)

    poa_clean = np.maximum(0.0, np.nan_to_num(poa_global, nan=0.0))
    eff_irrad = poa_clean * iam_eff * (1.0 - site.soiling_loss_frac)

    t_cell = compute_cell_temperature(
        poa_global=pd.Series(poa_clean, index=times),
        temp_air=pd.Series(temp_air, index=times),
        wind_speed=pd.Series(wind_speed, index=times),
        wind_direction=pd.Series(wind_direction, index=times),
        site=site,
    ).to_numpy(dtype=float)

    _, _, dc_after_kw, ac_unclip_kw, ac_net_kw, _, _, inv_max_total_kw = _evaluate_dc_ac_stage(
        eff_irrad=eff_irrad,
        t_cell=t_cell,
        site=site,
        module=module,
        inverter=inverter,
        dc_aging_factor=dc_aging_factor,
        inverter_count_override=inverter_count_override,
    )
    return {
        "ac_net_kw": ac_net_kw,
        "ac_unclipped_kw": ac_unclip_kw,
        "dc_after_losses_kw": dc_after_kw,
        "temp_cell_c": t_cell,
        "inv_max_total_kw": float(inv_max_total_kw),
    }
