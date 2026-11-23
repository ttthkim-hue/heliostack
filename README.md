# HelioStack v0.3.0

**Deterministic open-source solar PV, 3D ray-cast & Copernicus DEM terrain shading, OpenFOAM 14 CFD land/Floating-PV thermal, and HiGHS `LiFePO4` ESS optimization workbench with `RO-Crate 1.1` & `SHA-256` audit provenance.**

- **License:** MIT (`100%` OSI-permissive open source; `0%` generative AI or closed vendor APIs at runtime)
- **Live Data, CFD & Dual-Continent Field Validation:**
  1. European Commission **PVGIS v5.3** (`SARAH3` & `ERA5`) hourly TMY & `PVcalc` cross-validation across 4 baseline climates
  2. **Copernicus DEM** 36-azimuth ray-cast terrain horizon vs EU PVGIS `printhorizon` across Innsbruck, Bolzano, and Zermatt (`MAE 1.25–1.57°`)
  3. **OpenFOAM 14 (`foamRun -solver fluid`, steady `kOmegaSST`)** `28°`-tilted PV convective sweep (`5,910` cells, 8 cases) calibrating land vs pontoon Floating-PV cooling
  4. **European Union 1-Year Outdoor Testbed** (**University of Cyprus PHAETHON CoE**, `8,784` full hours, `CC-BY-4.0`): `Tmod RMSE 2.18 °C` (`open_rack R² 0.9705`) / `4.19 °C` (`OpenFOAM 14 R² 0.8906`), full-year DC `R² 0.9887`
  5. Real **892.8 kWp** US utility meter telemetry (**US DOE / NREL PVDAQ #2107**, 2024 `3,255` daylight operating hours, `R² = 0.9101`, `MBE = +3.81%`, `nRMSE = 6.79%`)
  6. Canonical **`pvlib ModelChain`** parity check (`-0.67%` Amsterdam, `+0.31%` Seville) + 12-step PVsyst-style loss tree
- **AI Transparency:** [`AI_DISCLOSURE.md`](./AI_DISCLOSURE.md)
- **NLnet Scope & Roadmap (`2027-01-03`):** [`docs/ROADMAP_TO_NLNET_20270103.md`](./docs/ROADMAP_TO_NLNET_20270103.md)

---

## Why HelioStack?

Commercial Windows-only tools (`PVsyst`, `PV*SOL`, `HOMER Pro`) and closed cloud SaaS (`HelioScope`) lock solar engineering workflows behind proprietary `.PAN`/`.OND` binary/desktop silos, while open libraries (`pvlib`) lack unified Copernicus DEM terrain + 3D obstacle ray-casting, Floating-PV water thermal physics, sparse 8,760-hour ESS curtailment optimization, and cryptographic reproducibility bundles.

`HelioStack` bridges that gap in pure open Python:
1. **Clean-Room Equipment Validation (`.PAN` / `.OND` / JSON):** Enforces physical single-diode & MPPT window invariants (`Vmp < Voc`, `Imp < Isc`, finite metrics, inverter efficiency bounds).
2. **Vectorized 3D Ray-Box, Copernicus DEM & Diffuse SVF:** Evaluates 3D obstacle shading, Copernicus 30m satellite & ASCII ESRI `.asc` DEM 36-azimuth mountain horizon blocking, inter-row shed geometry, and cosine-weighted hemispherical sky-view factors.
3. **Thermal Physics Beyond Single U-Values:** Compares open-rack Faiman baselines against wind-angle convective alleys and lagged water-coupled Floating-PV cooling (`-3.59 °C` to `-5.77 °C` daytime cooling).
4. **8,760-Hour Sparse HiGHS `LiFePO4` Dispatch LP:** Quantifies curtailment recovery under grid export caps with ESS container HVAC auxiliary loads and strict `10^-6 kW` hourly conservation checks.
5. **Reproducible Audit Packaging:** Outputs byte-deterministic `RO-Crate 1.1` (`ro-crate-metadata.json`), `repro-manifest.json` (`SHA-256`), and zero-CDN `bankable_report.html`.

---

## Observed 4-Site EU PVGIS v5.3 Benchmark (`100 kWp`, Verified Offline)

| Location (PVGIS DB) | POA Delta vs PVcalc | Mono Yield vs PVcalc | Land Bifacial (PR) | Floating PV Cooling (Pure Thermal / Net Bifacial) | 3D Obstacle Shade | 65% Cap + 200 kWh ESS Recovery (LP Time) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Amsterdam, NL** (`SARAH3`) | `-0.59%` | `1083.5` vs `1071.6` (`+1.11%`) | `1100.7 kWh/kWp` (`87.3%`) | `-3.59 °C` (`+1.53%` / `-0.68%`) | `15.07%` | `100.0%` of `6,205 kWh` (`0.70 s`) |
| **Munich, DE** (`SARAH3`) | `-1.12%` | `1204.4` vs `1191.5` (`+1.08%`) | `1234.5 kWh/kWp` (`87.2%`) | `-4.30 °C` (`+1.96%` / `-0.22%`) | `13.88%` | `100.0%` of `8,297 kWh` (`0.73 s`) |
| **Seville, ES** (`SARAH3`) | `-1.12%` | `1814.9` vs `1747.8` (`+3.84%`) | `1876.6 kWh/kWp` (`86.3%`) | `-5.77 °C` (`+2.30%` / `+0.38%`) | `11.24%` | `100.0%` of `19,449 kWh` (`0.73 s`) |
| **Busan, KR** (`ERA5`) | `+2.74%` | `1640.1` vs `1550.0` (`+5.82%`) | `1693.2 kWh/kWp` (`89.5%`) | `-4.16 °C` (`+1.53%` / `-0.39%`) | `11.63%` | `100.0%` of `14,690 kWh` (`0.79 s`) |

---

## Phase 2 Validation Highlights (`v0.2.0`)

### 1. Alpine Terrain Shading (Horizon-Free TMY + Sky-Dome SVF)
| Alpine Valley | Elevation | Copernicus vs PVGIS MAE | Flat -> Copernicus Loss | EU PVcalc Terrain Loss | Copernicus vs PVGIS-Hor Delta |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Innsbruck, AT** | `580 m` | `1.28°` | `1537.4 -> 1504.7` (`-2.13%`) | `-1.53%` | `+0.46%` |
| **Bolzano, IT** | `271 m` | `1.25°` | `1624.5 -> 1545.3` (`-4.88%`) | `-4.86%` | `+2.28%` |
| **Zermatt, CH** | `1,610 m` | `1.57°` | `1645.8 -> 1387.2` (`-15.72%`) | `-13.99%` | `+1.98%` |

### 2. Real Utility Meter Telemetry (`US DOE / NREL PVDAQ #2107`, Arbuckle, CA — 2024 Jan–early Nov)
- Plant: `892.8 kWp DC` (`2,880 × 310 W`), `24 × 27.6 kW` (`662.4 kW AC`), 7-year aging factor `0.965`, `3,255` daylight operating hours.
- **Convective Land Model:** Measured `1,221.32 MWh` vs Modeled `1,267.82 MWh` | **`MBE = +3.81%`**, **`nRMSE = 6.79%`**, **`R² = 0.9101`**.
- **Open-Rack Faiman Baseline:** Measured `1,221.32 MWh` vs Modeled `1,268.83 MWh` | `MBE = +3.89%`, `nRMSE = 6.80%`, `R² = 0.9098`.

### 3. Canonical `pvlib ModelChain` Parity (`99.0 kWp` Mono Plant)
- **Amsterdam, NL:** `pvlib = 1,113.34` vs `HelioStack = 1,105.87 kWh/kWp` (**`-0.67%`**)
- **Seville, ES:** `pvlib = 1,846.44` vs `HelioStack = 1,852.10 kWh/kWp` (**`+0.31%`**)

---

## Phase 3 Validation (`v0.3.0`): OpenFOAM 14 CFD & European Full-Year Field Testbed

### 1. Reproducible OpenFOAM 14 `28°`-Tilted PV Thermal Sweep (`foamRun -solver fluid`, 5,910 cells)
| Mounting Surface | Clearance / Soil or Water Boundary | Wind Convective Fit (`h_conv(v)`) | Longwave `h_rad` | OpenFOAM Faiman Eq. (`u0`, `u1`) |
| :--- | :---: | :---: | :---: | :---: |
| **Land Rack** | `0.85 m` over `+35 °C` sunlit soil | `4.705 + 3.648·v W/m²K` | `11.738 W/m²K` | `u0 = 22.56`, `u1 = 5.00` |
| **Floating PV** | `0.25 m` over `+21 °C` reservoir water | `4.912 + 3.906·v W/m²K` | `14.688 W/m²K` | `u0 = 26.89`, `u1 = 5.36` |

### 2. European Union 1-Year Field Validation (University of Cyprus PHAETHON CoE, `8,784` hrs, `CC-BY-4.0`)
- Dataset: June 2015 – May 2016 (`3,935` daylight operating hours, DOI `10.5281/zenodo.10816826`).
- **Thermal Accuracy (`Tmod` backsheet PT100):** `open_rack` `RMSE = 2.18 °C` (`R² = 0.9705`), `convective_land` `RMSE = 2.22 °C` (`R² = 0.9693`), pure **OpenFOAM 14 `cfd_land`** (zero Cyprus tuning) `RMSE = 4.19 °C` (`R² = 0.8906`).
- **Full-Year Yield Accuracy:** Measured `2,450 kWh` DC vs Modeled `2,410 kWh` (`MBE = -1.62%`, `nRMSE = 2.85%`, `R² = 0.9887`; AC `MBE = -1.01%`, `R² = 0.9876`).

---

## Quick Start

```bash
pip install -e ".[dev]"

# 1. Validate .PAN / .OND specifications (exit 0 on valid, exit 1 on physics failure)
heliostack validate fixtures/equipment/ref_550w_bifacial.pan
heliostack validate fixtures/equipment/invalid_module.pan

# 2. Extract 36-azimuth Copernicus DEM terrain horizon vs EU PVGIS printhorizon
heliostack horizon --lat 47.2692 --lon 11.4041 --cache-dir fixtures/weather

# 3. Run full Phase 1 + Phase 2 + Phase 3 reproducible benchmarks
python benchmarks/run_europe_benchmark.py
python benchmarks/run_phase2_validation.py
python benchmarks/run_phase3_validation.py

# (Optional in WSL2 / Linux with OpenFOAM 14 installed):
python openfoam/run_openfoam_pv_sweep.py

# 4. Preview offline interactive Web UI locally
heliostack serve --dir docs --port 8780
```
