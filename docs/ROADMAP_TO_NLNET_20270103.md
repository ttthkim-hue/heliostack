# HelioStack — 41-Day Execution Schedule to NLnet Restack (`2027-01-03 12:00 CET` Deadline)

- **Target Programme:** NLnet **Restack** (`https://nlnet.nl/restack/`, €5,000–€50,000, deadline `2027-01-03 12:00 CET` / `20:00 KST`) + **NREN** (`https://nlnet.nl/nren/`)
- **Funding Target & Effort:** **`€42,000`** (`600 hrs × €70/hr`, realistic `12 hrs/week` [`3 hrs × 4 days/wk`] over 12 months; `€0` hardware capex, `€0` commercial AI subscriptions) — `AGPL-3.0-or-later` (`M1 €10k / M2 OpenFOAM 3D Flagship €16k / M3 €10k / M4 €6k`)
- **Passing Bar:** `> 5.0 / 7.0` weighted score (`Technical Merit 30% + Strategic Relevance 40% + Value for Money 30%`)

---

## Strategic Alignment: Open Internet Stack & Citizen Renewable Energy Democratization

Distributed solar PV and `LiFePO4` battery storage cannot scale fast enough if trustworthy yield, shading, thermal, and curtailment engineering remains gated behind Windows-only proprietary binaries (`PVsyst`, `PV*SOL`, `HOMER Pro`) and closed cloud SaaS (`HelioScope`) designed primarily for utilities and large EPCs.

`HelioStack` directly advances **NLnet's Open Internet Stack** mission by returning verifiable energy engineering and data sovereignty to **individuals, households, citizen energy cooperatives, small installers, and graduate researchers**:
- **Beyond Governments & Utilities:** Lowers the barrier from commercial desktop licenses to `pip install heliostack` and zero-install client-side browser simulation (`v0.3.1` live static workbench today -> `M4` full **WebAssembly / WebGL** CAD & household/community sizing in `v1.0`).
- **Open Standards & Zero Cloud Lock-In:** Couples open European data feeds (**EU PVGIS v5.3**, **Copernicus GLO-30 DEM**), reproducible **OpenFOAM** CFD thermal physics, sparse **HiGHS** dispatch LP, and cryptographically signed **`RO-Crate 1.1` + `SHA-256`** audit bundles that run `100%` deterministically on local CPU (`0%` generative AI at runtime).
- **Anti-Enclosure Guarantee (`AGPL-3.0-or-later`):** Ensures OpenFOAM CHT atlases, partial-shading solvers, and community `.PAN`/`.OND` checks remain permanently free and open—never enclosed into closed SaaS paywalls.

---

## Brutal Gap Audit Progression (`v0.1.0` -> `v0.2.0` -> `v0.3.1` Pre-Grant Peak, `AGPL-3.0`)
| Criterion (7-Point Scale) | Weight | v0.1.0 | v0.2.0 | v0.3.1 Now | Why & What Remains Before `2027-01-03` | Target |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **Technical Merit** | 30% | `4.6` | `5.5` | **`6.0 / 7`** | **OpenFOAM 14** 28° tilted PV 8-case RANS + Churchill-Chu surrogate, **EU Cyprus** 1-yr telemetry (`Tmod R²=0.9705`, `DC R²=0.9887`), **US PVDAQ #2107**, **Copernicus DEM** Alpine horizon, and `pvlib ModelChain` (`<0.7%` delta) DONE. Technical PoC ceiling reached! | **6.1 / 7** |
| **Strategic Relevance (`Restack`)** | 40% | `4.9` | `5.2` | **`5.6 / 7`** | Explicit `v0.3.1 (AGPL-3.0) vs v1.0` scope prevents SaaS enclosure and extends bankable PV+ESS modeling from utility silos to individuals, citizen energy communities, and small installers; GitHub + PyPI + Web Demo are live, **awaiting 2–3 external researcher feedback threads before submission**. | **6.1 / 7** |
| **Value for Money** | 30% | `5.0` | `5.5` | **`5.8 / 7`** | Sharp pre-grant PoW (`v0.3`) vs NLnet-funded engineering milestones (`v1.0` M1–M4, `€42k`) eliminates any retroactive-funding ambiguity. | **6.0 / 7** |
| **Weighted Total** | **100%** | `4.84` | `5.38` | **`5.70 / 7`** | **Well above `5.0` bar (`~45–52%` odds upon immediate public launch; `0%` while private)** -> public release + EU feedback unlocks **`6.0+ / 7` (`~55–65%`)**! | **6.07 / 7** |

---

## Pre-Grant Prototype (`v0.3.1` Done, `AGPL-3.0`) vs NLnet Funded Work (`v1.0` M1–M4, `€42,000` / 600h)

