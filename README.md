# HelioStack v0.1.0

**Deterministic open-source solar PV, 3D ray-cast shading, CFD-informed land/Floating-PV thermal, and HiGHS `LiFePO4` ESS optimization workbench with `RO-Crate 1.1` & `SHA-256` audit provenance.**

- **License:** MIT (`100%` OSI-permissive open source; `0%` generative AI or closed vendor APIs at runtime)
- **Live Data Provenance:** Cross-validated against European Commission **PVGIS v5.3** (`SARAH3` & `ERA5`) hourly TMY and official `PVcalc` reference yields
- **AI Transparency:** [`AI_DISCLOSURE.md`](./AI_DISCLOSURE.md)
- **41-Day NLnet Plan:** [`docs/ROADMAP_TO_NLNET_20270103.md`](./docs/ROADMAP_TO_NLNET_20270103.md)

---

## Why HelioStack?

Commercial Windows-only tools (`PVsyst`, `PV*SOL`, `HOMER Pro`) and closed cloud SaaS (`HelioScope`) lock solar engineering workflows behind proprietary `.PAN`/`.OND` binary/desktop silos, while open libraries (`pvlib`) lack unified 3D obstacle ray-casting, Floating-PV water thermal physics, sparse 8,760-hour ESS curtailment optimization, and cryptographic reproducibility bundles.

`HelioStack` bridges that gap in pure open Python:
1. **Clean-Room Equipment Validation (`.PAN` / `.OND` / JSON):** Enforces physical single-diode & MPPT window invariants (`Vmp < Voc`, `Imp < Isc`, finite metrics, inverter efficiency bounds).
2. **Vectorized 3D Ray-Box Shading & Diffuse SVF:** Evaluates 3D obstacle shading, 36-azimuth horizon profiles, inter-row shed geometry, and cosine-weighted hemispherical sky-view factors.
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

## Quick Start

```bash
pip install -e ".[dev]"

# 1. Validate .PAN / .OND specifications (exit 0 on valid, exit 1 on physics failure)
heliostack validate fixtures/equipment/ref_550w_bifacial.pan
heliostack validate fixtures/equipment/invalid_module.pan

# 2. Run full 8,760-hr benchmark across cached/live EU PVGIS sites
python benchmarks/run_europe_benchmark.py

# 3. Preview offline interactive Web UI locally
heliostack serve --dir docs --port 8780
```
