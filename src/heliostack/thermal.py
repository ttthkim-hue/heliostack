"""CFD-informed land convective and Floating-PV water-coupled thermal models."""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pvlib

from heliostack.models import SiteConfig

PACKAGE_CFD_SURROGATE_PATH = (
    Path(__file__).resolve().parent / "data" / "openfoam14_pv_thermal_surrogate.json"
)
DEFAULT_CFD_SURROGATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "thermal"
    / "openfoam14_pv_thermal_surrogate.json"
)


@functools.lru_cache(maxsize=4)
def _read_surrogate_cached(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(f"OpenFOAM thermal surrogate JSON not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_openfoam_surrogate(path: Path | None = None) -> dict[str, Any]:
    """Load verified OpenFOAM 14 tilted-PV thermal surrogate table."""
    if path is not None:
        target = path.resolve()
    elif PACKAGE_CFD_SURROGATE_PATH.is_file():
        target = PACKAGE_CFD_SURROGATE_PATH.resolve()
    else:
        target = DEFAULT_CFD_SURROGATE_PATH.resolve()
    return _read_surrogate_cached(str(target))


def estimate_water_surface_temp(temp_air_c: pd.Series, wind_speed_ms: pd.Series) -> pd.Series:
    """72-hour thermally damped water surface temperature with evaporative wind cooling."""
    lagged = temp_air_c.ewm(halflife=36.0, adjust=False).mean()
    evap_cool = 1.2 + 0.25 * np.clip(wind_speed_ms.to_numpy(dtype=float), 0.5, 10.0)
    t_water = np.maximum(2.0, lagged.to_numpy(dtype=float) - evap_cool)
    return pd.Series(t_water, index=temp_air_c.index, name="temp_water_c")


def compute_cell_temperature(
    poa_global: pd.Series,
    temp_air: pd.Series,
    wind_speed: pd.Series,
    wind_direction: pd.Series,
    site: SiteConfig,
) -> pd.Series:
    """Compute hourly PV cell temperature for open_rack, convective_land, or floating_pv."""
    mode = site.mounting_mode.lower().strip()
    ws = np.clip(wind_speed.to_numpy(dtype=float), 0.2, 25.0)
    poa = np.maximum(0.0, poa_global.to_numpy(dtype=float))
    ta = temp_air.to_numpy(dtype=float)

    if mode == "open_rack":
        t_cell = pvlib.temperature.faiman(
            poa_global=poa_global,
            temp_air=temp_air,
            wind_speed=pd.Series(ws, index=temp_air.index),
            u0=25.0,
            u1=6.84,
        )
        return pd.Series(t_cell, index=temp_air.index, name="temp_cell_c")

    if mode == "convective_land":
        wd = wind_direction.to_numpy(dtype=float)
        # Flow perpendicular to row axis penetrates inter-row alleys better than sheltered parallel flow
        attack = 0.72 + 0.28 * np.abs(np.sin(np.radians(wd - site.surface_azimuth_deg)))
        shelter = max(0.55, 1.0 - 0.32 * max(0.0, site.gcr - 0.35))
        u_total = 25.5 + 7.2 * ws * attack * shelter
        rad_sky_cool = 1.4  # modest night/clear-sky radiative drop
        t_cell_arr = ta + poa / u_total - rad_sky_cool * (poa < 5.0)
        return pd.Series(t_cell_arr, index=temp_air.index, name="temp_cell_c")

    if mode == "floating_pv":
        # Marine/reservoir boundary layer cooling: higher heat transfer + coupled water sink
        t_water = estimate_water_surface_temp(temp_air, wind_speed).to_numpy(dtype=float)
        t_sink = 0.55 * ta + 0.45 * t_water
        # Free-over-water fetch enhances wind turbulence & convective coefficients
        u_fpv = 31.5 + 8.9 * (1.12 * ws)
        t_cell_arr = t_sink + poa / u_fpv
        return pd.Series(t_cell_arr, index=temp_air.index, name="temp_cell_c")

    if mode == "cfd_land":
        surrogate = load_openfoam_surrogate()
        eq = surrogate["surfaces"]["land_rack"]["faiman_equivalent"]
        u_cfd = float(eq["u0"]) + float(eq["u1"]) * ws
        t_cell_arr = ta + poa / u_cfd
        return pd.Series(t_cell_arr, index=temp_air.index, name="temp_cell_c")

    if mode == "cfd_floating_pv":
        surrogate = load_openfoam_surrogate()
        eq = surrogate["surfaces"]["floating_pv"]["faiman_equivalent"]
        t_water = estimate_water_surface_temp(temp_air, wind_speed).to_numpy(dtype=float)
        t_sink = 0.60 * ta + 0.40 * t_water
        u_cfd = float(eq["u0"]) + float(eq["u1"]) * ws
        t_cell_arr = t_sink + poa / u_cfd
        return pd.Series(t_cell_arr, index=temp_air.index, name="temp_cell_c")

    raise ValueError(f"Unsupported mounting_mode: {site.mounting_mode!r}")


def compute_ess_hvac_aux_kw(
    temp_air_c: np.ndarray,
    ess_throughput_kw: np.ndarray,
    ess_energy_kwh: float,
    cop_cooling: float = 3.2,
    t_set_c: float = 25.0,
) -> np.ndarray:
    """Deterministic LiFePO4 container thermal HVAC auxiliary load in kW."""
    if ess_energy_kwh <= 0.0:
        return np.zeros_like(temp_air_c, dtype=float)
    # Envelope conduction scales with container size + C-rate internal I2R heat (~2.5% of throughput)
    ua_kw_per_c = 0.018 * (ess_energy_kwh / 100.0) ** 0.67
    q_envelope = np.maximum(0.0, (temp_air_c - t_set_c) * ua_kw_per_c)
    q_internal = 0.025 * np.abs(ess_throughput_kw)
    q_heat = q_envelope + q_internal
    standby_bms_kw = 0.08 * (ess_energy_kwh / 100.0)
    return standby_bms_kw + q_heat / cop_cooling
