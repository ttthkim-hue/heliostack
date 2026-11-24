# OpenFOAM 14 Canonical Tilted PV Convective & Floating-PV Thermal Case

This directory contains a reproducible, AGPL-3.0-licensed 2D steady-state RANS (`kOmegaSST`) CFD sweep built for **OpenFOAM 14 (`foamRun -solver fluid`)** using structured 8-block `blockMesh` geometry around a **`28°`-tilted `2.0 m` photovoltaic module** in crosswind over:

1. **Sunlit Land Rack (`land_rack`):** `0.85 m` ground clearance above sunlit soil at `+35 °C`, outdoor freestream air `+25 °C` (`10%` turbulence intensity), heated PV module `+50 °C`.
2. **Floating PV Pontoon (`floating_pv`):** `0.25 m` pontoon clearance above reservoir water at `+21 °C`, outdoor freestream air `+25 °C`, heated PV module `+50 °C`.

Sweeping wind speeds `U = 1.0, 2.0, 4.0, 6.0 m/s` extracts `panelTop` and `panelBottom` area-averaged `wallHeatFlux`, pairs it with asymmetric tilted sky (`Tamb - 12 K`) and ground/water longwave radiation (`eps = 0.85`), and derives calibrated Faiman coefficients (`u0_cfd`, `u1_cfd`) cached deterministically in `fixtures/thermal/openfoam14_pv_thermal_surrogate.json`.

## Usage

### 1. Full 8-Case Sweep (WSL2 `Ubuntu-24.04` or Native Linux)

```bash
# Windows host -> WSL2 Ubuntu-24.04 (/opt/openfoam14)
python openfoam/run_openfoam_pv_sweep.py

# Native Linux / Docker / GitHub Actions runner
python3 openfoam/run_openfoam_pv_sweep.py --native

# Recompute surrogate fits strictly from the cached JSON fixture
python openfoam/run_openfoam_pv_sweep.py --recompute-from-cache
```

### 2. Fast Smoke Run (`--smoke`)

Runs one representative steady case (`land_rack`, `U = 2.0 m/s`, `clearance = 0.85 m`, `endTime = 80` iterations), checks `blockMesh` + `checkMesh`, verifies finite `wallHeatFlux` and positive convective heat transfer `h_conv_total_w_m2k`, and writes a separate smoke receipt JSON without altering `fixtures/thermal/openfoam14_pv_thermal_surrogate.json`:

```bash
python3 openfoam/run_openfoam_pv_sweep.py --native --smoke --out /tmp/openfoam_smoke_receipt.json
```

### 3. Offline Case Dictionary Export (`--generate-case-only`)

Writes the deterministic OpenFOAM 14 case dictionary tree (`0/`, `constant/`, `system/blockMeshDict`, `system/controlDict`, `system/fvSchemes`, `system/fvSolution`, `system/functions`) to a target directory without invoking OpenFOAM binaries:

```bash
python openfoam/run_openfoam_pv_sweep.py --generate-case-only /tmp/pv_case_preview
```

### 4. Docker Container (`openfoam/Dockerfile`)

Builds an Ubuntu 24.04 container with official OpenFOAM 14 packages (signed via `/usr/share/keyrings/openfoam.gpg`) and defaults to running the `--native --smoke` check:

```bash
docker build -t heliostack-openfoam14 openfoam
docker run --rm heliostack-openfoam14
```

Note: The sweep runs strictly single-core (`nice -n 19`). Live CI verification on `ubuntu-24.04` uses the exact 8-block mesh in `_block_mesh_dict` (`BLOCK_NX = (18, 40, 34)`, `BLOCK_NY = (28, 3, 36)` = **6,044 cells** verified via `checkMesh`), while `fixtures/thermal/openfoam14_pv_thermal_surrogate.json` (which retains `5,910` cells from the initial surrogate metadata) is preserved unchanged for regression continuity.