NLnet funds **future open-source engineering deliverables** (not retroactive reimbursement). Keeping `v0.3.1` sharp yet clearly bounded ensures `v0.3.1` serves strictly as verified Proof-of-Work while `€42,000` (`600 hrs @ €70/hr`, `12 hrs/week × 50 weeks`) delivers the OpenFOAM-centered industrial, citizen-energy & academic stack:

| Workstream | Already Verified Pre-Grant (`v0.3.1` Proof-of-Work) | Funded Future Deliverables (`v1.0` via NLnet `€42,000`) |
| :--- | :--- | :--- |
| **3D Geometry & Electrical Stringing** | Rigid axis-aligned box shading + lumped array mismatch | **M1 (€10k · 143h · Mos 1–3):** Arbitrary CAD roof/terrain obstacles, module bypass-diode partial-shading I-V curves, single/dual-axis trackers |
| **OpenFOAM Thermal Physics (Flagship)** | 2D tilted single-module steady RANS (`5,910` cells) + Churchill-Chu fit | **M2 (€16k · 228h · Mos 4–7):** Full 3D multi-row turbulent Conjugate Heat Transfer (CHT) OpenFOAM atlas covering BIPV ventilated facades, agrivoltaics & wave-tilted FPV + reproducible graduate research benchmark paper pack |
| **Storage, Grid & Uncertainty** | 1-year deterministic HiGHS dispatch LP + heuristic `4.4%` P90 | **M3 (€10k · 143h · Mos 8–10):** 25-year probabilistic Monte-Carlo bankability (`P50/P90/P99`), LiFePO4 calendar/cycle SEI aging & European ENTSO-E negative-price MILP |
| **Open Distribution & Citizen UX** | Local Python CLI + static browser preview dashboard | **M4 (€6k · 86h · Mos 11–12):** Zero-install client-side **WebAssembly/WebGL** browser CAD & citizen/home PV+ESS workbench (full local data sovereignty), open community `.PAN`/`.OND` registry, Debian/Nix/`PyPI` packaging & WCAG accessibility audit |

---

## Author Open-Science & Thermo-Fluid Track Record

- **Author:** **Tae-Hyung Kim** ([ORCID `0009-0003-5047-7501`](https://orcid.org/0009-0003-5047-7501) · [GitHub `@ttthkim-hue`](https://github.com/ttthkim-hue) · M.S. Materials Engineering, Pusan National University `2025`; B.S. Materials Engineering, University of Ulsan `2020`)
- **Open-Source CFD & Reproducibility Track Record:**
  - [`taichi_lbm_ref_gyroid`](https://github.com/ttthkim-hue/taichi_lbm_ref_gyroid) — GPU-accelerated (`Taichi`) D3Q19 MRT Lattice Boltzmann Method (MRT-LBM) porous-media CFD solver + Bayesian Optimization (`50`-point Pareto front, Forchheimer regression, OpenSCAD/STL/STEP geometry exchange).
  - [`openfair-mat`](https://github.com/ttthkim-hue/openfair-mat) — `MIT`-licensed pure Python standard-library physical-integrity, schema, and `RO-Crate 1.1` + `SHA-256` reproducibility validator (`openfair-check`) for open scientific datasets (Zenodo, NOMAD FAIRmat, Materials Project).
- **Peer-Reviewed Track Record:** `14` peer-reviewed journal articles indexed on [ORCID `0009-0003-5047-7501`](https://orcid.org/0009-0003-5047-7501) (`7` sole first-author, `1` co-first author, `6` co-author), plus `1` 2022 Crossref/OpenAlex-verified co-authored article (`15` total), spanning modeling, thermo-fluid/heat-recovery systems, and materials engineering (`10.1016/j.mtcomm.2026.115941`, `10.7844/kirr.2026.35.2.30`, `10.2109/jcersj2.25126`, `10.1016/j.apt.2024.104729`, `10.3390/ma17143463`).

---

## Final Non-Technical Launch Sequence to `2027-01-03`

1. **Public GitHub + `PyPI` Release (`v0.3.1` `AGPL-3.0` Live):** Push verified zero-secret repository (`gitleaks` clean) with GitHub Pages live demo (`ttthkim-hue/heliostack`) and installable `pip install heliostack` package.
2. **European Open-Energy Community Feedback (`Social Proof`):** Present OpenFOAM + EU Cyprus + Copernicus benchmarks on **OpenMod**, **pvlib Discussions**, and **Fosstodon**; resolve 2–3 real external tester edge cases.
3. **100% Human-Written Proposal (`12/25 – 2027-01-02`, NLnet GenAI Policy v2.0 Compliant):** Author an original, human-written plain-English Restack (+ independent NREN scope check) submission citing the public repo, PyPI stats, M1–M4 non-retroactive deliverables, and external tester feedback; submit before `2027-01-03 12:00 CET`.
