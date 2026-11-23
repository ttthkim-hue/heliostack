"""Vectorized 3D ray-box near-shading, horizon blocking, diffuse SVF, and shed self-shading."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from heliostack.models import ObstacleBox3D


@dataclass(slots=True)
class ShadingResult:
    """Hourly and annual optical shading breakdown."""

    beam_shaded_fraction: np.ndarray  # [0, 1], shape (T,)
    diffuse_svf: float  # [0, 1]
    rear_view_factor: float  # [0, 1]
    obstacle_beam_loss_pct: float
    shed_beam_loss_pct: float
    horizon_beam_loss_pct: float


def _array_basis(tilt_deg: float, azimuth_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Orthonormal basis (u_row_right, u_upslope, n_normal) in ENU coordinates."""
    t = math.radians(tilt_deg)
    az = math.radians(azimuth_deg)
    u_row = np.array([-math.cos(az), math.sin(az), 0.0], dtype=float)
    u_up = np.array([-math.cos(t) * math.sin(az), -math.cos(t) * math.cos(az), math.sin(t)], dtype=float)
    n_vec = np.array([math.sin(t) * math.sin(az), math.sin(t) * math.cos(az), math.cos(t)], dtype=float)
    return u_row, u_up, n_vec


def _fibonacci_hemisphere_dirs(n_dirs: int = 256) -> np.ndarray:
    """Deterministic uniform unit vectors over the upper hemisphere (z > 0)."""
    idx = np.arange(n_dirs, dtype=float) + 0.5
    z = idx / n_dirs
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    phi = np.pi * (3.0 - math.sqrt(5.0)) * idx
    return np.column_stack((r * np.cos(phi), r * np.sin(phi), z))


def _ray_box_hits(
    origins: np.ndarray,  # (P, 3)
    dirs: np.ndarray,  # (R, 3)
    bmin: tuple[float, float, float],
    bmax: tuple[float, float, float],
) -> np.ndarray:
    """Vectorized slab intersection returning boolean hit matrix of shape (R, P)."""
    nonzero = np.abs(dirs) > 1e-9
    safe_dirs = np.where(nonzero, dirs, 1.0)
    inv_d = np.where(nonzero, 1.0 / safe_dirs, 0.0)
    bmin_arr = np.asarray(bmin, dtype=float)[None, None, :]
    bmax_arr = np.asarray(bmax, dtype=float)[None, None, :]
    raw_t1 = (bmin_arr - origins[None, :, :]) * inv_d[:, None, :]
    raw_t2 = (bmax_arr - origins[None, :, :]) * inv_d[:, None, :]
    t1 = np.where(nonzero[:, None, :], raw_t1, -1e12)
    t2 = np.where(nonzero[:, None, :], raw_t2, 1e12)
    parallel_out = (~nonzero[:, None, :]) & (
        (origins[None, :, :] < bmin_arr) | (origins[None, :, :] > bmax_arr)
    )
    tmin = np.maximum(np.minimum(t1, t2), -1e12)
    tmax = np.minimum(np.maximum(t1, t2), 1e12)
    t_enter = np.max(tmin, axis=2)
    t_exit = np.min(tmax, axis=2)
    miss_parallel = np.any(parallel_out, axis=2)
    return (~miss_parallel) & (t_exit >= np.maximum(t_enter, 1e-4))


def compute_horizon_elevation(solar_azimuth_deg: np.ndarray, horizon_elev_deg_36: list[float]) -> np.ndarray:
    """Interpolate 36-bin (10-deg step) horizon elevation profile at hourly solar azimuths."""
    profile = np.asarray(horizon_elev_deg_36, dtype=float)
    if profile.shape != (36,):
        raise ValueError("horizon_elev_deg_36 must have exactly 36 entries.")
    angles = np.arange(0.0, 360.0, 10.0)
    angles_wrap = np.append(angles, 360.0)
    prof_wrap = np.append(profile, profile[0])
    return np.interp(np.mod(solar_azimuth_deg, 360.0), angles_wrap, prof_wrap)


