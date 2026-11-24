"""Reproducible OpenFOAM 14 2D Tilted PV Module Convective Cooling Sweep.

Runs strictly single-core (`nice -n 19`, zero MPI, zero GPU) either inside WSL2
`Ubuntu-24.04` or natively on Linux/container/CI (`--native`) against
`/opt/openfoam14` (`foamRun -solver fluid`, steady `kOmegaSST`, `heRhoThermo`)
around a 28-deg tilted 2.0 m PV module over sunlit land vs cool reservoir water.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "fixtures" / "thermal" / "openfoam14_pv_thermal_surrogate.json"
WSL_CASE_BASE = "/tmp/heliostack_of14_run"

FULL_END_TIME = 800
FULL_WRITE_INTERVAL = 200
SMOKE_END_TIME = 80
SMOKE_WRITE_INTERVAL = 80

BLOCK_NX = (18, 40, 34)
BLOCK_NY = (28, 3, 36)
EXPECTED_BLOCKMESH_CELLS = sum(
    BLOCK_NX[ix] * BLOCK_NY[iy]
    for iy in range(3)
    for ix in range(3)
    if not (ix == 1 and iy == 1)
)

TILT_DEG = 28.0
PANEL_CHORD_M = 2.0
DX_PANEL_M = PANEL_CHORD_M * math.cos(math.radians(TILT_DEG))  # 1.7659 m
DY_PANEL_M = PANEL_CHORD_M * math.sin(math.radians(TILT_DEG))  # 0.9389 m
PANEL_THICK_Y_M = 0.06
Y_TOP_M = 5.5

# Physical boundary conditions & dual-sided longwave radiation (T_sky = Tamb - 12 K)
T_AMB_K = 298.15  # 25.0 degC ambient freestream
T_SKY_K = T_AMB_K - 12.0  # 286.15 K clear-sky longwave sink
T_PANEL_K = 323.15  # 50.0 degC module operating baseline (dT = 25 K)
T_GROUND_LAND_K = 308.15  # 35.0 degC sunlit soil beneath rack
T_WATER_FPV_K = 294.15  # 21.0 degC evaporative water surface beneath FPV
ABSORPTANCE_THERMAL_FRAC = 0.90 * (1.0 - 0.19)  # 0.729 heat-to-incident-POA ratio
SIGMA_SB = 5.670374419e-8
EPS_SURFACE = 0.85

WIND_SPEEDS_MS = [1.0, 2.0, 4.0, 6.0]


def _natural_convection_h_2side() -> float:
    """McAdams/Churchill-Chu two-sided natural convection coefficient (W/m2K) at dT=25 K."""
    g = 9.81
    beta = 1.0 / (0.5 * (T_PANEL_K + T_AMB_K))
    dt = T_PANEL_K - T_AMB_K
    length = PANEL_CHORD_M
    nu = 1.67e-5
    alpha = 2.36e-5
    k_air = 0.027
    ra = g * beta * dt * (length ** 3) / (nu * alpha)
    h_top = 0.15 * (ra ** (1.0 / 3.0)) * k_air / length
    h_bot = 0.27 * (ra ** 0.25) * k_air / length
    return h_top + h_bot


def _radiative_effective_h(t_ground_k: float) -> float:
    """Asymmetric front (sky/ground) + rear (ground/sky) linearized radiative coefficient."""
    f_sky = 0.5 * (1.0 + math.cos(math.radians(TILT_DEG)))
    f_surf = 1.0 - f_sky
    tp4 = T_PANEL_K ** 4
    ts4 = T_SKY_K ** 4
    tg4 = t_ground_k ** 4
    q_rad_front = EPS_SURFACE * SIGMA_SB * (f_sky * (tp4 - ts4) + f_surf * (tp4 - tg4))
    q_rad_rear = EPS_SURFACE * SIGMA_SB * (f_sky * (tp4 - tg4) + f_surf * (tp4 - ts4))
    return (q_rad_front + q_rad_rear) / (T_PANEL_K - T_AMB_K)


def _block_mesh_dict(h_clear_m: float) -> str:
    xs = [-4.0, 0.0, DX_PANEL_M, 10.0]
    zs = [-0.05, 0.05]

    y_col_low = [0.0, h_clear_m, h_clear_m + PANEL_THICK_Y_M, Y_TOP_M]
    y_col_high = [
        0.0,
        h_clear_m + DY_PANEL_M,
        h_clear_m + DY_PANEL_M + PANEL_THICK_Y_M,
        Y_TOP_M,
    ]

    verts = []
    for z in zs:
        for iy in range(4):
            for ix, x in enumerate(xs):
                y = y_col_low[iy] if ix <= 1 else y_col_high[iy]
                verts.append(f"    ({x:.4f} {y:.4f} {z:.3f})")

    def vid(ix: int, iy: int, iz: int) -> int:
        return iz * 16 + iy * 4 + ix

    nx_list = list(BLOCK_NX)
    ny_list = list(BLOCK_NY)
    gx_list = [0.35, 1.0, 4.0]
    gy_strs = [
        "((0.5 0.5 2.5) (0.5 0.5 0.4))",
        "1",
        "4.5",
    ]

    blocks = []
    for iy in range(3):
        for ix in range(3):
            if ix == 1 and iy == 1:
                continue  # Solid 28-deg tilted 2.0 m PV module cavity
            v0 = vid(ix, iy, 0)
            v1 = vid(ix + 1, iy, 0)
            v2 = vid(ix + 1, iy + 1, 0)
            v3 = vid(ix, iy + 1, 0)
            v4 = vid(ix, iy, 1)
            v5 = vid(ix + 1, iy, 1)
            v6 = vid(ix + 1, iy + 1, 1)
            v7 = vid(ix, iy + 1, 1)
            blocks.append(
                f"    hex ({v0} {v1} {v2} {v3} {v4} {v5} {v6} {v7}) "
                f"({nx_list[ix]} {ny_list[iy]} 1) simpleGrading ({gx_list[ix]} {gy_strs[iy]} 1)"
            )

    inlet_faces = "\n".join(
        f"            ({vid(0, iy, 0)} {vid(0, iy, 1)} {vid(0, iy + 1, 1)} {vid(0, iy + 1, 0)})"
        for iy in range(3)
    )
    outlet_faces = "\n".join(
        f"            ({vid(3, iy, 0)} {vid(3, iy + 1, 0)} {vid(3, iy + 1, 1)} {vid(3, iy, 1)})"
        for iy in range(3)
    )
    top_faces = "\n".join(
        f"            ({vid(ix, 3, 0)} {vid(ix, 3, 1)} {vid(ix + 1, 3, 1)} {vid(ix + 1, 3, 0)})"
        for ix in range(3)
    )
    ground_faces = "\n".join(
        f"            ({vid(ix, 0, 0)} {vid(ix + 1, 0, 0)} {vid(ix + 1, 0, 1)} {vid(ix, 0, 1)})"
        for ix in range(3)
    )
    panel_top = f"            ({vid(1, 2, 0)} {vid(2, 2, 0)} {vid(2, 2, 1)} {vid(1, 2, 1)})"
    panel_bot = f"            ({vid(1, 1, 0)} {vid(1, 1, 1)} {vid(2, 1, 1)} {vid(2, 1, 0)})"
    edge_le = f"            ({vid(1, 1, 0)} {vid(1, 2, 0)} {vid(1, 2, 1)} {vid(1, 1, 1)})"
    edge_te = f"            ({vid(2, 1, 0)} {vid(2, 1, 1)} {vid(2, 2, 1)} {vid(2, 2, 0)})"

    return f"""FoamFile
{{
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
scale   1;

vertices
(
{chr(10).join(verts)}
);

blocks
(
{chr(10).join(blocks)}
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
{inlet_faces}
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
{outlet_faces}
        );
    }}
    top
    {{
        type patch;
        faces
        (
{top_faces}
        );
    }}
    ground
    {{
        type wall;
        faces
        (
{ground_faces}
        );
    }}
    panelTop
    {{
        type wall;
        faces
        (
{panel_top}
        );
    }}
    panelBottom
    {{
        type wall;
        faces
        (
{panel_bot}
        );
    }}
    panelEdges
    {{
        type wall;
        faces
        (
{edge_le}
{edge_te}
        );
    }}
);
"""


def _case_files(
    u_in: float,
    t_ground_k: float,
    h_clear_m: float,
    *,
    end_time: int = FULL_END_TIME,
    write_interval: int = FULL_WRITE_INTERVAL,
) -> dict[str, str]:
    # Outdoor atmospheric boundary layer turbulence intensity I = 10%, scale L_t = 0.30 m
    k_in = max(5e-4, 1.5 * (0.10 * u_in) ** 2)
    omega_in = max(0.15, math.sqrt(k_in) / ((0.09 ** 0.25) * 0.30))

    def _hdr(cls: str, loc: str, obj: str) -> str:
        return (
            "FoamFile\n{\n"
            "    format      ascii;\n"
            f"    class       {cls};\n"
            f'    location    "{loc}";\n'
            f"    object      {obj};\n"
            "}\n"
        )

    files: dict[str, str] = {}
    files["system/blockMeshDict"] = _block_mesh_dict(h_clear_m)
    files["system/controlDict"] = _hdr("dictionary", "system", "controlDict") + f"""
