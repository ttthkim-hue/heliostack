# AI Usage & Transparency Disclosure (`HelioStack` v0.3.2)

This disclosure follows the **NLnet Foundation Policy on the use of Generative Artificial Intelligence**.

## 1. Runtime Guarantee (0% Generative AI)
- `heliostack` (`src/heliostack/` and `docs/index.html`) executes **100% deterministically on CPU** using analytical photovoltaic physics (`pvlib`), vectorized 3D ray-box geometry (`numpy`), Copernicus DEM terrain horizon ray-casting, OpenFOAM 14 CFD-calibrated thermal balances, sparse linear programming (`scipy.optimize.linprog` via HiGHS), and cryptographic checksums (`RO-Crate 1.1` + `SHA-256`).
- Zero generative AI, LLMs, closed neural inference endpoints, or external paid APIs are called during validation, simulation, optimization, or audit generation.

## 2. Software Engineering Disclosure
- During scaffolding and verification sprints (v0.1.0 to v0.3.2), AI coding assistance was used under human architecture design, physical model formulation, and code audit. All releases and NLnet-funded milestones remain pure AGPL-3.0-or-later open source.
- Every physical equation, equipment parser guard, LP conservation constraint, OpenFOAM 14 `foamRun` CFD case (`checkMesh` clean, `5,910` cells), `pvlib ModelChain` parity check, US DOE / NREL PVDAQ #2107 check, and European Cyprus PHAETHON testbed check was executed and verified deterministically via `ruff`, `pytest --cov`, and SHA-256 manifests.

## 3. Open Data Provenance & Attribution
- **Solar & Horizon Weather:** European Commission **PVGIS v5.3** (`SARAH3`, `ERA5`, `printhorizon`, `PVcalc`) and **Copernicus GLO-30 DEM** via Open-Meteo Elevation API.
- **US Utility Telemetry:** Public **US DOE / NREL PVDAQ #2107** (`OEDI`) 2024 hourly data.
- **European Field Telemetry:** University of Cyprus **PHAETHON CoE** outdoor testbed 1-year dataset (`CC-BY-4.0`, DOI: `10.5281/zenodo.10816826`).
- Zero proprietary commercial vendor files or confidential institutional data are included.