def compute_interrow_shed_shading(
    solar_elevation_deg: np.ndarray,
    solar_azimuth_deg: np.ndarray,
    surface_tilt_deg: float,
    surface_azimuth_deg: float,
    gcr: float,
) -> np.ndarray:
    """Exact closed-form geometric inter-row beam shading fraction for parallel collector sheds."""
    n = len(solar_elevation_deg)
    if gcr <= 0.05 or surface_tilt_deg <= 0.5:
        return np.zeros(n, dtype=float)
    el = np.radians(np.clip(solar_elevation_deg, 0.0, 90.0))
    az_diff = np.radians(solar_azimuth_deg - surface_azimuth_deg)
    sx = np.cos(el) * np.cos(az_diff)
    sz = np.sin(el)
    tilt = math.radians(surface_tilt_deg)
    active = (solar_elevation_deg > 0.5) & (sx > 1e-6) & (sz > 1e-6)
    shaded = np.zeros(n, dtype=float)
    k = np.zeros(n, dtype=float)
    k[active] = sx[active] / sz[active]
    denom = gcr * (math.cos(tilt) + k[active] * math.sin(tilt))
    shaded[active] = np.clip(1.0 - 1.0 / np.maximum(denom, 1e-6), 0.0, 1.0)
    return shaded


