# HelioStack — 41-Day Execution Schedule to NLnet Restack (`2027-01-03 12:00 CET` Deadline)

- **Target Programme:** NLnet **Restack** (`https://nlnet.nl/restack/`, €5,000–€50,000, deadline `2027-01-03 12:00 CET` / `20:00 KST`) + **NREN** (`https://nlnet.nl/nren/`)
- **Funding Target:** **`€42,000`** across 4 deterministic open-source engineering milestones (M1 €10k / M2 €12k / M3 €12k / M4 €8k; €0 hardware capex, €0 commercial AI subscriptions)
- **Passing Bar:** `> 5.0 / 7.0` weighted score (`Technical Merit 30% + Strategic Relevance 40% + Value for Money 30%`)

---

## Brutal Gap Audit Progression (`v0.1.0` -> `v0.2.0` Verified Offline)
| Criterion (7-Point Scale) | Weight | v0.1.0 | v0.2.0 Now | Remaining Gap to `6.0+` by `2027-01-03` | Target |
| :--- | :---: | :---: | :---: | :--- | :---: |
| **Technical Merit** | 30% | `4.6 / 7` | **`5.5 / 7`** | Copernicus DEM (Innsbruck/Bolzano/Zermatt `MAE 1.25–1.57°`), US DOE PVDAQ #2107 892.8 kWp real telemetry (`R²=0.9101`, `MBE=+3.81%`), & `pvlib ModelChain` (`<0.7%` delta) DONE. Still missing reproducible **OpenFOAM** CFD thermal table & a 2nd European metered plant check. | **6.0 / 7** |
| **Strategic Relevance (`Restack`)** | 40% | `4.9 / 7` | **`5.2 / 7`** | Zero-vendor Copernicus+OEDI+PVGIS parity strengthens anti-lock-in case, **but repo is still unpublished (0 public GitHub stars, 0 PyPI downloads, 0 EU energy-coop/tester feedback yet)**. | **6.1 / 7** |
| **Value for Money** | 30% | `5.0 / 7` | **`5.5 / 7`** | Working verified engine + real telemetry benchmark already shipped upfront with zero grant funds; just needs crisp M1–M4 work-hour breakdown against `€42,000`. | **5.9 / 7** |
| **Weighted Total** | **100%** | `4.84 / 7` | **`5.38 / 7`** | Clears `5.0` passing bar (`~35–42%` realistic selection odds once made public; `0%` while local-only) -> Phase 3 unlocks **`55–60%+` tier**! | **6.01 / 7** |

---

## Remaining Sprint Plan to `2027-01-03`

1. **Completed Ahead of Schedule (`v0.2.0`):** Copernicus 30m DEM & ESRI `.asc` horizon ray-casting + diffuse SVF, US DOE / NREL PVDAQ #2107 (`892.8 kWp`, 2024 `3,255` daylight operating hrs) field meter validation, and canonical `pvlib ModelChain` + 12-step PVsyst loss-tree parity.
2. **Phase 3A — Reproducible OpenFOAM Convective & Floating-PV Thermal Case (`v0.2.5`):**
   - Package a minimal deterministic **`OpenFOAM` (`buoyantSimpleFoam` / `chtMultiRegionSimpleFoam`) 2D/3D parametric sweep** over wind speed, row spacing (`GCR`), and water cooling boundary conditions -> derive verified open surrogate thermal curves usable on CPU in `< 1 ms`, plus add a European/2nd metered plant check if available.
3. **Phase 3B — Public GitHub / PyPI Release & European Tester Feedback (`v0.3.0`):**
   - Publish `ttthkim-hue/heliostack` cleanly with zero secrets (`gitleaks`), GitHub Pages live workbench, and `PyPI` package.
   - Share live demo & benchmarks cleanly on **OpenMod**, **pvlib/GitHub Discussions**, and **Fosstodon**; gather real external tester feedback (`Social Proof`).
4. **Phase 3C — 100% Human-Written Proposal & Pre-Deadline Submission (`12/25 – 2027-01-02`):**
   - Author 100% human-written plain-English **NLnet Restack + NREN** proposal referencing live GitHub release, PyPI downloads, external tester quotes, PVDAQ validation, and Copernicus/OpenFOAM verification.
   - Submit **24 hours before `2027-01-03 20:00 KST` (`12:00 CET`)** deadline!
