"""Real utility-scale PV plant telemetry validation (US DOE / NREL PVDAQ OEDI)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from heliostack.models import InverterSpec, PVModuleSpec, SiteConfig
from heliostack.pv_engine import run_pv_from_measured_poa

OEDI_2107_BASE = "https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI"


def _download_if_missing(url: str, dest: Path, timeout_s: int = 60) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file():
        resp = requests.get(url, timeout=timeout_s)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return dest


def fetch_and_prepare_pvdaq_2107_2024(
    raw_cache_dir: Path,
    out_hourly_csv: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch public NREL PVDAQ #2107 (2024) telemetry, convert F/mph/local TZ, and aggregate hourly."""
    env_path = _download_if_missing(f"{OEDI_2107_BASE}/data/2107_environment_data_2024.csv", raw_cache_dir / "2107_environment_data_2024.csv")
    irr_path = _download_if_missing(f"{OEDI_2107_BASE}/data/2107_irradiance_data_2024.csv", raw_cache_dir / "2107_irradiance_data_2024.csv")
    mtr_path = _download_if_missing(f"{OEDI_2107_BASE}/data/2107_meter_15m_data_2024.csv", raw_cache_dir / "2107_meter_15m_data_2024.csv")
    meta_path = _download_if_missing(f"{OEDI_2107_BASE}/metadata/2107_system_metadata.json", raw_cache_dir / "2107_system_metadata.json")

    def _read_ts(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path, parse_dates=["measured_on"]).set_index("measured_on").sort_index()
        df.index = df.index.tz_localize("America/Los_Angeles", ambiguous="NaT", nonexistent="shift_forward")
        df = df[~df.index.isna()]
        df.index = df.index.tz_convert("UTC")
        return df.resample("1h").mean()

    df_env = _read_ts(env_path)
    df_irr = _read_ts(irr_path)
    df_mtr = _read_ts(mtr_path)

    merged = pd.DataFrame(index=df_mtr.index.intersection(df_irr.index).intersection(df_env.index))
    merged["poa_global"] = df_irr.loc[merged.index, "poa_irradiance_o_149574"].astype(float).clip(lower=0.0)
    merged["temp_air"] = (df_env.loc[merged.index, "ambient_temperature_o_149575"].astype(float) - 32.0) * (5.0 / 9.0)
    merged["wind_speed"] = (df_env.loc[merged.index, "wind_speed_o_149576"].astype(float) * 0.44704).clip(lower=0.2)
    merged["wind_direction"] = df_env.loc[merged.index, "wind_direction_o_149577"].astype(float).fillna(180.0)
    merged["ac_power_kw"] = df_mtr.loc[merged.index, "meter_revenue_grade_ac_output_meter_149578"].astype(float).clip(lower=0.0)

    merged = merged.dropna()
    out_hourly_csv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_hourly_csv, index=True, index_label="time_utc")

    meta = {
        "source": "US_DOE_NREL_PVDAQ_OEDI_2107_2024",
        "metadata_sha256": hashlib.sha256(meta_path.read_bytes()).hexdigest(),
        "hourly_csv_sha256": hashlib.sha256(out_hourly_csv.read_bytes()).hexdigest(),
        "hourly_rows": int(len(merged)),
    }
    return merged, meta


def load_telemetry_csv(path: Path) -> pd.DataFrame:
    """Load preprocessed hourly field telemetry CSV cleanly."""
    df = pd.read_csv(path, parse_dates=["time_utc"]).set_index("time_utc").sort_index()
    required = ("poa_global", "temp_air", "wind_speed", "wind_direction", "ac_power_kw")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Telemetry CSV missing columns: {missing}")
    return df


