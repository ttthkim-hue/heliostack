# HelioStack — 41-Day Execution Schedule to NLnet Restack (`2027-01-03 12:00 CET` Deadline)

- **Target Programme:** NLnet **Restack** (`https://nlnet.nl/restack/`, €5,000–€50,000, deadline `2027-01-03 12:00 CET` / `20:00 KST`) + **NREN** (`https://nlnet.nl/nren/`)
- **Funding Target:** **`€42,000`** across 4 deterministic open-source engineering milestones (M1 €10k / M2 €12k / M3 €12k / M4 €8k; €0 hardware capex, €0 commercial AI subscriptions)
- **Passing Bar:** `> 5.0 / 7.0` weighted score (`Technical Merit 30% + Strategic Relevance 40% + Value for Money 30%`)

---

## Brutal Gap Audit Baseline (`2026-11-23` v0.1.0)
| Criterion (7-Point Scale) | Weight | v0.1 Score | Why Not 6+ Yet (Exact Technical Gaps) | Target Score by `2027-01-03` |
| :--- | :---: | :---: | :--- | :---: |
| **Technical Merit** | 30% | **4.6 / 7** | Strong 8,760-hr PV+ESS+3D shading core, but still uses lumped analytical water-coupling instead of validated **OpenFOAM** CFD lookup tables, lacks **Copernicus DEM GeoTIFF** horizon auto-loading, and has zero real-plant SCADA/open measured telemetry calibration yet. | **5.9 / 7** |
| **Strategic Relevance (`Restack`)** | 40% | **4.9 / 7** | Cleanly replaces `PVsyst`+`HOMER`+`HelioScope` with 0% GenAI and uses `PVGIS`+`RO-Crate`, but repo is still local-only (not public on GitHub/`PyPI`, `0` external users/contributors, and no explicit EU `NREN`/energy-coop adoption proof). | **6.1 / 7** |
| **Value for Money** | 30% | **5.0 / 7** | Strong v0.1 PoW already built in advance; zero equipment capex keeps budget compliant, but M1–M4 milestone work-hours and EU open-standards deliverables need sharper line-item justification. | **5.8 / 7** |
| **Weighted Total** | **100%** | **4.84 / 7** | **Right below `5.0` pass bar today (~20–25% odds if submitted raw today)** -> closes ALL 5 gaps in Weeks 1–5 below! | **5.95 / 7 (~50%+ realistic tier)** |

---

## 41-Day Weekly Sprint Plan (`2026-11-24` -> `2027-01-03`)

1. **Week 1 (`11/24 – 11/30`) — Public Release & Open Data Telemetry Benchmark:**
   - Publish `HelioStack` v0.1.0 to public GitHub (`ttthkim-hue/heliostack`) + GitHub Pages live simulator (`https://ttthkim-hue.github.io/heliostack/`) + `PyPI` `0.1.x`.
   - Benchmark against at least **2 real measured open PV datasets** (e.g., NREL PVDAQ public sites / Zenodo open plant telemetry) beyond synthetic TMY.
2. **Week 2 (`12/01 – 12/08`) — Copernicus DEM Horizon + Real PVsyst Sample Parity (`v0.2.0`):**
   - Implement automatic **Copernicus GLO-30 DEM / PVGIS horizon** elevation ingestion (`--dem` / automatic API horizon fetch) for genuine terrain shading.
   - Add automated 1:1 loss-waterfall parity comparison table against documented reference cases.
3. **Week 3 (`12/09 – 12/16`) — Reproducible OpenFOAM Convective & Floating-PV Thermal Case (`v0.2.5`):**
   - Package a minimal deterministic **`OpenFOAM` (`buoyantSimpleFoam` / `chtMultiRegionSimpleFoam`) 2D/3D parametric sweep** over wind speed, row spacing (`GCR`), and water cooling boundary conditions -> derive verified open surrogate thermal curves usable on CPU in `< 1 ms`.
4. **Week 4 (`12/17 – 12/24`) — European Open-Energy Community Feedback & Issue Polish:**
   - Share live demo & benchmarks cleanly on **OpenMod**, **pvlib/GitHub Discussions**, and **Fosstodon**; collect external feedback/stars/testers (`Social Proof`) and resolve reported edge cases.
5. **Week 5 (`12/25 – 2027-01-02`) — Human-Written Proposal & Pre-Deadline Submission:**
   - Author 100% human-written plain-English **NLnet Restack + NREN** proposal (strictly 0% LLM translation/drafting) referencing live GitHub release, PyPI downloads, external tester quotes, and Copernicus/OpenFOAM verification.
   - Submit **24 hours before `2027-01-03 20:00 KST` (`12:00 CET`)** deadline!
