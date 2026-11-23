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
from heliostack.thermal import compute_cell_temperature

OEDI_2107_BASE = "https://oedi-data-lake.s3.amazonaws.com/pvdaq/2023-solar-data-prize/2107_OEDI"
CYPRUS_ZENODO_CSV_URL = (
    "https://zenodo.org/api/records/10816826/files/PCoE-Dataset%20PV%20system%20test-bed.csv/content"
)


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


def fetch_and_prepare_cyprus_pcoe(
    raw_cache_dir: Path,
    out_hourly_csv: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch public Univ. of Cyprus PHAETHON CoE 1-year testbed telemetry (Zenodo 10816826, CC-BY-4.0)."""
    raw_csv = _download_if_missing(
        CYPRUS_ZENODO_CSV_URL,
        raw_cache_dir / "cyprus_pcoe_testbed_15m.csv",
        timeout_s=60,
    )
    df_raw = pd.read_csv(raw_csv)
    df_raw["time_local"] = pd.to_datetime(df_raw["time_stamp"], dayfirst=True)
    df_raw = df_raw.set_index("time_local").sort_index()

    hourly = pd.DataFrame(index=df_raw.resample("1h").mean(numeric_only=True).index)
    df_1h = df_raw.resample("1h").mean(numeric_only=True)
    hourly["poa_global"] = df_1h["Gpoa"].astype(float).clip(lower=0.0)
    hourly["temp_air"] = df_1h["Tamb"].astype(float)
    hourly["wind_speed"] = df_1h["WS"].astype(float).clip(lower=0.2)
    hourly["wind_direction"] = df_1h["Waplha"].astype(float).fillna(180.0) % 360.0
    hourly["temp_module_c"] = df_1h["Tmod"].astype(float)
    hourly["p_dc_w"] = df_1h["Pdc"].astype(float).clip(lower=0.0)
    hourly["p_ac_w"] = df_1h["Pac"].astype(float).clip(lower=0.0)
    hourly = hourly.dropna()

    out_hourly_csv.parent.mkdir(parents=True, exist_ok=True)
    hourly.to_csv(out_hourly_csv, index=True, index_label="time_local")
    return hourly, {
        "source": "EU_CYPRUS_PHAETHON_COE_ZENODO_10816826",
        "license": "CC-BY-4.0",
        "doi": "10.5281/zenodo.10816826",
        "raw_csv_sha256": hashlib.sha256(raw_csv.read_bytes()).hexdigest(),
        "hourly_csv_sha256": hashlib.sha256(out_hourly_csv.read_bytes()).hexdigest(),
        "hourly_rows": int(len(hourly)),
        "start": str(hourly.index[0]),
        "end": str(hourly.index[-1]),
    }


def load_cyprus_telemetry_csv(path: Path) -> pd.DataFrame:
    """Load preprocessed 1-year hourly European Cyprus testbed telemetry cleanly."""
    df = pd.read_csv(path, parse_dates=["time_local"]).set_index("time_local").sort_index()
    required = ("poa_global", "temp_air", "wind_speed", "wind_direction", "temp_module_c", "p_dc_w", "p_ac_w")
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Cyprus telemetry CSV missing columns: {missing}")
    return df


def evaluate_eu_cyprus_validation(
    df_hourly: pd.DataFrame,
    p_stc_w: float = 1250.0,
    gamma_pmp_per_c: float = -0.0040,
    eta_inv_nom: float = 0.922,
) -> dict[str, Any]:
    """Validate HelioStack thermal (including OpenFOAM CFD) and yield vs 1-yr EU Cyprus testbed."""
    poa_s = df_hourly["poa_global"].astype(float)
    ta_s = df_hourly["temp_air"].astype(float)
    ws_s = df_hourly["wind_speed"].astype(float)
    wd_s = df_hourly["wind_direction"].astype(float)
    t_mod = df_hourly["temp_module_c"].to_numpy(dtype=float)
    p_dc = df_hourly["p_dc_w"].to_numpy(dtype=float)
    p_ac = df_hourly["p_ac_w"].to_numpy(dtype=float)
    poa = poa_s.to_numpy(dtype=float)

    valid = (poa >= 50.0) & (p_dc > 10.0) & (p_ac > 10.0)
    site_base = SiteConfig(
        site_name="University of Cyprus PHAETHON CoE Outdoor Testbed (Nicosia, CY)",
        latitude=35.144,
        longitude=33.411,
        elevation_m=150.0,
        surface_tilt_deg=27.5,
        surface_azimuth_deg=180.0,
        dc_kwp=p_stc_w / 1000.0,
        gcr=0.40,
    )

    months = df_hourly.index.month
    mode_results: dict[str, Any] = {}
    for mode in ("open_rack", "convective_land", "cfd_land"):
        t_cell = compute_cell_temperature(
            poa_s, ta_s, ws_s, wd_s, replace(site_base, mounting_mode=mode)
        ).to_numpy(dtype=float)

        # Direct physical module backsheet temperature validation (Sandia King et al. 2004 open-rack 3 C/1000 W/m2 offset)
        t_mod_pred = t_cell - 3.0 * (poa / 1000.0)
        t_diff = t_mod_pred[valid] - t_mod[valid]
        ss_res_t = float(np.sum(t_diff * t_diff))
        ss_tot_t = float(np.sum((t_mod[valid] - np.mean(t_mod[valid])) ** 2))
        temp_stats = {
            "mbe_c": round(float(np.mean(t_diff)), 2),
            "mae_c": round(float(np.mean(np.abs(t_diff))), 2),
            "rmse_c": round(float(np.sqrt(np.mean(t_diff * t_diff))), 2),
            "r2": round(1.0 - ss_res_t / max(1e-9, ss_tot_t), 4),
        }

        # Physical DC & AC power validation using thermal predictions
        p_dc_pred = np.where(
            valid,
            p_stc_w * (poa / 1000.0) * 0.985 * np.maximum(0.65, 1.0 + gamma_pmp_per_c * (t_cell - 25.0)),
            0.0,
        )
        p_ac_pred = p_dc_pred * eta_inv_nom

        dc_kw_stats = _regression_metrics(p_dc[valid] / 1000.0, p_dc_pred[valid] / 1000.0, p_stc_w / 1000.0)
        ac_kw_stats = _regression_metrics(p_ac[valid] / 1000.0, p_ac_pred[valid] / 1000.0, p_stc_w / 1000.0)
        monthly_dc_meas = [round(float(np.sum(p_dc[valid & (months == m)])) / 1000.0, 1) for m in range(1, 13)]
        monthly_dc_pred = [round(float(np.sum(p_dc_pred[valid & (months == m)])) / 1000.0, 1) for m in range(1, 13)]
        mode_results[mode] = {
            "module_temp": temp_stats,
            "dc_power": {
                "measured_kwh": round(dc_kw_stats["measured_mwh"] * 1000.0, 1),
                "modeled_kwh": round(dc_kw_stats["modeled_mwh"] * 1000.0, 1),
                "mbe_pct": dc_kw_stats["mbe_pct"],
                "nrmse_pct": dc_kw_stats["nrmse_pct"],
                "r2": dc_kw_stats["r2"],
                "monthly_measured_kwh": monthly_dc_meas,
                "monthly_modeled_kwh": monthly_dc_pred,
            },
            "ac_power": {
                "measured_kwh": round(ac_kw_stats["measured_mwh"] * 1000.0, 1),
                "modeled_kwh": round(ac_kw_stats["modeled_mwh"] * 1000.0, 1),
                "mbe_pct": ac_kw_stats["mbe_pct"],
                "nrmse_pct": ac_kw_stats["nrmse_pct"],
                "r2": ac_kw_stats["r2"],
            },
        }

    return {
        "site_name": site_base.site_name,
        "dc_stc_w": p_stc_w,
        "cell_to_backsheet_offset_c_at_1000": 3.0,
        "total_hourly_rows": int(len(df_hourly)),
        "valid_operating_hours": int(np.sum(valid)),
        "mean_measured_tmod_c": round(float(np.mean(t_mod[valid])), 2),
        "peak_measured_tmod_c": round(float(np.max(t_mod[valid])), 2),
        "models": mode_results,
    }