def _regression_metrics(meas: np.ndarray, pred: np.ndarray, dc_kwp: float) -> dict[str, float]:
    diff = pred - meas
    mbe_pct = float(np.sum(diff) / max(1e-6, np.sum(meas)) * 100.0)
    rmse_kw = float(np.sqrt(np.mean(diff * diff)))
    nrmse_pct = float(rmse_kw / max(1e-6, dc_kwp) * 100.0)
    ss_res = float(np.sum(diff * diff))
    ss_tot = float(np.sum((meas - np.mean(meas)) ** 2))
    r2 = 1.0 - ss_res / max(1e-9, ss_tot)
    return {
        "measured_mwh": round(float(np.sum(meas)) / 1000.0, 2),
        "modeled_mwh": round(float(np.sum(pred)) / 1000.0, 2),
        "mbe_pct": round(mbe_pct, 2),
        "rmse_kw": round(rmse_kw, 2),
        "nrmse_pct": round(nrmse_pct, 2),
        "r2": round(r2, 4),
    }


def evaluate_field_validation(
    df_hourly: pd.DataFrame,
    site: SiteConfig,
    module: PVModuleSpec,
    inverter: InverterSpec,
    inverter_count: int = 24,
    plant_age_years: float = 7.0,
) -> dict[str, Any]:
    """Validate HelioStack open_rack and convective_land thermal models against real field telemetry."""
    times = df_hourly.index
    poa = df_hourly["poa_global"].to_numpy(dtype=float)
    ta = df_hourly["temp_air"].to_numpy(dtype=float)
    ws = df_hourly["wind_speed"].to_numpy(dtype=float)
    wd = df_hourly["wind_direction"].to_numpy(dtype=float)
    meas = df_hourly["ac_power_kw"].to_numpy(dtype=float)

    # Filter out grid curtailment/inverter offline outages (>5 kW measured during daylight POA >= 50 W/m2)
    daylight = poa >= 50.0
    valid_op = daylight & (meas > 5.0)
    aging_factor = max(0.80, 1.0 - 0.005 * plant_age_years)

    mode_results: dict[str, Any] = {}
    for mode in ("open_rack", "convective_land"):
        cfg_mode = replace(site, mounting_mode=mode)
        sim = run_pv_from_measured_poa(
            times=times,
            poa_global=poa,
            temp_air=ta,
            wind_speed=ws,
            wind_direction=wd,
            site=cfg_mode,
            module=module,
            inverter=inverter,
            dc_aging_factor=aging_factor,
            inverter_count_override=inverter_count,
        )
        pred = sim["ac_net_kw"]
        inv_cap = float(sim["inv_max_total_kw"])
        stats = _regression_metrics(meas[valid_op], pred[valid_op], site.dc_kwp)
        stats["clipping_hours_measured"] = int(np.sum(meas[valid_op] >= inv_cap * 0.985))
        stats["clipping_hours_modeled"] = int(np.sum(pred[valid_op] >= inv_cap * 0.985))

        months = df_hourly.index.month
        monthly_meas = [round(float(np.sum(meas[valid_op & (months == m)])) / 1000.0, 2) for m in range(1, 13)]
        monthly_pred = [round(float(np.sum(pred[valid_op & (months == m)])) / 1000.0, 2) for m in range(1, 13)]
        stats["monthly_measured_mwh"] = monthly_meas
        stats["monthly_modeled_mwh"] = monthly_pred
        mode_results[mode] = stats

    return {
        "site_name": site.site_name,
        "dc_kwp": site.dc_kwp,
        "inverter_block_kw": round(inverter_count * inverter.p_max_ac_kw, 2),
        "plant_age_years": plant_age_years,
        "aging_factor": round(aging_factor, 4),
        "total_hourly_rows": int(len(df_hourly)),
        "total_daylight_hours": int(np.sum(daylight)),
        "valid_operating_hours": int(np.sum(valid_op)),
        "outage_or_zero_hours": int(np.sum(daylight & ~valid_op)),
        "peak_measured_kw": round(float(np.max(meas)), 2),
        "models": mode_results,
    }
