"""Offline tests for Copernicus DEM vs EU PVGIS horizon ray-casting and ESRI ASCII DEMs."""

from __future__ import annotations

from pathlib import Path

import pytest

from heliostack.cli import main as cli_main
from heliostack.terrain import (
    _destination_lat_lon,
    compare_horizon_profiles,
    fetch_copernicus_dem_horizon,
    fetch_pvgis_horizon,
    load_ascii_dem_horizon,
    parse_pvgis_horizon_payload,
)
from heliostack.weather import fetch_pvgis_tmy

WEATHER_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "weather"


def test_cached_innsbruck_copernicus_matches_pvgis_horizon(tmp_path: Path) -> None:
    h_cop, meta_cop = fetch_copernicus_dem_horizon(47.2692, 11.4041, cache_dir=WEATHER_DIR)
    h_pvg, meta_pvg = fetch_pvgis_horizon(47.2692, 11.4041, cache_dir=WEATHER_DIR)
    assert meta_cop["cache_hit"] is True
    assert meta_pvg["cache_hit"] is True
    assert len(h_cop) == 36
    assert len(h_pvg) == 36

    cmp_stats = compare_horizon_profiles(h_cop, h_pvg)
    assert cmp_stats["mae_deg"] < 3.0
    assert cmp_stats["mean_copernicus_deg"] > 5.0

    # Cached horizon-free Alpine TMY also reports provenance cleanly
    df_nohor, prov_nohor = fetch_pvgis_tmy(47.2692, 11.4041, cache_dir=WEATHER_DIR, use_horizon=False)
    assert len(df_nohor) == 8760
    assert prov_nohor["use_horizon"] is False
    assert prov_nohor["cache_hit"] is True

    # Spherical geodesic projection & horizon validation helpers
    lat_n, _ = _destination_lat_lon(47.0, 11.0, 0.0, 10000.0)
    assert lat_n > 47.05
    with pytest.raises(ValueError, match="horizon_profile"):
        parse_pvgis_horizon_payload({})
    with pytest.raises(ValueError, match="n_azimuths"):
        fetch_copernicus_dem_horizon(47.2692, 11.4041, n_azimuths=18)

    # CLI horizon JSON + text output + missing serve directory
    assert cli_main(["horizon", "--lat", "47.2692", "--lon", "11.4041", "--cache-dir", str(WEATHER_DIR), "--json"]) == 0
    assert cli_main(["horizon", "--lat", "47.2692", "--lon", "11.4041", "--cache-dir", str(WEATHER_DIR)]) == 0
    assert cli_main(["serve", "--dir", str(tmp_path / "missing_docs")]) == 2


def test_ascii_dem_horizon_detects_synthetic_south_ridge(tmp_path: Path) -> None:
    # 21x21 grid at 100 m spacing (0..2100 m E, 0..2100 m N), site at (1050, 1050) elevation 100 m.
    # Place a ridge at the southernmost 3 rows (y=0..300 m, distance ~800-1000 m south) with elevation 600 m.
    nrows, ncols = 21, 21
    rows_txt = []
    for r in range(nrows):
        # ESRI row 0 is northmost (y = 2050 m); row 18..20 is southmost (y = 50..250 m)
        is_south_ridge = r >= 18
        z_val = "600.0" if is_south_ridge else "100.0"
        rows_txt.append(" ".join([z_val] * ncols))

    asc = tmp_path / "ridge.asc"
    asc.write_text(
        "\n".join(
            [
                f"ncols {ncols}",
                f"nrows {nrows}",
                "xllcorner 0.0",
                "yllcorner 0.0",
                "cellsize 100.0",
                "NODATA_value -9999",
                *rows_txt,
            ]
        ),
        encoding="utf-8",
    )

    bins = load_ascii_dem_horizon(asc, site_x=1050.0, site_y=1050.0, max_radius_m=1500.0)
    assert len(bins) == 36
    assert bins[0] == 0.0  # Due North is flat
    assert bins[18] > 25.0  # Due South (az 180) blocked by the ~800 m distant 500 m tall ridge

    with pytest.raises(ValueError, match="36"):
        load_ascii_dem_horizon(asc, 1050.0, 1050.0, n_azimuths=18)
