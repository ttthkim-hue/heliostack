"""Satellite DEM horizon ray-casting (Copernicus DEM via Open-Meteo, EU PVGIS, ESRI ASCII)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import requests

PVGIS_HORIZON_URL = "https://re.jrc.ec.europa.eu/api/v5_3/printhorizon"
OPEN_METEO_ELEV_URL = "https://api.open-meteo.com/v1/elevation"
_EARTH_RADIUS_M = 6371000.0
_REFRACTION_EFF_RADIUS_M = _EARTH_RADIUS_M / (1.0 - 0.13)


def _destination_lat_lon(lat_deg: float, lon_deg: float, bearing_deg: float, dist_m: float) -> tuple[float, float]:
    """Spherical Earth destination point given bearing (0=N, 90=E) and distance in meters."""
    phi1 = math.radians(lat_deg)
    lam1 = math.radians(lon_deg)
    theta = math.radians(bearing_deg)
    delta = dist_m / _EARTH_RADIUS_M

    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi2)))
    y = math.sin(theta) * math.sin(delta) * math.cos(phi1)
    x = math.cos(delta) - math.sin(phi1) * math.sin(phi2)
    lam2 = lam1 + math.atan2(y, x)
    lon2 = ((math.degrees(lam2) + 540.0) % 360.0) - 180.0
    return math.degrees(phi2), lon2


def parse_pvgis_horizon_payload(payload: dict[str, Any]) -> list[float]:
    """Parse EU PVGIS printhorizon JSON and resample onto 36 compass bins (0..350 deg, 0=N)."""
    profile = payload.get("outputs", {}).get("horizon_profile")
    if not isinstance(profile, list) or len(profile) < 12:
        raise ValueError("Invalid PVGIS printhorizon payload: missing horizon_profile.")

    pairs = []
    for row in profile:
        # PVGIS A: 0=S, -90=E, +90=W, -180=N -> Compass az: 0=N, 90=E, 180=S, 270=W
        az_compass = (float(row["A"]) + 180.0) % 360.0
        elev = max(0.0, float(row["H_hor"]))
        pairs.append((az_compass, elev))
    pairs.sort(key=lambda item: item[0])

    az = np.array([p[0] for p in pairs], dtype=float)
    hv = np.array([p[1] for p in pairs], dtype=float)
    az_wrap = np.concatenate(([az[-1] - 360.0], az, [az[0] + 360.0]))
    hv_wrap = np.concatenate(([hv[-1]], hv, [hv[0]]))
    target_bins = np.arange(0.0, 360.0, 10.0)
    return [round(float(val), 2) for val in np.interp(target_bins, az_wrap, hv_wrap)]


def fetch_pvgis_horizon(
    latitude: float,
    longitude: float,
    cache_dir: Path | None = None,
    timeout_s: int = 30,
) -> tuple[list[float], dict[str, Any]]:
    """Fetch (or read cache of) official EU PVGIS DEM-derived terrain horizon profile."""
    cache_file = (
        cache_dir / f"pvgis_horizon_{latitude:.4f}_{longitude:.4f}.json" if cache_dir else None
    )
    if cache_file and cache_file.is_file():
        raw_bytes = cache_file.read_bytes()
        cache_hit = True
    else:
        resp = requests.get(
            PVGIS_HORIZON_URL,
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
    bins = parse_pvgis_horizon_payload(payload)
    meta = {
        "source": "EU_JRC_PVGIS_v5_3_Horizon",
        "horizon_db": payload.get("inputs", {}).get("location", {}).get("horizon_db", "DEM-calculated"),
        "site_elevation_m": payload.get("inputs", {}).get("location", {}).get("elevation"),
        "payload_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "cache_hit": cache_hit,
    }
    return bins, meta


def fetch_copernicus_dem_horizon(
    latitude: float,
    longitude: float,
    cache_dir: Path | None = None,
    n_azimuths: int = 36,
    max_radius_m: float = 20000.0,
    n_rings: int = 10,
    timeout_s: int = 30,
) -> tuple[list[float], dict[str, Any]]:
    """Ray-cast terrain horizon using Copernicus DEM elevations via Open-Meteo Elevation API."""
    if n_azimuths != 36:
        raise ValueError("n_azimuths must be 36 to match 10-degree horizon bins.")

    cache_file = (
        cache_dir / f"copernicus_horizon_{latitude:.4f}_{longitude:.4f}.json" if cache_dir else None
    )
    if cache_file and cache_file.is_file():
        raw_bytes = cache_file.read_bytes()
        grid_data = json.loads(raw_bytes.decode("utf-8"))
        cache_hit = True
    else:
        azimuths = [float(i * 10) for i in range(n_azimuths)]
        distances = [round(float(d), 1) for d in np.geomspace(300.0, max_radius_m, n_rings)]
        pts: list[tuple[float, float]] = [(latitude, longitude)]
        for az in azimuths:
            for dist in distances:
                pts.append(_destination_lat_lon(latitude, longitude, az, dist))

        elevations: list[float] = []
        chunk_size = 80
        for start in range(0, len(pts), chunk_size):
            batch = pts[start : start + chunk_size]
            resp = requests.get(
                OPEN_METEO_ELEV_URL,
                params={
                    "latitude": ",".join(f"{p[0]:.5f}" for p in batch),
                    "longitude": ",".join(f"{p[1]:.5f}" for p in batch),
                },
                timeout=timeout_s,
            )
            resp.raise_for_status()
            body = resp.json()
            batch_elev = body.get("elevation")
            if not isinstance(batch_elev, list) or len(batch_elev) != len(batch):
                raise RuntimeError(f"Unexpected elevation API response length: {body!r}")
            elevations.extend(float(v) for v in batch_elev)

        site_elev = elevations[0]
        ring_elevs = [
            elevations[1 + i * n_rings : 1 + (i + 1) * n_rings] for i in range(n_azimuths)
        ]
        grid_data = {
            "source": "Copernicus_DEM_via_OpenMeteo",
            "latitude": latitude,
            "longitude": longitude,
            "site_elevation_m": site_elev,
            "azimuths_deg": azimuths,
            "distances_m": distances,
            "ring_elevations_m": ring_elevs,
        }
        raw_bytes = json.dumps(grid_data, indent=2, sort_keys=True).encode("utf-8")
        cache_hit = False
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(raw_bytes)

    z0 = float(grid_data["site_elevation_m"])
    dists = np.asarray(grid_data["distances_m"], dtype=float)
    horizon_bins: list[float] = []
    for row_elevs in grid_data["ring_elevations_m"]:
        z_arr = np.asarray(row_elevs, dtype=float)
        # Earth curvature + standard atmospheric refraction drop: r^2 / (2 * R_eff)
        dz = z_arr - z0 - (dists * dists) / (2.0 * _REFRACTION_EFF_RADIUS_M)
        angles_deg = np.degrees(np.arctan2(dz, dists))
        horizon_bins.append(round(float(max(0.0, float(np.max(angles_deg)))), 2))

    meta = {
        "source": grid_data["source"],
        "site_elevation_m": z0,
        "max_radius_m": float(dists[-1]),
        "n_rings": len(dists),
        "payload_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "cache_hit": cache_hit,
    }
    return horizon_bins, meta


def load_ascii_dem_horizon(
    asc_path: Path,
    site_x: float,
    site_y: float,
    n_azimuths: int = 36,
    max_radius_m: float = 15000.0,
) -> list[float]:
    """Extract 36-azimuth horizon angles from an offline ESRI ASCII Grid (.asc) DEM tile."""
    if n_azimuths != 36:
        raise ValueError("n_azimuths must be 36.")
    lines = asc_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 7:
        raise ValueError(f"Invalid ESRI ASCII DEM file: {asc_path}")

    header: dict[str, float] = {}
    data_start = 0
    for idx, line in enumerate(lines[:10]):
        parts = line.strip().split()
        if len(parts) == 2 and parts[0].lower() in {
            "ncols",
            "nrows",
            "xllcorner",
            "yllcorner",
            "xllcenter",
            "yllcenter",
            "cellsize",
            "nodata_value",
        }:
            header[parts[0].lower()] = float(parts[1])
            data_start = idx + 1
        else:
            break

    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    cell = float(header["cellsize"])
    xll = header.get("xllcorner", header.get("xllcenter", 0.0) - 0.5 * cell)
    yll = header.get("yllcorner", header.get("yllcenter", 0.0) - 0.5 * cell)
    nodata = header.get("nodata_value", -9999.0)

    grid_rows = []
    for row_txt in lines[data_start : data_start + nrows]:
        vals = [float(tok) for tok in row_txt.split()]
        if len(vals) != ncols:
            raise ValueError(f"Row width mismatch in DEM: expected {ncols}, got {len(vals)}.")
        grid_rows.append(vals)
    if len(grid_rows) != nrows:
        raise ValueError(f"Row count mismatch in DEM: expected {nrows}, got {len(grid_rows)}.")
    z_grid = np.asarray(grid_rows, dtype=float)

    def _sample(x_coord: float, y_coord: float) -> float:
        col = int(round((x_coord - xll) / cell - 0.5))
        # ESRI ASCII row 0 is the TOP (northmost) row
        row_from_bottom = int(round((y_coord - yll) / cell - 0.5))
        row = (nrows - 1) - row_from_bottom
        if not (0 <= row < nrows and 0 <= col < ncols):
            return nodata
        return float(z_grid[row, col])

    z0 = _sample(site_x, site_y)
    if z0 == nodata:
        raise ValueError("Site coordinates lie outside valid DEM cells.")

    steps = np.arange(cell, max_radius_m + 0.5 * cell, cell)
    horizon_bins: list[float] = []
    for i in range(n_azimuths):
        az_rad = math.radians(i * 10.0)
        dx = math.sin(az_rad)
        dy = math.cos(az_rad)
        max_ang = 0.0
        for r in steps:
            z_pt = _sample(site_x + r * dx, site_y + r * dy)
            if z_pt == nodata:
                continue
            dz = z_pt - z0 - (r * r) / (2.0 * _REFRACTION_EFF_RADIUS_M)
            ang = math.degrees(math.atan2(dz, r))
            if ang > max_ang:
                max_ang = ang
        horizon_bins.append(round(max_ang, 2))
    return horizon_bins


def compare_horizon_profiles(h_copernicus: list[float], h_pvgis: list[float]) -> dict[str, float]:
    """Compare two 36-bin horizon profiles and return MAE, RMSE, max absolute diff, and means."""
    a = np.asarray(h_copernicus, dtype=float)
    b = np.asarray(h_pvgis, dtype=float)
    if a.shape != (36,) or b.shape != (36,):
        raise ValueError("Both horizon profiles must have length 36.")
    diff = a - b
    return {
        "mae_deg": round(float(np.mean(np.abs(diff))), 2),
        "rmse_deg": round(float(np.sqrt(np.mean(diff * diff))), 2),
        "max_abs_diff_deg": round(float(np.max(np.abs(diff))), 2),
        "mean_copernicus_deg": round(float(np.mean(a)), 2),
        "mean_pvgis_deg": round(float(np.mean(b)), 2),
    }