solver          fluid;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time};
deltaT          1;
writeControl    timeStep;
writeInterval   {write_interval};
purgeWrite      2;
writeFormat     ascii;
writePrecision  6;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;

functions
{{
    wallHeatFlux1
    {{
        type            wallHeatFlux;
        libs            ("libfieldFunctionObjects.so");
        executeControl  writeTime;
        writeControl    writeTime;
        patches         (panelTop panelBottom ground);
    }}
    panelTopFlux
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        log             yes;
        writeFields     no;
        patch           panelTop;
        operation       areaAverage;
        fields          (wallHeatFlux);
        executeControl  writeTime;
        writeControl    writeTime;
    }}
    panelBottomFlux
    {{
        type            surfaceFieldValue;
        libs            ("libfieldFunctionObjects.so");
        log             yes;
        writeFields     no;
        patch           panelBottom;
        operation       areaAverage;
        fields          (wallHeatFlux);
        executeControl  writeTime;
        writeControl    writeTime;
    }}
}}
"""
    files["system/functions"] = _hdr("dictionary", "system", "functions") + (
        "// Active runtime function objects (wallHeatFlux1, panelTopFlux, panelBottomFlux)\n"
        "// are embedded in system/controlDict for single-file OpenFOAM 14 compatibility;\n"
        "// this dictionary intentionally stays empty to prevent duplicate execution.\n"
    )
    files["system/fvSchemes"] = _hdr("dictionary", "system", "fvSchemes") + """
ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; }
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss linearUpwind grad(U);
    div(phi,K)      bounded Gauss upwind;
    div(phi,h)      bounded Gauss linearUpwind grad(T);
    div(phi,k)      bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
}
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; }
snGradSchemes { default corrected; }
wallDist { method meshWave; }
"""
    files["system/fvSolution"] = _hdr("dictionary", "system", "fvSolution") + """
