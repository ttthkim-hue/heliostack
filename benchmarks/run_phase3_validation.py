"""Phase 3 Validation Benchmark: OpenFOAM 14 Thermal Surrogate & EU Cyprus 1-Yr Testbed."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from heliostack.telemetry import evaluate_eu_cyprus_validation, fetch_and_prepare_cyprus_pcoe
from heliostack.thermal import load_openfoam_surrogate

ROOT = Path(__file__).resolve().parent.parent
RAW_CACHE = ROOT / "outputs" / "oedi_cache"
CYPRUS_CSV = ROOT / "fixtures" / "telemetry" / "eu_cyprus_pcoe_2015_2016_hourly.csv"
RESULTS_PATH = ROOT / "results" / "phase3_validation_v03.json"


def main() -> None:
    t0 = time.perf_counter()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 1. OpenFOAM 14 verified thermal surrogate summary
    cfd_surrogate = load_openfoam_surrogate()
    for surf, sdata in cfd_surrogate["surfaces"].items():
        feq = sdata["faiman_equivalent"]
        fit = sdata["h_conv_linear_fit_w_m2k"]
        print(
            f"[OpenFOAM14 {surf}] h_conv(v) = {fit['c0']} + {fit['c1']}*v W/m2K | "
            f"Faiman equiv U0={feq['u0']}, U1={feq['u1']}"
        )

    # 2. European Union full-year measured telemetry (Cyprus PHAETHON CoE, CC-BY-4.0)
    df_cy, prov_cy = fetch_and_prepare_cyprus_pcoe(RAW_CACHE, CYPRUS_CSV)
    val_cy = evaluate_eu_cyprus_validation(df_cy)
    val_cy["data_provenance"] = prov_cy

    for mode, mres in val_cy["models"].items():
        tm = mres["module_temp"]
        dc = mres["dc_power"]
        ac = mres["ac_power"]
        print(
            f"[EU Cyprus {mode}] Tmod RMSE={tm['rmse_c']} C MAE={tm['mae_c']} C R2={tm['r2']} | "
            f"DC {dc['measured_kwh']} vs {dc['modeled_kwh']} kWh (MBE={dc['mbe_pct']:+.2f}%, R2={dc['r2']}) | "
            f"AC MBE={ac['mbe_pct']:+.2f}%"
        )

    engineering_roadmap: dict[str, Any] = {
        "verified_baseline_v03": [
            "Clean-room .PAN/.OND validator and 12-step PVsyst loss waterfall",
            "3D ray-box obstacles + 36-azimuth Copernicus DEM horizon & diffuse SVF",
            "2D canonical OpenFOAM 14 steady RANS thermal surrogate (land & Floating PV)",
            "Offline/cached US PVDAQ #2107 & EU Cyprus 1-year validation harnesses",
            "8,760-hr HiGHS LiFePO4 curtailment-recovery dispatch LP & RO-Crate 1.1 audit",
        ],
        "planned_v10_milestones": [
            "M1: Full 3D string-level electrical mismatch, bypass diode I-V shading, single/dual-axis trackers",
            "M2: Flagship 3D multi-row turbulent CHT OpenFOAM atlas covering BIPV ventilated facades, agrivoltaics & wave-tilted FPV + academic benchmark paper pack",
            "M3: 25-year probabilistic Monte-Carlo P50/P90/P99 bankability, SEI battery degradation & EU ENTSO-E negative-price MILP",
            "M4: Local browser WebAssembly/WebGL CAD scene editor, open crowd-verified equipment DB, Debian/Nix/PyPI packaging & WCAG audit",
        ],
    }

    payload = {
        "engine_version": "0.3.2",
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "openfoam14_thermal_surrogate": cfd_surrogate,
        "eu_cyprus_field_validation": val_cy,
        "engineering_roadmap": engineering_roadmap,
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Saved Phase 3 validation to {RESULTS_PATH} in {payload['elapsed_s']}s")


if __name__ == "__main__":
    main()
