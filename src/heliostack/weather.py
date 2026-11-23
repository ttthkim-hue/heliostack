"""European Commission PVGIS v5.3 TMY & official PVcalc reference weather client."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

PVGIS_BASE_URL = "https://re.jrc.ec.europa.eu/api/v5_3"
REQUIRED_WEATHER_COLS = (
    "ghi",
    "dni",
    "dhi",
    "temp_air",
    "wind_speed",
    "wind_direction",
    "rh",
    "pressure",
)


def pvlib_azimuth_to_pvgis_aspect(surface_azimuth_deg: float) -> float:
    """Convert pvlib azimuth (0=N, 90=E, 180=S, 270=W) to PVGIS aspect (0=S, -90=E, +90=W)."""
    return ((surface_azimuth_deg % 360.0) - 180.0)


def parse_pvgis_tmy_payload(payload: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse raw PVGIS v5.3 TMY JSON into a monotonic 8,760-hr UTC DataFrame."""
    outputs = payload.get("outputs", {})
    rows = outputs.get("tmy_hourly")
    if not isinstance(rows, list) or len(rows) != 8760:
        raise ValueError(f"Expected 8760 hourly PVGIS TMY records, got {len(rows) if rows else 0}.")

    records: list[dict[str, float]] = []
    timestamps: list[pd.Timestamp] = []
    for row in rows:
        t_str = str(row["time(UTC)"])  # e.g. 20210101:0000
        mm_dd = t_str[4:8]
        hh_mi = t_str[9:13]
        ts = pd.Timestamp(f"2023-{mm_dd[:2]}-{mm_dd[2:]} {hh_mi[:2]}:{hh_mi[2:]}:00", tz="UTC")
        timestamps.append(ts)
        records.append(
            {
                "ghi": float(row["G(h)"]),
                "dni": float(row["Gb(n)"]),
                "dhi": float(row["Gd(h)"]),
                "temp_air": float(row["T2m"]),
                "wind_speed": float(row["WS10m"]),
                "wind_direction": float(row.get("WD10m", 180.0)),
                "rh": float(row.get("RH", 60.0)),
                "pressure": float(row.get("SP", 101325.0)),
            }
        )

    df = pd.DataFrame(records, index=pd.DatetimeIndex(timestamps, name="time_utc")).sort_index()
    loc_in = payload.get("inputs", {}).get("location", {})
    meteo_in = payload.get("inputs", {}).get("meteo_data", {})
    provenance = {
        "source": "EU_JRC_PVGIS_v5_3_TMY",
        "radiation_db": meteo_in.get("radiation_db", "unknown"),
        "meteo_db": meteo_in.get("meteo_db", "unknown"),
        "year_min": meteo_in.get("year_min"),
        "year_max": meteo_in.get("year_max"),
        "elevation_m": loc_in.get("elevation"),
        "months_selected": outputs.get("months_selected", []),
    }
    return df, provenance


def fetch_pvgis_tmy(
    latitude: float,
    longitude: float,
    cache_dir: Path | None = None,
    timeout_s: int = 30,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch (or read deterministic cache of) real 8,760-hr PVGIS v5.3 TMY data."""
    cache_file = (
        cache_dir / f"pvgis_tmy_{latitude:.4f}_{longitude:.4f}.json" if cache_dir else None
    )
    if cache_file and cache_file.is_file():
        raw_bytes = cache_file.read_bytes()
        cache_hit = True
    else:
        url = f"{PVGIS_BASE_URL}/tmy"
        resp = requests.get(
            url,
            params={"lat": latitude, "lon": longitude, "outputformat": "json"},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        raw_bytes = resp.content
        cache_hit = False
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(raw_bytes)

    payload = json.loads(raw_bytes.decode("utf-8"))
    df, prov = parse_pvgis_tmy_payload(payload)
    prov["payload_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
    prov["cache_hit"] = cache_hit
    return df, prov


def fetch_pvgis_pvcalc(
    latitude: float,
    longitude: float,
    peakpower_kw: float,
    loss_pct: float,
    tilt_deg: float,
    surface_azimuth_deg: float,
    cache_dir: Path | None = None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Fetch official EU PVGIS v5.3 PVcalc annual & monthly yield reference."""
    aspect = pvlib_azimuth_to_pvgis_aspect(surface_azimuth_deg)
    cache_file = (
        cache_dir / f"pvgis_pvcalc_{latitude:.4f}_{longitude:.4f}_{tilt_deg:.1f}_{aspect:.1f}.json"
        if cache_dir
        else None
    )
    if cache_file and cache_file.is_file():
        raw_bytes = cache_file.read_bytes()
    else:
        url = f"{PVGIS_BASE_URL}/PVcalc"
        resp = requests.get(
            url,
            params={
                "lat": latitude,
                "lon": longitude,
                "peakpower": peakpower_kw,
                "loss": loss_pct,
                "angle": tilt_deg,
                "aspect": aspect,
                "outputformat": "json",
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
        raw_bytes = resp.content
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(raw_bytes)

    payload = json.loads(raw_bytes.decode("utf-8"))
    fixed = payload["outputs"]["totals"]["fixed"]
    months = payload["outputs"]["monthly"]["fixed"]
    return {
        "e_y_kwh": float(fixed["E_y"]),
        "specific_yield_kwh_kwp": float(fixed["E_y"]) / peakpower_kw,
        "h_i_y_kwh_m2": float(fixed["H(i)_y"]),
        "monthly_e_m_kwh": [float(m["E_m"]) for m in months],
        "radiation_db": payload.get("inputs", {}).get("meteo_data", {}).get("radiation_db", "unknown"),
        "payload_sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }


def save_tmy_csv(df: pd.DataFrame, path: Path) -> None:
    """Save normalized 8,760-hr TMY DataFrame cleanly as UTF-8 CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=True, index_label="time_utc")


def load_cached_tmy(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load an offline CSV or PVGIS JSON TMY file strictly with SHA-256 provenance."""
    raw_bytes = path.read_bytes()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    if path.suffix.lower() == ".json":
        payload = json.loads(raw_bytes.decode("utf-8"))
        df, prov = parse_pvgis_tmy_payload(payload)
        prov["payload_sha256"] = sha
        prov["cache_hit"] = True
        return df, prov

    df = pd.read_csv(path, parse_dates=["time_utc"]).set_index("time_utc")
    missing = [col for col in REQUIRED_WEATHER_COLS if col not in df.columns]
    if missing:
        raise ValueError(f"Weather CSV missing required columns: {missing}")
    if len(df) != 8760:
        raise ValueError(f"Expected 8760 hourly rows in {path}, got {len(df)}.")
    if df.isna().any().any():
        raise ValueError(f"Weather CSV contains NaN entries in {path}.")
    return df, {"source": f"OFFLINE_CSV:{path.name}", "payload_sha256": sha, "cache_hit": True}