solvers
{
    p_rgh
    {
        solver           GAMG;
        tolerance        1e-7;
        relTol           0.01;
        smoother         DICGaussSeidel;
    }
    "(U|h|k|omega)"
    {
        solver          PBiCGStab;
        preconditioner  DILU;
        tolerance       1e-7;
        relTol          0.1;
    }
}
SIMPLE
{
    nNonOrthogonalCorrectors 1;
    pRefCell        0;
    pRefValue       0;
    residualControl
    {
        p_rgh           1e-4;
        U               1e-4;
        h               1e-4;
        "(k|omega)"     1e-3;
    }
}
relaxationFactors
{
    fields
    {
        rho             0.9;
        p_rgh           0.6;
    }
    equations
    {
        U               0.45;
        h               0.45;
        "(k|omega)"     0.5;
    }
}
"""
    files["constant/g"] = _hdr("uniformDimensionedVectorField", "constant", "g") + (
        "dimensions      [acceleration];\nvalue           (0 -9.81 0);\n"
    )
    files["constant/pRef"] = _hdr("uniformDimensionedScalarField", "constant", "pRef") + (
        "dimensions      [pressure];\nvalue           1e5;\n"
    )
    files["constant/momentumTransport"] = _hdr("dictionary", "constant", "momentumTransport") + (
        "simulationType RAS;\nRAS\n{\n    model kOmegaSST;\n    turbulence on;\n}\n"
    )
    files["constant/physicalProperties"] = _hdr("dictionary", "constant", "physicalProperties") + """
