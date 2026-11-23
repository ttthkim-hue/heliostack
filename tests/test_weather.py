"""Offline tests for PVGIS weather parsing, azimuth conversion, caching, and error guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from heliostack.weather import (
    fetch_pvgis_pvcalc,
    fetch_pvgis_tmy,
    load_cached_tmy,
    pvlib_azimuth_to_pvgis_aspect,
    save_tmy_csv,
)

WEATHER_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "weather"


def test_azimuth_to_pvgis_aspect_conversion() -> None:
    assert pvlib_azimuth_to_pvgis_aspect(180.0) == 0.0
    assert pvlib_azimuth_to_pvgis_aspect(90.0) == -90.0
    assert pvlib_azimuth_to_pvgis_aspect(270.0) == 90.0


def test_load_cached_pvgis_json_csv_and_save_roundtrip(tmp_path: Path) -> None:
    df_json, prov_json = load_cached_tmy(WEATHER_DIR / "pvgis_tmy_52.3700_4.9000.json")
    assert len(df_json) == 8760
    assert prov_json["source"] == "EU_JRC_PVGIS_v5_3_TMY"
    assert prov_json["cache_hit"] is True

    df_csv, prov_csv = load_cached_tmy(WEATHER_DIR / "amsterdam_pvgis_tmy_2023.csv")
    assert len(df_csv) == 8760
    assert prov_csv["cache_hit"] is True

    roundtrip = tmp_path / "rt.csv"
    save_tmy_csv(df_json, roundtrip)
    df_rt, _ = load_cached_tmy(roundtrip)
    assert len(df_rt) == 8760
    assert abs(float(df_rt["ghi"].sum() - df_json["ghi"].sum())) < 1e-3


def test_fetch_pvgis_cache_hits() -> None:
    df_tmy, prov_tmy = fetch_pvgis_tmy(52.37, 4.90, cache_dir=WEATHER_DIR)
    assert len(df_tmy) == 8760
    assert prov_tmy["cache_hit"] is True

    pvcalc = fetch_pvgis_pvcalc(52.37, 4.90, 100.0, 10.0, 35.0, 180.0, cache_dir=WEATHER_DIR)
    assert pvcalc["specific_yield_kwh_kwp"] > 900.0
    assert len(pvcalc["monthly_e_m_kwh"]) == 12


def test_reject_malformed_weather_csvs(tmp_path: Path) -> None:
    missing_col = tmp_path / "missing.csv"
    missing_col.write_text("time_utc,ghi\n2023-01-01 00:00:00+00:00,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        load_cached_tmy(missing_col)

    df_csv, _ = load_cached_tmy(WEATHER_DIR / "amsterdam_pvgis_tmy_2023.csv")
    short = tmp_path / "short.csv"
    df_csv.iloc[:100].to_csv(short, index=True, index_label="time_utc")
    with pytest.raises(ValueError, match="8760"):
        load_cached_tmy(short)

    bad_nan = df_csv.copy()
    bad_nan.iloc[5, 0] = float("nan")
    nan_path = tmp_path / "nan.csv"
    save_tmy_csv(bad_nan, nan_path)
    with pytest.raises(ValueError, match="NaN"):
        load_cached_tmy(nan_path)
