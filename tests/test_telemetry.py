"""Offline tests for US DOE / NREL PVDAQ #2107 telemetry loader and field validation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from heliostack.formats import parse_ond, parse_pan
from heliostack.models import SiteConfig
from heliostack.telemetry import (
    evaluate_field_validation,
    fetch_and_prepare_pvdaq_2107_2024,
    load_telemetry_csv,
    run_pv_from_measured_poa,
)

ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_CSV = ROOT / "fixtures" / "telemetry" / "pvdaq_2107_2024_hourly.csv"


def test_load_telemetry_csv_and_missing_column_error(tmp_path: Path) -> None:
    df = load_telemetry_csv(TELEMETRY_CSV)
    assert len(df) == 7286
    for col in ("poa_global", "temp_air", "wind_speed", "wind_direction", "ac_power_kw"):
        assert col in df.columns

    bad_csv = tmp_path / "missing_col.csv"
    df.drop(columns=["wind_direction"]).head(10).to_csv(bad_csv, index_label="time_utc")
    with pytest.raises(ValueError, match="missing columns"):
        load_telemetry_csv(bad_csv)


def test_prepare_pvdaq_hourly_aggregation_offline(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    ts = ["2024-06-21 12:00:00", "2024-06-21 12:15:00", "2024-06-21 12:30:00", "2024-06-21 12:45:00"]
    pd.DataFrame({
        "measured_on": ts,
        "ambient_temperature_o_149575": [77.0] * 4,  # 25.0 C
        "wind_speed_o_149576": [10.0] * 4,  # ~4.47 m/s
        "wind_direction_o_149577": [180.0] * 4,
    }).to_csv(raw / "2107_environment_data_2024.csv", index=False)
    pd.DataFrame({"measured_on": ts, "poa_irradiance_o_149574": [850.0] * 4}).to_csv(
        raw / "2107_irradiance_data_2024.csv", index=False
    )
    pd.DataFrame({"measured_on": ts, "meter_revenue_grade_ac_output_meter_149578": [600.0] * 4}).to_csv(
        raw / "2107_meter_15m_data_2024.csv", index=False
    )
    (raw / "2107_system_metadata.json").write_text('{"system_id": 2107}', encoding="utf-8")

    df_out, meta = fetch_and_prepare_pvdaq_2107_2024(raw, tmp_path / "out.csv")
    assert len(df_out) == 1
    assert df_out["temp_air"].iloc[0] == pytest.approx(25.0, abs=1e-6)
    assert df_out["wind_speed"].iloc[0] == pytest.approx(4.4704, abs=1e-4)
    assert meta["hourly_rows"] == 1


def test_pvdaq_2107_field_validation_parity() -> None:
    df = load_telemetry_csv(TELEMETRY_CSV)
    mod, errs_m = parse_pan(ROOT / "fixtures" / "equipment" / "hyundai_his_m310ti.pan")
    inv, errs_i = parse_ond(ROOT / "fixtures" / "equipment" / "abb_trio_27_6.ond")
    assert mod and not errs_m
    assert inv and not errs_i

    site = SiteConfig(
        site_name="US DOE PVDAQ #2107 Farm Solar Array (Arbuckle, CA)",
        latitude=38.996306,
        longitude=-122.134111,
        elevation_m=10.0,
        surface_tilt_deg=25.0,
        surface_azimuth_deg=180.0,
        dc_kwp=892.8,
        gcr=0.45,
        albedo=0.20,
        soiling_loss_frac=0.025,
        dc_wiring_loss_frac=0.015,
        mismatch_loss_frac=0.015,
        availability_frac=1.0,
        use_3d_shading=False,
    )
    val = evaluate_field_validation(df, site, mod, inv, inverter_count=24, plant_age_years=7.0)
    assert val["valid_operating_hours"] == 3255

    conv = val["models"]["convective_land"]
    open_r = val["models"]["open_rack"]
    assert conv["r2"] > 0.90
    assert abs(conv["mbe_pct"]) < 5.0
    assert conv["nrmse_pct"] < 8.0
    assert conv["rmse_kw"] <= open_r["rmse_kw"]


def test_run_pv_from_measured_poa_zero_at_night() -> None:
    mod, _ = parse_pan(ROOT / "fixtures" / "equipment" / "hyundai_his_m310ti.pan")
    inv, _ = parse_ond(ROOT / "fixtures" / "equipment" / "abb_trio_27_6.ond")
    assert mod and inv

    idx = pd.date_range("2024-06-21T00:00:00Z", periods=3, freq="1h", tz="UTC")
    site = SiteConfig(
        site_name="Unit POA Test",
        latitude=39.0,
        longitude=-122.1,
        elevation_m=10.0,
        surface_tilt_deg=25.0,
        surface_azimuth_deg=180.0,
        dc_kwp=892.8,
    )
    out = run_pv_from_measured_poa(
        times=idx,
        poa_global=pd.Series([0.0, 450.0, 950.0]).to_numpy(),
        temp_air=pd.Series([15.0, 22.0, 30.0]).to_numpy(),
        wind_speed=pd.Series([2.0, 3.0, 4.0]).to_numpy(),
        wind_direction=pd.Series([180.0, 180.0, 90.0]).to_numpy(),
        site=site,
        module=mod,
        inverter=inv,
        dc_aging_factor=0.965,
        inverter_count_override=24,
    )
    assert out["ac_net_kw"][0] == 0.0
    assert 0.0 < out["ac_net_kw"][1] < out["ac_net_kw"][2] <= out["inv_max_total_kw"]