thermoType
{
    type            heRhoThermo;
    mixture         pureMixture;
    transport       const;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}
mixture
{
    specie { molWeight 28.96; }
    thermodynamics { Cp 1004.4; hf 0; }
    transport { mu 1.831e-05; Pr 0.705; }
}
"""
    files["0/U"] = _hdr("volVectorField", "0", "U") + f"""
dimensions      [velocity];
internalField   uniform ({u_in:.3f} 0 0);
boundaryField
{{
    inlet       {{ type fixedValue; value uniform ({u_in:.3f} 0 0); }}
    outlet      {{ type inletOutlet; inletValue uniform (0 0 0); value uniform ({u_in:.3f} 0 0); }}
    top         {{ type slip; }}
    ground      {{ type noSlip; }}
    panelTop    {{ type noSlip; }}
    panelBottom {{ type noSlip; }}
    panelEdges  {{ type noSlip; }}
    #includeEtc "caseDicts/setConstraintTypes"
}}
"""
    files["0/T"] = _hdr("volScalarField", "0", "T") + f"""
dimensions      [temperature];
internalField   uniform {T_AMB_K:.2f};
boundaryField
{{
    inlet       {{ type fixedValue; value uniform {T_AMB_K:.2f}; }}
    outlet      {{ type inletOutlet; inletValue uniform {T_AMB_K:.2f}; value uniform {T_AMB_K:.2f}; }}
    top         {{ type zeroGradient; }}
    ground      {{ type fixedValue; value uniform {t_ground_k:.2f}; }}
    panelTop    {{ type fixedValue; value uniform {T_PANEL_K:.2f}; }}
    panelBottom {{ type fixedValue; value uniform {T_PANEL_K:.2f}; }}
    panelEdges  {{ type zeroGradient; }}
    #includeEtc "caseDicts/setConstraintTypes"
}}
"""
    files["0/p_rgh"] = _hdr("volScalarField", "0", "p_rgh") + """
dimensions      [pressure];
internalField   uniform 0;
boundaryField
{
    inlet       { type fixedFluxPressure; value uniform 0; }
    outlet      { type fixedValue; value uniform 0; }
    top         { type fixedFluxPressure; value uniform 0; }
    ground      { type fixedFluxPressure; value uniform 0; }
    panelTop    { type fixedFluxPressure; value uniform 0; }
    panelBottom { type fixedFluxPressure; value uniform 0; }
    panelEdges  { type fixedFluxPressure; value uniform 0; }
    #includeEtc "caseDicts/setConstraintTypes"
}
"""
    files["0/p"] = _hdr("volScalarField", "0", "p") + """
dimensions      [pressure];
internalField   uniform 1e5;
boundaryField
{
    ".*" { type calculated; value uniform 1e5; }
    #includeEtc "caseDicts/setConstraintTypes"
}
"""
    files["0/k"] = _hdr("volScalarField", "0", "k") + f"""
dimensions      [turbulentKineticEnergy];
internalField   uniform {k_in:.6g};
boundaryField
{{
    inlet       {{ type fixedValue; value uniform {k_in:.6g}; }}
    outlet      {{ type inletOutlet; inletValue uniform {k_in:.6g}; value uniform {k_in:.6g}; }}
    top         {{ type zeroGradient; }}
    ground      {{ type kqRWallFunction; value uniform {k_in:.6g}; }}
    panelTop    {{ type kqRWallFunction; value uniform {k_in:.6g}; }}
    panelBottom {{ type kqRWallFunction; value uniform {k_in:.6g}; }}
    panelEdges  {{ type kqRWallFunction; value uniform {k_in:.6g}; }}
    #includeEtc "caseDicts/setConstraintTypes"
}}
"""
    files["0/omega"] = _hdr("volScalarField", "0", "omega") + f"""
