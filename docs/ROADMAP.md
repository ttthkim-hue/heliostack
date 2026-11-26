# HelioStack — Open-Source Engineering Roadmap (`v0.3.2` -> `v1.0`)

`HelioStack` (`AGPL-3.0-or-later`) is an open-source Python, OpenFOAM, and open-standards solar PV + storage engineering workbench built to provide deterministic, cryptographically reproducible alternatives to closed commercial software (`PVsyst`, `PV*SOL`, `HOMER Pro`, `HelioScope`).

## Design Principles

- **100% Deterministic CPU Execution:** Zero generative AI or opaque SaaS APIs at simulation runtime.
- **Open Standards & Provenance:** Couples EU PVGIS v5.3, Copernicus GLO-30 DEM, upstream `pvlib-python`, reproducible OpenFOAM 14 CFD cases, sparse `HiGHS` LP dispatch, and `RO-Crate 1.1` + `SHA-256` verification bundles.
- **Local Data Sovereignty:** Runs offline via Python CLI or directly client-side in the browser (`docs/index.html`) with no backend lock-in.

## Engineering Scope: Verified Baseline (`v0.3.2`) vs. Planned Milestones (`v1.0`)

| Workstream | Current Verified Baseline (`v0.3.2`, `AGPL-3.0`) | Planned Open-Source Deliverable (`v1.0`, `AGPL-3.0`) |
| :--- | :--- | :--- |
| **3D Geometry & Electrical Stringing** | Vectorized 3D ray-box obstacles + 36-azimuth Copernicus DEM horizon & diffuse SVF | **M1:** Arbitrary CAD roof/terrain obstacles (`glTF`/`OBJ`), module bypass-diode partial-shading `I-V` curves, single/dual-axis backtracking trackers |
| **OpenFOAM Thermal Physics (Flagship)** | 2D tilted single-module steady RANS (`5,910` cells) + Churchill-Chu convective surrogate + OpenFOAM 14 smoke CI | **M2:** Full 3D multi-row turbulent Conjugate Heat Transfer (CHT) OpenFOAM atlas covering BIPV ventilated facades, agrivoltaics & wave-tilted FPV targeting `< 2.5 °C` outdoor `RMSE`, plus reproducible graduate benchmark pack |
| **Storage, Grid & Uncertainty** | 1-year deterministic HiGHS curtailment-recovery LP + `4.4%` P90 | **M3:** 25-year probabilistic Monte-Carlo bankability (`P50`/`P90`/`P99`), `LiFePO4` calendar/cycle SEI aging & European `ENTSO-E` hourly/negative-price MILP |
| **Open Distribution & Citizen UX** | Local Python CLI + static browser workbench (`0.8 kWp` / `6 kWp` / `100 kWp` / custom) | **M4:** Client-side WebAssembly (`Pyodide`) + WebGL 3D scene editor, community-verified `.PAN`/`.OND` database, Debian/Nix/PyPI packaging & WCAG accessibility audit |
