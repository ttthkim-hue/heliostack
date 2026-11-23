# OpenFOAM 14 Canonical Tilted PV Convective & Floating-PV Thermal Case

This directory contains a reproducible, MIT-licensed 2D steady-state RANS (`kOmegaSST`) CFD sweep built for **OpenFOAM 14 (`foamRun -solver fluid`)** using structured 8-block `blockMesh` geometry around a **`28°`-tilted `2.0 m` photovoltaic module** in crosswind over:

1. **Sunlit Land Rack (`land_rack`):** `0.85 m` ground clearance above sunlit soil at `+35 °C`, outdoor freestream air `+25 °C` (`10%` turbulence intensity), heated PV module `+50 °C`.
2. **Floating PV Pontoon (`floating_pv`):** `0.25 m` pontoon clearance above reservoir water at `+21 °C`, outdoor freestream air `+25 °C`, heated PV module `+50 °C`.

Sweeping wind speeds `U = 1.0, 2.0, 4.0, 6.0 m/s` extracts `panelTop` and `panelBottom` area-averaged `wallHeatFlux`, pairs it with asymmetric tilted sky (`Tamb - 12 K`) and ground/water longwave radiation (`eps = 0.85`), and derives calibrated Faiman coefficients (`u0_cfd`, `u1_cfd`) cached deterministically in `fixtures/thermal/openfoam14_pv_thermal_surrogate.json`.

```bash
python openfoam/run_openfoam_pv_sweep.py
```

Note: The sweep runs strictly single-core (`nice -n 19`) across ~5,910 cells (~1.5 minutes total runtime).