dimensions      [turbulentOmega];
internalField   uniform {omega_in:.6g};
boundaryField
{{
    inlet       {{ type fixedValue; value uniform {omega_in:.6g}; }}
    outlet      {{ type inletOutlet; inletValue uniform {omega_in:.6g}; value uniform {omega_in:.6g}; }}
    top         {{ type zeroGradient; }}
    ground      {{ type omegaWallFunction; value uniform {omega_in:.6g}; }}
    panelTop    {{ type omegaWallFunction; value uniform {omega_in:.6g}; }}
    panelBottom {{ type omegaWallFunction; value uniform {omega_in:.6g}; }}
    panelEdges  {{ type omegaWallFunction; value uniform {omega_in:.6g}; }}
    #includeEtc "caseDicts/setConstraintTypes"
}}
"""
    files["0/nut"] = _hdr("volScalarField", "0", "nut") + """
dimensions      [turbulentViscosity];
internalField   uniform 0;
boundaryField
{
    inlet       { type calculated; value uniform 0; }
    outlet      { type calculated; value uniform 0; }
    top         { type zeroGradient; }
    ground      { type nutUWallFunction; value uniform 0; }
    panelTop    { type nutUWallFunction; value uniform 0; }
    panelBottom { type nutUWallFunction; value uniform 0; }
    panelEdges  { type nutUWallFunction; value uniform 0; }
    #includeEtc "caseDicts/setConstraintTypes"
}
"""
    files["0/alphat"] = _hdr("volScalarField", "0", "alphat") + """
