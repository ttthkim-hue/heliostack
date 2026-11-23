# Contributing to HelioStack (`AGPL-3.0-or-later`)

Thank you for helping strengthen open, reproducible photovoltaic and thermo-fluid engineering for researchers, graduate students, and open-energy labs.

## License & Governance
- **Open-Source License:** All contributions are licensed under the **GNU Affero General Public License v3.0 or later ([`LICENSE`](./LICENSE))**. By submitting a pull request, you agree to release your contribution under `AGPL-3.0-or-later`.
- **Maintainer Governance:** Official merges to `main`, release tags, and PyPI package publications (`publish-pypi.yml`) are reviewed, approved, and managed solely by the copyright holder (`Tae-Hyung Kim`).
- **Academic & Commercial Use:** Research, academic, and open-source use is permanently free under `AGPL-3.0-or-later`. Networked hosted services running modified versions must provide corresponding source under `AGPL-3.0`. Parties requiring separate closed commercial dual-licensing may contact the copyright holder independently.

## Development Setup

```bash
git clone https://github.com/ttthkim-hue/heliostack.git
cd heliostack
pip install -e ".[dev]"
```

## Verification Before Opening a Pull Request

Every pull request must keep runtime execution **100% deterministic CPU** (`0%` generative AI calls at runtime) and pass all local checks:

```bash
ruff check src tests benchmarks openfoam
pytest --cov=heliostack
```

- Please include sanitized public fixtures or cite open DOIs when adding thermal, terrain, or telemetry validation cases.
- Use the issue templates under `.github/ISSUE_TEMPLATE/` for OpenFOAM 3D CHT benchmark requests and `.PAN`/`.OND`/DEM edge cases.
