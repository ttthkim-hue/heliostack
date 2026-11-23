"""Thermal physics tests comparing open_rack, convective_land, floating_pv, and ESS HVAC."""

from __future__ import annotations

import numpy as np
import pandas as pd

from heliostack.models import SiteConfig
from heliostack.thermal import compute_cell_temperature, compute_ess_hvac_aux_kw


def test_floating_pv_runs_cooler_than_open_rack_under_sun_and_wind() -> None:
    idx = pd.date_range("2023-07-01", periods=120, freq="h", tz="UTC")
    poa = pd.Series(np.tile(np.concatenate([np.zeros(6), np.full(12, 850.0), np.zeros(6)]), 5), index=idx)
    temp = pd.Series(np.full(120, 32.0), index=idx)
    wind = pd.Series(np.full(120, 3.8), index=idx)
    wdir = pd.Series(np.full(120, 90.0), index=idx)

    site_land = SiteConfig("Land", 37.4, -6.0, mounting_mode="open_rack")
    site_conv = SiteConfig("Conv", 37.4, -6.0, mounting_mode="convective_land")
    site_fpv = SiteConfig("FPV", 37.4, -6.0, mounting_mode="floating_pv")

    t_land = compute_cell_temperature(poa, temp, wind, wdir, site_land)
    t_conv = compute_cell_temperature(poa, temp, wind, wdir, site_conv)
    t_fpv = compute_cell_temperature(poa, temp, wind, wdir, site_fpv)

    day = poa > 500.0
    assert float(t_fpv[day].mean()) < float(t_land[day].mean()) - 2.0
    assert float(t_conv[day].mean()) > 32.0


def test_ess_hvac_aux_scales_with_ambient_heat_and_throughput() -> None:
    assert np.all(compute_ess_hvac_aux_kw(np.array([20.0, 35.0]), np.array([10.0, 10.0]), 0.0) == 0.0)
    aux_cool = compute_ess_hvac_aux_kw(np.array([20.0, 20.0]), np.array([0.0, 50.0]), 200.0)
    aux_hot = compute_ess_hvac_aux_kw(np.array([40.0, 40.0]), np.array([0.0, 50.0]), 200.0)
    assert aux_cool[1] > aux_cool[0] > 0.0
    assert aux_hot[0] > aux_cool[0]