dimensions      [dynamicDiffusivity];
internalField   uniform 0;
boundaryField
{
    inlet       { type calculated; value uniform 0; }
    outlet      { type calculated; value uniform 0; }
    top         { type zeroGradient; }
    ground      { type compressible::alphatWallFunction; Prt 0.85; value uniform 0; }
    panelTop    { type compressible::alphatWallFunction; Prt 0.85; value uniform 0; }
    panelBottom { type compressible::alphatWallFunction; Prt 0.85; value uniform 0; }
    panelEdges  { type compressible::alphatWallFunction; Prt 0.85; value uniform 0; }
    #includeEtc "caseDicts/setConstraintTypes"
}
"""
    return files


def write_case_tree(target_dir: Path, files: dict[str, str]) -> list[Path]:
    """Write an OpenFOAM 14 case dictionary tree to target_dir with LF line endings."""
    written: list[Path] = []
    for rel_path, content in sorted(files.items()):
        dest = target_dir / Path(rel_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode("utf-8"))
        written.append(dest)
    return written


def _shell_argv(cmd: str, *, native: bool) -> list[str]:
    if native:
        return ["bash", "-lc", cmd]
    return ["wsl", "-d", "Ubuntu-24.04", "--", "bash", "-lc", cmd]


def _run_cmd(cmd: str, *, native: bool = False, stdin_text: str | None = None) -> str:
    proc = subprocess.run(
        _shell_argv(cmd, native=native),
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        mode = "Native" if native else "WSL"
        raise RuntimeError(
            f"{mode} OpenFOAM command failed (exit {proc.returncode}):\n"
            f"{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}"
        )
    return proc.stdout


def _wsl_run(cmd: str) -> str:
    return _run_cmd(cmd, native=False)


def _cleanup_case_base(case_base: str, *, native: bool) -> None:
    subprocess.run(
        _shell_argv(f"rm -rf {shlex.quote(case_base)}", native=native),
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_checkmesh_cells(output: str) -> int:
    match = re.search(r"\bcells:\s+(\d+)", output)
    if match is None:
        raise RuntimeError(f"Could not parse cell count from checkMesh output:\n{output}")
    return int(match.group(1))


def _parse_latest_surface_flux(dat_text: str) -> tuple[float, float]:
    rows = []
    for line in dat_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) >= 2:
            rows.append((float(parts[0]), float(parts[1])))
    if not rows:
        raise ValueError(f"No data rows found in surfaceFieldValue.dat:\n{dat_text}")
    return rows[-1]


def _run_single_case(
    surface: str,
    u_in: float,
    t_ground_k: float,
    h_clear_m: float,
    *,
    native: bool = False,
    end_time: int = FULL_END_TIME,
    write_interval: int = FULL_WRITE_INTERVAL,
    case_base: str = WSL_CASE_BASE,
) -> dict[str, Any]:
    case_dir = f"{case_base.rstrip('/')}/{surface}_u{u_in:.0f}"
    files = _case_files(
        u_in,
        t_ground_k,
        h_clear_m,
        end_time=end_time,
        write_interval=write_interval,
    )
    payload_json = json.dumps(files)

    py_write = (
        "import json, pathlib, sys; "
        f"root = pathlib.Path({case_dir!r}); "
        "data = json.loads(sys.stdin.read()); "
        "[((root / k).parent.mkdir(parents=True, exist_ok=True), "
        "(root / k).write_bytes(v.encode('utf-8'))) for k, v in data.items()]"
    )
    _run_cmd(
        f"rm -rf {shlex.quote(case_dir)} && python3 -c {shlex.quote(py_write)}",
        native=native,
        stdin_text=payload_json,
    )

    t0 = time.perf_counter()
    of_cmd = (
        f"source /opt/openfoam14/etc/bashrc && cd {shlex.quote(case_dir)} && "
        "(nice -n 19 blockMesh > log.blockMesh 2>&1 && "
        "nice -n 19 checkMesh -constant > log.checkMesh 2>&1 && "
        "nice -n 19 foamRun -solver fluid > log.foamRun 2>&1 || "
        "{ tail -n 40 log.blockMesh log.checkMesh log.foamRun 2>/dev/null >&2; exit 1; }) && "
        "grep -E 'cells:|Mesh OK' log.checkMesh && "
        "echo '---TOP---' && cat postProcessing/panelTopFlux/*/surfaceFieldValue.dat | tail -n 12 && "
        "echo '---BOT---' && cat postProcessing/panelBottomFlux/*/surfaceFieldValue.dat | tail -n 12 && "
        "echo '---TAIL---' && tail -n 12 log.foamRun && "
        "echo '---HASH---' && sha256sum log.foamRun"
    )
    out = _run_cmd(of_cmd, native=native)
    elapsed_s = round(time.perf_counter() - t0, 2)

    if "Mesh OK" not in out:
        raise RuntimeError(f"checkMesh did not report Mesh OK for {surface} u={u_in}:\n{out}")

    cells = _parse_checkmesh_cells(out)
    top_part = out.split("---TOP---")[1].split("---BOT---")[0]
    bot_part = out.split("---BOT---")[1].split("---TAIL---")[0]
    hash_part = out.split("---HASH---")[1].strip().split()[0]

    step_top, q_top = _parse_latest_surface_flux(top_part)
    step_bot, q_bot = _parse_latest_surface_flux(bot_part)

    dt_panel_air = T_PANEL_K - T_AMB_K
    h_conv_top = abs(q_top) / dt_panel_air
    h_conv_bot = abs(q_bot) / dt_panel_air
    h_conv_total = h_conv_top + h_conv_bot
    h_rad_eff = _radiative_effective_h(t_ground_k)

    for metric_name, metric_val in (
        ("q_panel_top_w_m2", q_top),
        ("q_panel_bottom_w_m2", q_bot),
        ("h_conv_total_w_m2k", h_conv_total),
        ("h_rad_eff_w_m2k", h_rad_eff),
    ):
        if not math.isfinite(metric_val):
            raise RuntimeError(f"Non-finite {metric_name} for {surface} u={u_in}: {metric_val}")
    if h_conv_total <= 0.0:
        raise RuntimeError(f"Expected positive h_conv_total_w_m2k for {surface} u={u_in}, got {h_conv_total}")

    return {
        "surface": surface,
        "wind_speed_ms": u_in,
        "clearance_m": h_clear_m,
        "t_ground_k": t_ground_k,
        "cells": cells,
        "mesh_ok": True,
        "final_step": int(step_top),
        "q_panel_top_w_m2": round(q_top, 3),
        "q_panel_bottom_w_m2": round(q_bot, 3),
        "h_conv_top_w_m2k": round(h_conv_top, 3),
        "h_conv_bottom_w_m2k": round(h_conv_bot, 3),
        "h_conv_total_w_m2k": round(h_conv_total, 3),
        "h_rad_eff_w_m2k": round(h_rad_eff, 3),
        "h_total_with_rad_w_m2k": round(h_conv_total + h_rad_eff, 3),
        "elapsed_s": elapsed_s,
        "foam_log_sha256": hash_part,
        "step_bot": int(step_bot),
    }


def _fit_surface_surrogate(
    t_ground: float,
    h_clear: float,
    cases: list[dict[str, Any]],
    h_nat: float,
) -> dict[str, Any]:
    xs = np.array([c["wind_speed_ms"] for c in cases], dtype=float)
    hc_raw = np.array([c["h_conv_total_w_m2k"] for c in cases], dtype=float)
    c1_raw, c0_raw = np.polyfit(xs, hc_raw, 1)

    # Standard textbook mixed forced+natural convection cube-root blending (Churchill-Chu + RANS)
    hc_mixed = (h_nat ** 3 + hc_raw ** 3) ** (1.0 / 3.0)
    c1, c0 = np.polyfit(xs, hc_mixed, 1)
    h_rad_eff = _radiative_effective_h(t_ground)
    u0_faiman = float((c0 + h_rad_eff) / ABSORPTANCE_THERMAL_FRAC)
    u1_faiman = float(c1 / ABSORPTANCE_THERMAL_FRAC)
    return {
        "ground_boundary_temp_c": round(t_ground - 273.15, 2),
        "clearance_m": h_clear,
        "radiative_effective_h_w_m2k": round(h_rad_eff, 3),
        "cases": cases,
        "h_conv_raw_linear_fit_w_m2k": {"c0": round(float(c0_raw), 3), "c1": round(float(c1_raw), 3)},
        "h_conv_linear_fit_w_m2k": {"c0": round(float(c0), 3), "c1": round(float(c1), 3)},
        "faiman_equivalent": {"u0": round(u0_faiman, 2), "u1": round(u1_faiman, 2)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenFOAM 14 28-deg PV thermal sweep")
    parser.add_argument(
        "--recompute-from-cache",
        action="store_true",
        help="Recompute surrogate fits from already-cached converged OpenFOAM 14 cases JSON",
    )
    parser.add_argument(
        "--native",
        action="store_true",
        help="Execute commands natively via bash -lc (Linux/container/CI) instead of wsl -d Ubuntu-24.04",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a single fast representative case (land_rack, U=2.0 m/s, 80 iterations) without modifying the surrogate JSON",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (smoke receipt path when --smoke is set; surrogate JSON path otherwise)",
    )
    parser.add_argument(
        "--generate-case-only",
        type=Path,
        default=None,
        metavar="DIR",
        help="Write the deterministic OpenFOAM 14 case dictionary tree to DIR without invoking OpenFOAM binaries",
    )
    args = parser.parse_args()

    mode_count = sum(
        [
            bool(args.recompute_from_cache),
            bool(args.smoke),
            args.generate_case_only is not None,
        ]
    )
    if mode_count > 1:
        parser.error("--recompute-from-cache, --smoke, and --generate-case-only are mutually exclusive")

    if args.generate_case_only is not None:
        files = _case_files(
            2.0,
            T_GROUND_LAND_K,
            0.85,
            end_time=FULL_END_TIME,
            write_interval=FULL_WRITE_INTERVAL,
        )
        written = write_case_tree(args.generate_case_only, files)
        print(f"Generated OpenFOAM 14 case tree ({len(written)} files) at {args.generate_case_only}")
        return

    if args.smoke:
        default_smoke_out = Path(tempfile.gettempdir()) / "openfoam_smoke_receipt.json"
        smoke_out = args.out if args.out is not None else default_smoke_out
        if smoke_out.resolve() == OUT_JSON.resolve():
            parser.error(
                f"--smoke must not overwrite cached surrogate {OUT_JSON}; provide a separate --out path"
            )
        try:
            row = _run_single_case(
                "land_rack",
                2.0,
                T_GROUND_LAND_K,
                0.85,
                native=args.native,
                end_time=SMOKE_END_TIME,
                write_interval=SMOKE_WRITE_INTERVAL,
            )
        finally:
            _cleanup_case_base(WSL_CASE_BASE, native=args.native)

        if row["cells"] != EXPECTED_BLOCKMESH_CELLS:
            raise RuntimeError(
                f"Expected {EXPECTED_BLOCKMESH_CELLS} blockMesh cells, got {row['cells']}"
            )
        smoke_payload = {
            "mode": "smoke",
            "solver": "OpenFOAM 14 (foamRun -solver fluid, steady kOmegaSST, heRhoThermo ideal gas air, 28-deg tilted PV)",
            "native": bool(args.native),
            "end_time": SMOKE_END_TIME,
            "domain_m": {"x": [-4.0, 10.0], "y": [0.0, Y_TOP_M], "tilt_deg": TILT_DEG, "chord_m": PANEL_CHORD_M},
            **row,
        }
        smoke_out.parent.mkdir(parents=True, exist_ok=True)
        smoke_raw = json.dumps(smoke_payload, indent=2) + "\n"
        smoke_out.write_bytes(smoke_raw.encode("utf-8"))
        smoke_sha = hashlib.sha256(smoke_raw.encode("utf-8")).hexdigest()[:16]
        print(
            f"[OpenFOAM14 smoke] cells={row['cells']} q_top={row['q_panel_top_w_m2']} "
            f"q_bot={row['q_panel_bottom_w_m2']} h_conv={row['h_conv_total_w_m2k']} W/m2K "
            f"-> {smoke_out} (sha256={smoke_sha}...)"
        )
        return

    t_all = time.perf_counter()
    h_nat = _natural_convection_h_2side()
    results_by_surface: dict[str, Any] = {}
    out_path = args.out if args.out is not None else OUT_JSON

    if args.recompute_from_cache:
        cached = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        prev_wall_s = float(cached.get("total_wall_s", 0.0))
        cell_count = int(cached.get("cells", 5910))
        for surface, t_ground, h_clear in (
            ("land_rack", T_GROUND_LAND_K, 0.85),
            ("floating_pv", T_WATER_FPV_K, 0.25),
        ):
            cases = cached["surfaces"][surface]["cases"]
            results_by_surface[surface] = _fit_surface_surrogate(t_ground, h_clear, cases, h_nat)
        wall_s = prev_wall_s
    else:
        cell_count = EXPECTED_BLOCKMESH_CELLS
        try:
            for surface, t_ground, h_clear in (
                ("land_rack", T_GROUND_LAND_K, 0.85),
                ("floating_pv", T_WATER_FPV_K, 0.25),
            ):
                cases = []
                for v in WIND_SPEEDS_MS:
                    row = _run_single_case(surface, v, t_ground, h_clear, native=args.native)
                    cell_count = int(row["cells"])
                    cases.append(row)
                    print(
                        f"[OpenFOAM14 28deg {surface} U={v:.1f}m/s] step={row['final_step']} "
                        f"cells={row['cells']} q_top={row['q_panel_top_w_m2']} "
                        f"q_bot={row['q_panel_bottom_w_m2']} "
                        f"h_conv={row['h_conv_total_w_m2k']} + h_rad={row['h_rad_eff_w_m2k']} W/m2K ({row['elapsed_s']}s)"
                    )
                results_by_surface[surface] = _fit_surface_surrogate(t_ground, h_clear, cases, h_nat)
        finally:
            _cleanup_case_base(WSL_CASE_BASE, native=args.native)
        wall_s = round(time.perf_counter() - t_all, 2)

    payload = {
        "solver": "OpenFOAM 14 (foamRun -solver fluid, steady kOmegaSST, heRhoThermo ideal gas air, 28-deg tilted PV)",
        "domain_m": {"x": [-4.0, 10.0], "y": [0.0, Y_TOP_M], "tilt_deg": TILT_DEG, "chord_m": PANEL_CHORD_M},
        "cells": cell_count,
        "t_amb_c": round(T_AMB_K - 273.15, 2),
        "t_sky_c": round(T_SKY_K - 273.15, 2),
        "t_panel_c": round(T_PANEL_K - 273.15, 2),
        "natural_convection_h_w_m2k": round(h_nat, 3),
        "thermal_absorptance_factor": round(ABSORPTANCE_THERMAL_FRAC, 4),
        "total_wall_s": wall_s,
        "surfaces": results_by_surface,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2) + "\n"
    out_path.write_bytes(raw.encode("utf-8"))
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    print(f"Saved OpenFOAM 14 28-deg surrogate table to {out_path} (sha256={sha}...) in {wall_s}s")


if __name__ == "__main__":
    main()
