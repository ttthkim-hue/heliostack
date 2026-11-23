# AI Usage & Transparency Disclosure (`HelioStack` v0.1.0)

This disclosure follows the **NLnet Foundation Policy on the use of Generative Artificial Intelligence**.

## 1. Runtime Guarantee (0% Generative AI)
- `heliostack` (`src/heliostack/` and `docs/index.html`) executes **100% deterministically on CPU** using analytical photovoltaic physics (`pvlib`), vectorized 3D ray-box geometry (`numpy`), convective/floating thermal energy balances, sparse linear programming (`scipy.optimize.linprog` via HiGHS), and cryptographic checksums (`RO-Crate 1.1` + `SHA-256`).
- Zero generative AI, LLMs, closed neural inference endpoints, or external paid APIs are called during validation, simulation, optimization, or audit generation.

## 2. Software Engineering Disclosure
- During initial v0.1.0 scaffolding (module structure, fixture creation, and test boilerplate), AI coding assistance was used under human architecture design, physical equation selection, and code review.
- Every physical equation, equipment parser guard, LP conservation constraint, and European Commission `PVGIS v5.3` cross-check was independently verified by deterministic unit/integration tests (`pytest --cov`) and CLI/benchmark runs on public data.

## 3. Data & IP Separation Statement
- All weather benchmarks rely strictly on public European Commission **PVGIS v5.3** data, public textbook single-diode/inverter equipment fixtures, and public reference geometries. Zero proprietary commercial vendor files or confidential institutional data are included.
