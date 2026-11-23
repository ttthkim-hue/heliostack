"""Full 8,760-hour offline PV + HiGHS ESS conservation and exceedance tests."""

from __future__ import annotations

import dataclasses
import math
from dataclasses import replace
from pathlib import Path

from heliostack.ess_optimizer import run_full_simulation
from heliostack.formats import parse_ond, parse_pan
from heliostack.models import ObstacleBox3D, SiteConfig
from heliostack.weather import load_cached_tmy

ROOT = Path(__file__).resolve().parent.parent
WEATHER_CSV = ROOT / "fixtures" / "weather" / "amsterdam_pvgis_tmy_2023.csv"
PAN_FILE = ROOT / "fixtures" / "equipment" / "ref_550w_bifacial.pan"
OND_FILE = ROOT / "fixtures" / "equipment" / "ref_250kw_inverter.ond"


def test_8760hr_pv_waterfall_and_highs_ess_conservation() -> None:
    weather, prov = load_cached_tmy(WEATHER_CSV)
    mod, _ = parse_pan(PAN_FILE)
    inv, _ = parse_ond(OND_FILE)
    assert mod is not None and inv is not None

    base_site = SiteConfig(
        site_name="Amsterdam Test",
        latitude=52.37,
        longitude=4.90,
        elevation_m=3.0,
        surface_tilt_deg=35.0,
        surface_azimuth_deg=180.0,
        dc_kwp=100.0,
        gcr=0.45,
        obstacles=[ObstacleBox3D("Parapet", -7.5, -10.0, 10.0, 4.0, 6.5)],
        grid_export_limit_kw=65.0,
        ess_energy_kwh=200.0,
        ess_power_kw=50.0,
    )
    res = run_full_simulation(weather, prov, base_site, mod, inv)

    wf_dict = dataclasses.asdict(res.loss_waterfall)
    for k, v in wf_dict.items():
        if isinstance(v, (int, float)):
            assert math.isfinite(v), f"Non-finite waterfall field {k}={v}"

    assert 0.65 <= res.loss_waterfall.performance_ratio <= 0.96
    assert 800.0 <= res.loss_waterfall.specific_yield_kwh_kwp <= 1500.0
    assert res.loss_waterfall.shading_loss_pct > 2.0
    assert res.loss_waterfall.p99_kwh_yr < res.loss_waterfall.p90_kwh_yr < res.loss_waterfall.p75_kwh_yr < res.loss_waterfall.p50_kwh_yr

    ess = res.ess_metrics
    assert ess.solver_success is True
    assert ess.max_hourly_conservation_err_kw < 1e-6
    assert ess.curtailed_no_ess_kwh_yr > 1000.0
    assert ess.curtailment_recovery_pct > 80.0
    assert ess.annual_cycles > 50.0
    assert ess.ess_hvac_aux_kwh_yr > 100.0
    assert ess.revenue_uplift_eur_yr > 500.0

    # Baseline without ESS reports zero cycles and higher curtailment
    no_ess_site = replace(base_site, ess_energy_kwh=0.0, ess_power_kw=0.0)
    res_no = run_full_simulation(weather, prov, no_ess_site, mod, inv)
    assert res_no.ess_metrics.annual_cycles == 0.0
    assert res_no.ess_metrics.curtailed_with_ess_kwh_yr == res_no.ess_metrics.curtailed_no_ess_kwh_yr