def compute_near_shading(
    solar_elevation_deg: np.ndarray,
    solar_azimuth_deg: np.ndarray,
    surface_tilt_deg: float,
    surface_azimuth_deg: float,
    array_height_m: float,
    row_length_m: float,
    row_depth_m: float,
    gcr: float,
    obstacles: list[ObstacleBox3D],
    horizon_elev_deg_36: list[float] | None = None,
    beam_irradiance_weight: np.ndarray | None = None,
    n_u: int = 5,
    n_v: int = 4,
) -> ShadingResult:
    """Compute hourly 3D obstacle beam shading, horizon mask, inter-row shade, and diffuse SVF."""
    n_hrs = len(solar_elevation_deg)
    u_row, u_up, n_vec = _array_basis(surface_tilt_deg, surface_azimuth_deg)
    us = np.linspace(-0.45 * row_length_m, 0.45 * row_length_m, n_u)
    vs = np.linspace(-0.45 * row_depth_m, 0.45 * row_depth_m, n_v)
    center = np.array([0.0, 0.0, array_height_m], dtype=float)
    pts = np.array([center + u * u_row + v * u_up for u in us for v in vs], dtype=float)

    # 1. 3D Obstacle beam ray-casting over sunlit hours
    sunlit = solar_elevation_deg > 0.5
    obs_shaded = np.zeros(n_hrs, dtype=float)
    if obstacles and np.any(sunlit):
        el_rad = np.radians(solar_elevation_deg[sunlit])
        az_rad = np.radians(solar_azimuth_deg[sunlit])
        sun_dirs = np.column_stack(
            (np.cos(el_rad) * np.sin(az_rad), np.cos(el_rad) * np.cos(az_rad), np.sin(el_rad))
        )
        # Only trace hours where sun is in front of collector plane
        in_front = (sun_dirs @ n_vec) > 0.0
        blocked_pts = np.zeros((int(np.sum(sunlit)), len(pts)), dtype=bool)
        if np.any(in_front):
            dirs_active = sun_dirs[in_front]
            hit_any = np.zeros((len(dirs_active), len(pts)), dtype=bool)
            for box in obstacles:
                bmin, bmax = box.bounds()
                hit_any |= _ray_box_hits(pts, dirs_active, bmin, bmax)
            blocked_pts[in_front] = hit_any
        obs_shaded[sunlit] = blocked_pts.mean(axis=1)

    # 2. 36-azimuth horizon blocking
    hor_shaded = np.zeros(n_hrs, dtype=float)
    if horizon_elev_deg_36 is not None:
        hor_elev = compute_horizon_elevation(solar_azimuth_deg, horizon_elev_deg_36)
        hor_shaded = ((solar_elevation_deg > 0.0) & (solar_elevation_deg < hor_elev)).astype(float)

    # 3. Inter-row geometric shed self-shading
    shed_shaded = compute_interrow_shed_shading(
        solar_elevation_deg, solar_azimuth_deg, surface_tilt_deg, surface_azimuth_deg, gcr
    )

    # Combined conservative optical beam loss (1 - unshaded product over independent mechanisms, capped <= 1)
    combined = 1.0 - (1.0 - obs_shaded) * (1.0 - hor_shaded) * (1.0 - shed_shaded)
    combined = np.clip(combined, 0.0, 1.0)

    # 4. Diffuse Sky-View Factor (SVF) via cosine-weighted hemisphere integration
    hemi_dirs = _fibonacci_hemisphere_dirs(256)
    cos_inc = np.maximum(0.0, hemi_dirs @ n_vec)
    tilt_rad = math.radians(surface_tilt_deg)
    # Standard collector sky view baseline (1 + cos(beta)) / 2 discounted by inter-row view obstruction & 3D boxes
    row_sky_factor = max(0.35, 1.0 - 0.18 * max(0.0, gcr - 0.30) * math.sin(tilt_rad))
    svf_base = 0.5 * (1.0 + math.cos(tilt_rad)) * row_sky_factor
    if obstacles or horizon_elev_deg_36 is not None:
        above_plane = cos_inc > 1e-4
        blocked_sky = np.zeros(len(hemi_dirs), dtype=float)
        if np.any(above_plane):
            dirs_sky = hemi_dirs[above_plane]
            blocked_frac = np.zeros(len(dirs_sky), dtype=float)
            if horizon_elev_deg_36 is not None:
                hemi_az = np.degrees(np.arctan2(dirs_sky[:, 0], dirs_sky[:, 1])) % 360.0
                hemi_el = np.degrees(np.arcsin(np.clip(dirs_sky[:, 2], 0.0, 1.0)))
                hor_blocked = hemi_el < compute_horizon_elevation(hemi_az, horizon_elev_deg_36)
                blocked_frac = np.where(hor_blocked, 1.0, blocked_frac)
            if obstacles:
                hit_sky = np.zeros((len(dirs_sky), len(pts)), dtype=bool)
                for box in obstacles:
                    bmin, bmax = box.bounds()
                    hit_sky |= _ray_box_hits(pts, dirs_sky, bmin, bmax)
                obs_frac = hit_sky.mean(axis=1)
                blocked_frac = 1.0 - (1.0 - blocked_frac) * (1.0 - obs_frac)
            blocked_sky[above_plane] = blocked_frac
        weights = cos_inc / max(1e-9, float(np.sum(cos_inc)))
        obstacle_sky_pass = float(np.sum(weights * (1.0 - blocked_sky)))
    else:
        obstacle_sky_pass = 1.0

    diffuse_svf = float(np.clip(svf_base * obstacle_sky_pass, 0.1, 1.0))
    rear_vf = float(np.clip(0.5 * (1.0 - math.cos(tilt_rad)) + 0.18 * (1.0 - gcr), 0.05, 0.45))

    w = beam_irradiance_weight if beam_irradiance_weight is not None else np.maximum(0.0, np.sin(np.radians(np.maximum(0.0, solar_elevation_deg))))
    w_sum = max(1e-9, float(np.sum(w)))

    return ShadingResult(
        beam_shaded_fraction=combined,
        diffuse_svf=diffuse_svf,
        rear_view_factor=rear_vf,
        obstacle_beam_loss_pct=float(np.sum(obs_shaded * w) / w_sum * 100.0),
        shed_beam_loss_pct=float(np.sum(shed_shaded * w) / w_sum * 100.0),
        horizon_beam_loss_pct=float(np.sum(hor_shaded * w) / w_sum * 100.0),
    )
