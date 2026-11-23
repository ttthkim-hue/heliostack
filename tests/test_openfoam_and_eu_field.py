"""Tests for OpenFOAM 14 tilted-PV thermal surrogate and EU Cyprus 1-year validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from heliostack.models import SiteConfig
from heliostack.telemetry import evaluate_eu_cyprus_validation, load_cyprus_telemetry_csv
from heliostack.thermal import compute_cell_temperature, load_openfoam_surrogate

ROOT = Path(__file__).resolve().parent.parent
CYPRUS_CSV = ROOT / "fixtures" / "telemetry" / "eu_cyprus_pcoe_2015_2016_hourly.csv"


def test_openfoam14_surrogate_physics_and_fpv_cooling(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_openfoam_surrogate(tmp_path / "missing_surrogate.json")
    surr = load_openfoam_surrogate()
    assert "OpenFOAM 14" in surr["solver"]
    surfaces = surr["surfaces"]
    assert "land_rack" in surfaces and "floating_pv" in surfaces

    for sname in ("land_rack", "floating_pv"):
        cases = surfaces[sname]["cases"]
        winds = [c["wind_speed_ms"] for c in cases]
        h_convs = [c["h_conv_total_w_m2k"] for c in cases]
        assert winds == sorted(winds)
        assert all(h2 > h1 for h1, h2 in zip(h_convs[:-1], h_convs[1:], strict=True))
        eq = surfaces[sname]["faiman_equivalent"]
        assert 15.0 < eq["u0"] < 45.0
        assert 2.0 < eq["u1"] < 15.0

    # Radiative + pontoon clearance advantage makes cfd_floating_pv cooler than cfd_land
    fpv_u0 = surfaces["floating_pv"]["faiman_equivalent"]["u0"]
    land_u0 = surfaces["land_rack"]["faiman_equivalent"]["u0"]
    assert fpv_u0 > land_u0

    idx = pd.date_range("2024-07-01", periods=96, freq="1h", tz="UTC")
    poa = pd.Series(np.tile(np.concatenate([np.zeros(6), np.full(12, 900.0), np.zeros(6)]), 4), index=idx)
    ta = pd.Series(np.full(96, 30.0), index=idx)
    ws = pd.Series(np.full(96, 3.0), index=idx)
    wd = pd.Series(np.full(96, 90.0), index=idx)

    tc_land = compute_cell_temperature(poa, ta, ws, wd, SiteConfig("CFD Land", 35.1, 33.4, mounting_mode="cfd_land"))
    tc_fpv = compute_cell_temperature(poa, ta, ws, wd, SiteConfig("CFD FPV", 35.1, 33.4, mounting_mode="cfd_floating_pv"))
    day = poa > 500.0
    assert float(tc_fpv[day].mean()) < float(tc_land[day].mean()) - 1.5


def test_eu_cyprus_pcoe_thermal_and_power_validation(tmp_path: Path) -> None:
    df = load_cyprus_telemetry_csv(CYPRUS_CSV)
    assert len(df) == 8784

    bad = tmp_path / "bad_cyprus.csv"
    df.drop(columns=["temp_module_c"]).head(10).to_csv(bad, index_label="time_local")
    with pytest.raises(ValueError, match="missing columns"):
        load_cyprus_telemetry_csv(bad)

    res = evaluate_eu_cyprus_validation(df)
    assert res["valid_operating_hours"] > 3500

    cfd = res["models"]["cfd_land"]
    assert cfd["module_temp"]["rmse_c"] < 6.0
    assert cfd["module_temp"]["r2"] > 0.85
    assert cfd["dc_power"]["r2"] > 0.90
    assert abs(cfd["dc_power"]["mbe_pct"]) < 8.0
    assert cfd["ac_power"]["r2"] > 0.90
