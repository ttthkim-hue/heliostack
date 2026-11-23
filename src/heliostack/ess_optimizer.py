"""Sparse 8,760-hour HiGHS linear programming optimizer for LiFePO4 ESS & curtailment recovery."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import csc_matrix

from heliostack.models import ESSMetrics, SiteConfig
from heliostack.thermal import compute_ess_hvac_aux_kw


def _local_tariff_profile(times: pd.DatetimeIndex, site: SiteConfig) -> np.ndarray:
    """Construct hourly export price array with evening peak arbitrage window (17:00-21:00 local)."""
    tz_offset = round(site.longitude / 15.0)
    local_hour = (times.hour.to_numpy(dtype=int) + tz_offset) % 24
    is_peak = (local_hour >= 17) & (local_hour <= 21)
    return np.where(is_peak, site.tariff_peak_eur_kwh, site.tariff_export_eur_kwh)


def _economic_summary(
    site: SiteConfig,
    net_export_no_ess: float,
    net_export_with_ess: float,
    rev_no_ess: float,
    rev_with_ess: float,
) -> tuple[float, float | None, float]:
    """Compute project LCOE, simple payback of ESS add-on, and 20-year NPV."""
    capex_pv = site.dc_kwp * site.capex_pv_eur_kwp
    capex_ess = site.ess_energy_kwh * site.capex_ess_eur_kwh
    capex_total = capex_pv + capex_ess
    opex_yr = site.dc_kwp * site.opex_eur_kwp_yr + 0.012 * capex_ess

    r = site.discount_rate
    n_yr = site.project_life_years
    # Capital Recovery / Present-Value Annuity factor with 0.5%/yr linear PV degradation
    pv_factor = sum(((1.0 - 0.005 * (y - 1)) / ((1.0 + r) ** y)) for y in range(1, n_yr + 1))
    annuity_factor = sum(1.0 / ((1.0 + r) ** y) for y in range(1, n_yr + 1))

    energy_pv = max(1e-6, net_export_with_ess * pv_factor)
    lcoe = (capex_total + opex_yr * annuity_factor) / energy_pv
    rev_uplift = rev_with_ess - rev_no_ess
    payback = (capex_ess / rev_uplift) if (capex_ess > 0 and rev_uplift > 1e-3) else None
    npv = -capex_total + rev_with_ess * pv_factor - opex_yr * annuity_factor
    return round(lcoe, 5), (round(payback, 2) if payback is not None else None), round(npv, 2)


def optimize_ess_dispatch(
    pv_ac_kw: np.ndarray,
    times: pd.DatetimeIndex,
    ambient_temp_c: np.ndarray,
    site: SiteConfig,
) -> tuple[ESSMetrics, np.ndarray, np.ndarray]:
    """Solve 8,760-hour periodic ESS dispatch LP using SciPy HiGHS."""
    t0 = time.perf_counter()
    n = len(pv_ac_kw)
    tariff = _local_tariff_profile(times, site)

    p_exp_no_ess = np.minimum(pv_ac_kw, site.grid_export_limit_kw)
    p_curt_no_ess = np.maximum(0.0, pv_ac_kw - p_exp_no_ess)
    pv_avail_kwh = float(np.sum(pv_ac_kw))
    curt_no_ess_kwh = float(np.sum(p_curt_no_ess))
    exp_no_ess_kwh = float(np.sum(p_exp_no_ess))
    rev_no_ess = float(np.sum(p_exp_no_ess * tariff))

    if site.ess_energy_kwh <= 0.0 or site.ess_power_kw <= 0.0:
        lcoe, payback, npv = _economic_summary(site, exp_no_ess_kwh, exp_no_ess_kwh, rev_no_ess, rev_no_ess)
        return (
            ESSMetrics(
                solver_success=True,
                solver_message="No ESS configured (baseline analytic dispatch).",
                solve_time_s=round(time.perf_counter() - t0, 4),
                pv_ac_available_kwh_yr=round(pv_avail_kwh, 2),
                curtailed_no_ess_kwh_yr=round(curt_no_ess_kwh, 2),
                curtailed_with_ess_kwh_yr=round(curt_no_ess_kwh, 2),
                curtailment_recovery_pct=0.0,
                net_export_no_ess_kwh_yr=round(exp_no_ess_kwh, 2),
                net_export_with_ess_kwh_yr=round(exp_no_ess_kwh, 2),
                ess_charge_kwh_yr=0.0,
                ess_discharge_kwh_yr=0.0,
                ess_hvac_aux_kwh_yr=0.0,
                annual_cycles=0.0,
                revenue_no_ess_eur_yr=round(rev_no_ess, 2),
                revenue_with_ess_eur_yr=round(rev_no_ess, 2),
                revenue_uplift_eur_yr=0.0,
                lcoe_eur_kwh=lcoe,
                simple_payback_ess_yr=payback,
                npv_20yr_eur=npv,
                max_hourly_conservation_err_kw=0.0,
            ),
            p_curt_no_ess,
            p_curt_no_ess,
        )

    # Variables stacked in 6 blocks of length N = 8760:
    # 0: exp[t]     in [0, grid_export_limit_kw]
    # 1: imp_aux[t] in [0, 50.0] (strictly emergency night HVAC feed, higher cost)
    # 2: chg[t]     in [0, ess_power_kw]
    # 3: dis[t]     in [0, ess_power_kw]
    # 4: soc[t]     in [soc_min * E_nom, soc_max * E_nom]
    # 5: curt[t]    in [0, max(pv_ac_kw)]
    cop_hvac = 3.2
    alpha_hvac = 0.025 / cop_hvac
    aux_standby = compute_ess_hvac_aux_kw(ambient_temp_c, np.zeros(n), site.ess_energy_kwh, cop_cooling=cop_hvac)
    wear_cost = 0.012  # EUR/kWh throughput degradation penalty (prevents zero-profit cycling & simultaneous chg/dis)
    imp_price = max(0.28, site.tariff_peak_eur_kwh + 0.10)

    c = np.zeros(6 * n, dtype=float)
    c[0:n] = -tariff
    c[n : 2 * n] = imp_price
    c[2 * n : 3 * n] = wear_cost
    c[3 * n : 4 * n] = wear_cost
    # tiny positive cost on curtailment prefers legitimate export/storage over artificial waste
    c[5 * n : 6 * n] = 1e-4

    # Build sparse equality system A_eq @ x = b_eq (2*N rows):
    # Rows 0..N-1 (AC bus power balance):
    #   exp[t] - imp_aux[t] + (1 + alpha)*chg[t] - (1 - alpha)*dis[t] + curt[t] == pv_ac[t] - aux_standby[t]
    # Rows N..2N-1 (Periodic SoC conservation):
    #   soc[t] - soc[(t-1)%N] - eta_c*chg[t] + (1/eta_d)*dis[t] == 0
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    t_idx = np.arange(n, dtype=int)
    t_prev = np.roll(t_idx, 1)

    def _add_block(r_arr: np.ndarray, c_arr: np.ndarray, v_arr: np.ndarray) -> None:
        rows.append(r_arr)
        cols.append(c_arr)
        vals.append(v_arr)

    # Balance rows
    _add_block(t_idx, t_idx, np.ones(n))
    _add_block(t_idx, n + t_idx, -np.ones(n))
    _add_block(t_idx, 2 * n + t_idx, np.full(n, 1.0 + alpha_hvac))
    _add_block(t_idx, 3 * n + t_idx, np.full(n, -(1.0 - alpha_hvac)))
    _add_block(t_idx, 5 * n + t_idx, np.ones(n))

    # SoC conservation rows
    _add_block(n + t_idx, 4 * n + t_idx, np.ones(n))
    _add_block(n + t_idx, 4 * n + t_prev, -np.ones(n))
    _add_block(n + t_idx, 2 * n + t_idx, np.full(n, -site.ess_eta_charge))
    _add_block(n + t_idx, 3 * n + t_idx, np.full(n, 1.0 / site.ess_eta_discharge))

    a_eq = csc_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
        shape=(2 * n, 6 * n),
    )
    b_eq = np.concatenate([pv_ac_kw - aux_standby, np.zeros(n, dtype=float)])

    max_aux_bound = max(50.0, float(np.max(aux_standby)) * 2.0)
    soc_lo = site.ess_soc_min * site.ess_energy_kwh
    soc_hi = site.ess_soc_max * site.ess_energy_kwh
    lb = np.concatenate(
        [
            np.zeros(n),
            np.zeros(n),
            np.zeros(n),
            np.zeros(n),
            np.full(n, soc_lo),
            np.zeros(n),
        ]
    )
    ub = np.concatenate(
        [
            np.full(n, site.grid_export_limit_kw),
            np.full(n, max_aux_bound),
            np.full(n, site.ess_power_kw),
            np.full(n, site.ess_power_kw),
            np.full(n, soc_hi),
            np.maximum(0.0, pv_ac_kw),
        ]
    )
    bounds = list(zip(lb, ub, strict=True))

    res = linprog(c, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    elapsed = time.perf_counter() - t0
    if not res.success:
        raise RuntimeError(f"HiGHS ESS dispatch LP failed: {res.message}")

    x = res.x
    exp = x[0:n]
    imp_aux = x[n : 2 * n]
    chg = x[2 * n : 3 * n]
    dis = x[3 * n : 4 * n]
    curt_with = x[5 * n : 6 * n]

    residual = a_eq @ x - b_eq
    max_err = float(np.max(np.abs(residual)))

    curt_with_kwh = float(np.sum(curt_with))
    recovery_pct = ((curt_no_ess_kwh - curt_with_kwh) / curt_no_ess_kwh * 100.0) if curt_no_ess_kwh > 1e-6 else 0.0
    net_exp_with_kwh = float(np.sum(exp - imp_aux))
    chg_kwh = float(np.sum(chg))
    dis_kwh = float(np.sum(dis))
    hvac_kwh = float(np.sum(aux_standby + alpha_hvac * (chg + dis)))
    usable_kwh = max(1e-6, (site.ess_soc_max - site.ess_soc_min) * site.ess_energy_kwh)
    cycles = (0.5 * (chg_kwh * site.ess_eta_charge + dis_kwh / site.ess_eta_discharge)) / usable_kwh

    rev_with_ess = float(np.sum(exp * tariff - imp_aux * imp_price))
    lcoe, payback, npv = _economic_summary(site, exp_no_ess_kwh, net_exp_with_kwh, rev_no_ess, rev_with_ess)

    metrics = ESSMetrics(
        solver_success=bool(res.success),
        solver_message=str(res.message),
        solve_time_s=round(elapsed, 4),
        pv_ac_available_kwh_yr=round(pv_avail_kwh, 2),
        curtailed_no_ess_kwh_yr=round(curt_no_ess_kwh, 2),
        curtailed_with_ess_kwh_yr=round(curt_with_kwh, 2),
        curtailment_recovery_pct=round(recovery_pct, 2),
        net_export_no_ess_kwh_yr=round(exp_no_ess_kwh, 2),
        net_export_with_ess_kwh_yr=round(net_exp_with_kwh, 2),
        ess_charge_kwh_yr=round(chg_kwh, 2),
        ess_discharge_kwh_yr=round(dis_kwh, 2),
        ess_hvac_aux_kwh_yr=round(hvac_kwh, 2),
        annual_cycles=round(cycles, 2),
        revenue_no_ess_eur_yr=round(rev_no_ess, 2),
        revenue_with_ess_eur_yr=round(rev_with_ess, 2),
        revenue_uplift_eur_yr=round(rev_with_ess - rev_no_ess, 2),
        lcoe_eur_kwh=lcoe,
        simple_payback_ess_yr=payback,
        npv_20yr_eur=npv,
        max_hourly_conservation_err_kw=round(max_err, 9),
    )
    return metrics, p_curt_no_ess, curt_with


def run_full_simulation(
    weather: pd.DataFrame,
    weather_provenance: dict[str, Any],
    site: SiteConfig,
    module,
    inverter,
):
    """Run linked 8,760-hr PV + shading + thermal + HiGHS ESS simulation."""
    from heliostack.models import SimulationResult
    from heliostack.pv_engine import run_pv_simulation

    wf, ac_net_kw, _, _ = run_pv_simulation(weather=weather, site=site, module=module, inverter=inverter)
    ess, curt_no_ess, curt_with_ess = optimize_ess_dispatch(
        pv_ac_kw=ac_net_kw,
        times=weather.index,
        ambient_temp_c=weather["temp_air"].to_numpy(dtype=float),
        site=site,
    )

    months = weather.index.month
    monthly_ac = [float(np.sum(ac_net_kw[months == m])) for m in range(1, 13)]
    monthly_curt_no = [float(np.sum(curt_no_ess[months == m])) for m in range(1, 13)]
    monthly_curt_with = [float(np.sum(curt_with_ess[months == m])) for m in range(1, 13)]

    return SimulationResult(
        site=site,
        module=module,
        inverter=inverter,
        weather_provenance=weather_provenance,
        loss_waterfall=wf,
        ess_metrics=ess,
        monthly_ac_kwh=monthly_ac,
        monthly_curtailed_no_ess_kwh=monthly_curt_no,
        monthly_curtailed_with_ess_kwh=monthly_curt_with,
    )
