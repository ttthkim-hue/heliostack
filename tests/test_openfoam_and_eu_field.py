"""Tests for OpenFOAM 14 tilted-PV thermal surrogate and EU Cyprus 1-year validation."""

from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from heliostack.models import SiteConfig
from heliostack.telemetry import evaluate_eu_cyprus_validation, load_cyprus_telemetry_csv
from heliostack.thermal import compute_cell_temperature, load_openfoam_surrogate

ROOT = Path(__file__).resolve().parent.parent
CYPRUS_CSV = ROOT / "fixtures" / "telemetry" / "eu_cyprus_pcoe_2015_2016_hourly.csv"
OPENFOAM_SWEEP_SCRIPT = ROOT / "openfoam" / "run_openfoam_pv_sweep.py"
SURROGATE_JSON = ROOT / "fixtures" / "thermal" / "openfoam14_pv_thermal_surrogate.json"


def test_openfoam14_surrogate_physics_and_fpv_cooling(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_openfoam_surrogate(tmp_path / "missing_surrogate.json")
    surr = load_openfoam_surrogate()
    assert "OpenFOAM 14" in surr["solver"]
    surfaces = surr["surfaces"]
    assert "land_rack" in surfaces and "floating_pv" in surfaces

    for sname in ("land_rack", "floating_pv"):
        cases = surfaces[sname]["cases"]
        winds = [c["wind_speed_ms"] for c in cases]
        h_convs = [c["h_conv_total_w_m2k"] for c in cases]
        assert winds == sorted(winds)
        assert all(h2 > h1 for h1, h2 in zip(h_convs[:-1], h_convs[1:], strict=True))
        eq = surfaces[sname]["faiman_equivalent"]
        assert 15.0 < eq["u0"] < 45.0
        assert 2.0 < eq["u1"] < 15.0

    # Radiative + pontoon clearance advantage makes cfd_floating_pv cooler than cfd_land
    fpv_u0 = surfaces["floating_pv"]["faiman_equivalent"]["u0"]
    land_u0 = surfaces["land_rack"]["faiman_equivalent"]["u0"]
    assert fpv_u0 > land_u0

    idx = pd.date_range("2024-07-01", periods=96, freq="1h", tz="UTC")
    poa = pd.Series(np.tile(np.concatenate([np.zeros(6), np.full(12, 900.0), np.zeros(6)]), 4), index=idx)
    ta = pd.Series(np.full(96, 30.0), index=idx)
    ws = pd.Series(np.full(96, 3.0), index=idx)
    wd = pd.Series(np.full(96, 90.0), index=idx)

    tc_land = compute_cell_temperature(poa, ta, ws, wd, SiteConfig("CFD Land", 35.1, 33.4, mounting_mode="cfd_land"))
    tc_fpv = compute_cell_temperature(poa, ta, ws, wd, SiteConfig("CFD FPV", 35.1, 33.4, mounting_mode="cfd_floating_pv"))
    day = poa > 500.0
    assert float(tc_fpv[day].mean()) < float(tc_land[day].mean()) - 1.5


def test_eu_cyprus_pcoe_thermal_and_power_validation(tmp_path: Path) -> None:
    df = load_cyprus_telemetry_csv(CYPRUS_CSV)
    assert len(df) == 8784

    bad = tmp_path / "bad_cyprus.csv"
    df.drop(columns=["temp_module_c"]).head(10).to_csv(bad, index_label="time_local")
    with pytest.raises(ValueError, match="missing columns"):
        load_cyprus_telemetry_csv(bad)

    res = evaluate_eu_cyprus_validation(df)
    assert res["valid_operating_hours"] > 3500

    cfd = res["models"]["cfd_land"]
    assert cfd["module_temp"]["rmse_c"] < 6.0
    assert cfd["module_temp"]["r2"] > 0.85
    assert cfd["dc_power"]["r2"] > 0.90
    assert abs(cfd["dc_power"]["mbe_pct"]) < 8.0
    assert cfd["ac_power"]["r2"] > 0.90


def test_openfoam_cli_help_and_generate_case_only(tmp_path: Path) -> None:
    help_proc = subprocess.run(
        [sys.executable, str(OPENFOAM_SWEEP_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_proc.returncode == 0
    for flag in ("--recompute-from-cache", "--native", "--smoke", "--out", "--generate-case-only"):
        assert flag in help_proc.stdout

    case_dir = tmp_path / "of14_case"
    gen_proc = subprocess.run(
        [sys.executable, str(OPENFOAM_SWEEP_SCRIPT), "--generate-case-only", str(case_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert gen_proc.returncode == 0, gen_proc.stderr

    expected_files = (
        "0/U",
        "0/T",
        "0/p_rgh",
        "0/p",
        "0/k",
        "0/omega",
        "0/nut",
        "0/alphat",
        "constant/g",
        "constant/pRef",
        "constant/momentumTransport",
        "constant/physicalProperties",
        "system/blockMeshDict",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
        "system/functions",
    )
    for rel_path in expected_files:
        file_path = case_dir / rel_path
        assert file_path.is_file(), f"Missing generated OpenFOAM file: {rel_path}"

    block_mesh = (case_dir / "system" / "blockMeshDict").read_text(encoding="utf-8")
    for patch in ("inlet", "outlet", "top", "ground", "panelTop", "panelBottom", "panelEdges"):
        assert patch in block_mesh

    verts = [
        tuple(float(v) for v in m.groups())
        for m in re.finditer(r"^\s+\(([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)$", block_mesh, re.MULTILINE)
    ]
    assert len(verts) == 32
    assert all(math.isfinite(coord) for pt in verts for coord in pt)
    assert min(pt[0] for pt in verts) == pytest.approx(-4.0)
    assert max(pt[0] for pt in verts) == pytest.approx(10.0)
    assert min(pt[1] for pt in verts) == pytest.approx(0.0)
    assert max(pt[1] for pt in verts) == pytest.approx(5.5)

    blocks = [
        tuple(int(c) for c in m.groups())
        for m in re.finditer(r"hex\s+\([^)]+\)\s+\((\d+)\s+(\d+)\s+(\d+)\)", block_mesh)
    ]
    assert len(blocks) == 8
    assert sum(nx * ny * nz for nx, ny, nz in blocks) == 6044

    control_dict = (case_dir / "system" / "controlDict").read_text(encoding="utf-8")
    assert "solver          fluid;" in control_dict
    assert "endTime         800;" in control_dict
    assert "writeInterval   200;" in control_dict
    for fn_name in ("wallHeatFlux1", "panelTopFlux", "panelBottomFlux"):
        assert fn_name in control_dict

    functions_dict = (case_dir / "system" / "functions").read_text(encoding="utf-8")
    assert "object      functions;" in functions_dict

    u_text = (case_dir / "0" / "U").read_text(encoding="utf-8")
    t_text = (case_dir / "0" / "T").read_text(encoding="utf-8")
    k_text = (case_dir / "0" / "k").read_text(encoding="utf-8")
    omega_text = (case_dir / "0" / "omega").read_text(encoding="utf-8")
    assert "uniform (2.000 0 0)" in u_text
    assert "uniform 298.15" in t_text and "uniform 308.15" in t_text and "uniform 323.15" in t_text
    k_match = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+);", k_text)
    omega_match = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+);", omega_text)
    assert k_match is not None and math.isfinite(float(k_match.group(1))) and float(k_match.group(1)) > 0.0
    assert omega_match is not None and math.isfinite(float(omega_match.group(1))) and float(omega_match.group(1)) > 0.0

    # Guard: --smoke must refuse overwriting cached surrogate JSON
    guard_proc = subprocess.run(
        [sys.executable, str(OPENFOAM_SWEEP_SCRIPT), "--smoke", "--out", str(SURROGATE_JSON)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert guard_proc.returncode != 0

