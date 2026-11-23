"""Physical geometry tests for 3D ray-box near-shading, horizon blocking, and inter-row shade."""

from __future__ import annotations

import numpy as np

from heliostack.models import ObstacleBox3D
from heliostack.shading import (
    compute_horizon_elevation,
    compute_interrow_shed_shading,
    compute_near_shading,
)


def test_zero_obstacles_zero_beam_shade_low_gcr() -> None:
    el = np.array([15.0, 45.0, 75.0, -10.0])
    az = np.array([120.0, 180.0, 180.0, 270.0])
    res = compute_near_shading(
        solar_elevation_deg=el,
        solar_azimuth_deg=az,
        surface_tilt_deg=30.0,
        surface_azimuth_deg=180.0,
        array_height_m=1.2,
        row_length_m=10.0,
        row_depth_m=2.0,
        gcr=0.20,
        obstacles=[],
    )
    assert res.obstacle_beam_loss_pct == 0.0
    assert res.horizon_beam_loss_pct == 0.0
    assert res.beam_shaded_fraction[-1] == 0.0
    assert 0.85 <= res.diffuse_svf <= 1.0


def test_large_south_wall_blocks_sun_and_scales_monotonically() -> None:
    el = np.array([25.0, 40.0])
    az = np.array([180.0, 180.0])
    short_wall = ObstacleBox3D("Short", center_east_m=0.0, center_north_m=-6.0, width_east_m=40.0, depth_north_m=2.0, height_m=3.0)
    tall_wall = ObstacleBox3D("Tall", center_east_m=0.0, center_north_m=-6.0, width_east_m=40.0, depth_north_m=2.0, height_m=20.0)

    r_short = compute_near_shading(el, az, 30.0, 180.0, 1.0, 10.0, 2.0, 0.30, [short_wall])
    r_tall = compute_near_shading(el, az, 30.0, 180.0, 1.0, 10.0, 2.0, 0.30, [tall_wall])
    assert r_tall.obstacle_beam_loss_pct > r_short.obstacle_beam_loss_pct > 0.0
    assert r_tall.beam_shaded_fraction[0] == 1.0
    assert r_tall.diffuse_svf < r_short.diffuse_svf


def test_interrow_shed_shading_and_horizon_mask() -> None:
    el = np.array([5.0, 60.0])
    az = np.array([180.0, 180.0])
    shed = compute_interrow_shed_shading(el, az, surface_tilt_deg=35.0, surface_azimuth_deg=180.0, gcr=0.65)
    assert shed[0] > 0.5
    assert shed[1] == 0.0

    horizon = [15.0] * 36
    h_interp = compute_horizon_elevation(np.array([45.0, 185.0]), horizon)
    assert np.allclose(h_interp, 15.0)
    res_h = compute_near_shading(el, az, 35.0, 180.0, 1.2, 10.0, 2.0, 0.25, [], horizon_elev_deg_36=horizon)
    assert res_h.beam_shaded_fraction[0] == 1.0
    assert res_h.horizon_beam_loss_pct > 0.0
