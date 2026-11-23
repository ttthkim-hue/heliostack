# HelioStack — 41-Day Execution Schedule to NLnet Restack (`2027-01-03 12:00 CET` Deadline)

- **Target Programme:** NLnet **Restack** (`https://nlnet.nl/restack/`, €5,000–€50,000, deadline `2027-01-03 12:00 CET` / `20:00 KST`) + **NREN** (`https://nlnet.nl/nren/`)
- **Funding Target:** **`€42,000`** across 4 deterministic open-source engineering milestones (M1 €10k / M2 €12k / M3 €12k / M4 €8k; €0 hardware capex, €0 commercial AI subscriptions)
- **Passing Bar:** `> 5.0 / 7.0` weighted score (`Technical Merit 30% + Strategic Relevance 40% + Value for Money 30%`)

---

## Brutal Gap Audit Progression (`v0.1.0` -> `v0.2.0` -> `v0.3.0` Pre-Grant Peak)
| Criterion (7-Point Scale) | Weight | v0.1.0 | v0.2.0 | v0.3.0 Now | Why & What Remains Before `2027-01-03` | Target |
| :--- | :---: | :---: | :---: | :---: | :--- | :---: |
| **Technical Merit** | 30% | `4.6` | `5.5` | **`6.0 / 7`** | **OpenFOAM 14** 28° tilted PV 8-case RANS + Churchill-Chu surrogate, **EU Cyprus** 1-yr telemetry (`Tmod R²=0.9705`, `DC R²=0.9887`), **US PVDAQ #2107**, **Copernicus DEM** Alpine horizon, and `pvlib ModelChain` (`<0.7%` delta) DONE. Technical PoC ceiling reached! | **6.1 / 7** |
| **Strategic Relevance (`Restack`)** | 40% | `4.9` | `5.2` | **`5.4 / 7`** | Explicit `v0.3 vs v1.0` open-stack scope proves zero lock-in, **but repo is still local/unpublished (`0` public GitHub users, `0` PyPI installs, `0` external EU tester quotes yet)**. | **6.1 / 7** |
| **Value for Money** | 30% | `5.0` | `5.5` | **`5.8 / 7`** | Sharp pre-grant PoW (`v0.3`) vs NLnet-funded engineering milestones (`v1.0` M1–M4, `€42k`) eliminates any retroactive-funding ambiguity. | **6.0 / 7** |
| **Weighted Total** | **100%** | `4.84` | `5.38` | **`5.70 / 7`** | **Well above `5.0` bar (`~45–52%` odds upon immediate public launch; `0%` while private)** -> public release + EU feedback unlocks **`6.0+ / 7` (`~55–65%`)**! | **6.07 / 7** |

---

## Pre-Grant Prototype (`v0.3.0` Done) vs NLnet Funded Work (`v1.0` M1–M4, `€42,000`)

NLnet funds **future open-source engineering deliverables** (not retroactive reimbursement). Keeping `v0.3.0` sharp yet clearly bounded ensures `v0.3.0` serves strictly as verified Proof-of-Work while `€42,000` delivers the missing industrial stack:

| Workstream | Already Verified Pre-Grant (`v0.3.0` Proof-of-Work) | Funded Future Deliverables (`v1.0` via NLnet `€42,000`) |
| :--- | :--- | :--- |
| **3D Geometry & Electrical Stringing** | Rigid axis-aligned box shading + lumped array mismatch | **M1 (€10k):** Arbitrary CAD roof/terrain obstacles, module bypass-diode partial-shading I-V curves, single/dual-axis trackers |
| **OpenFOAM Thermal Physics** | 2D tilted single-module steady RANS (`5,910` cells) + Churchill-Chu fit | **M2 (€12k):** Full 3D multi-row turbulent Conjugate Heat Transfer (CHT) OpenFOAM atlas covering BIPV ventilated facades, agrivoltaics & wave-tilted FPV |
| **Storage, Grid & Uncertainty** | 1-year deterministic HiGHS dispatch LP + heuristic `4.4%` P90 | **M3 (€12k):** 25-year probabilistic Monte-Carlo bankability (`P50/P90/P99`), LiFePO4 calendar/cycle SEI aging & European ENTSO-E negative-price MILP |
| **Open Distribution & UX** | Local Python CLI + static browser preview dashboard | **M4 (€8k):** Client-side WebAssembly/WebGL browser CAD workbench, open community `.PAN`/`.OND` registry, Debian/Nix/`PyPI` packaging & WCAG accessibility audit |

---

## Final Non-Technical Launch Sequence to `2027-01-03`

1. **Public GitHub + `PyPI` Release (`v0.3.0` Ready Now):** Push verified zero-secret repository (`gitleaks` clean) with GitHub Pages live demo (`ttthkim-hue/heliostack`) and installable `pip install heliostack` package.
2. **European Open-Energy Community Feedback (`Social Proof`):** Present OpenFOAM + EU Cyprus + Copernicus benchmarks on **OpenMod**, **pvlib Discussions**, and **Fosstodon**; resolve 2–3 real external tester edge cases.
3. **100% Human-Written Proposal (`12/25 – 2027-01-02`):** Draft crisp plain-English Restack + NREN proposal citing public repo, PyPI stats, M1–M4 non-retroactive deliverables, and external tester feedback; submit before `2027-01-03 12:00 CET`.
