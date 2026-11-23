"""Deterministic RO-Crate 1.1, SHA-256 manifest, JSON audit, and printable HTML report."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from heliostack import __version__
from heliostack.models import SimulationResult


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _render_monthly_svg(monthly_ac: list[float], monthly_curt_no: list[float], monthly_curt_with: list[float]) -> str:
    """Render clean standalone SVG monthly yield and curtailment chart."""
    w, h = 680, 220
    pad_l, pad_r, pad_t, pad_b = 54, 16, 20, 32
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    max_val = max(100.0, max((a + c for a, c in zip(monthly_ac, monthly_curt_no, strict=True)), default=100.0) * 1.12)
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    step = plot_w / 12.0
    bar_w = step * 0.62

    bars: list[str] = []
    for i, label in enumerate(labels):
        x = pad_l + i * step + (step - bar_w) * 0.5
        ac_h = (monthly_ac[i] / max_val) * plot_h
        y_ac = pad_t + plot_h - ac_h
        bars.append(
            f'<rect x="{x:.1f}" y="{y_ac:.1f}" width="{bar_w:.1f}" height="{ac_h:.1f}" '
            f'rx="3" fill="#0f766e" opacity="0.88" />'
        )
        if monthly_curt_with[i] > 1.0:
            ch = (monthly_curt_with[i] / max_val) * plot_h
            bars.append(
                f'<rect x="{x:.1f}" y="{y_ac:.1f}" width="{bar_w:.1f}" height="{min(ac_h, ch):.1f}" '
                f'rx="2" fill="#d97706" opacity="0.92" />'
            )
        bars.append(
            f'<text x="{x + bar_w * 0.5:.1f}" y="{h - 10}" text-anchor="middle" '
            f'font-size="11" fill="#475569">{label}</text>'
        )

    grid_lines: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        yv = pad_t + plot_h * (1.0 - frac)
        val_kwh = max_val * frac / 1000.0
        grid_lines.append(
            f'<line x1="{pad_l}" y1="{yv:.1f}" x2="{w - pad_r}" y2="{yv:.1f}" stroke="#e2e8f0" stroke-width="1" />'
        )
        grid_lines.append(
            f'<text x="{pad_l - 6}" y="{yv + 4:.1f}" text-anchor="end" font-size="10" fill="#64748b">{val_kwh:.1f} MWh</text>'
        )

    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="Monthly PV Yield Chart">'
        + "".join(grid_lines)
        + "".join(bars)
        + "</svg>"
    )


def render_bankable_html(result: SimulationResult) -> str:
    """Generate a deterministic, zero-CDN standalone HTML engineering report."""
    s = result.site
    wf = result.loss_waterfall
    ess = result.ess_metrics
    svg = _render_monthly_svg(
        result.monthly_ac_kwh,
        result.monthly_curtailed_no_ess_kwh,
        result.monthly_curtailed_with_ess_kwh,
    )
    esc = html.escape
    payback_txt = f"{ess.simple_payback_ess_yr:.2f} yr" if ess.simple_payback_ess_yr is not None else "N/A"
    weather_sha = str(result.weather_provenance.get("payload_sha256", ""))[:16]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>HelioStack Bankable Engineering Report — {esc(s.site_name)}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 24px; color: #0f172a; background: #f8fafc; }}
  .wrap {{ max-width: 920px; margin: 0 auto; background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px; padding: 28px; }}
  h1 {{ margin: 0 0 6px; font-size: 1.55rem; }}
  .sub {{ color: #475569; margin: 0 0 18px; font-size: 0.92rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 20px; }}
  .kpi {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; background: #f8fafc; }}
  .kpi .v {{ font-size: 1.28rem; font-weight: 700; color: #0f766e; }}
  .kpi .k {{ font-size: 0.8rem; color: #475569; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 14px 0 22px; font-size: 0.9rem; }}
  th, td {{ border-bottom: 1px solid #e2e8f0; padding: 8px 10px; text-align: left; }}
  th {{ background: #f1f5f9; font-weight: 600; }}
  .foot {{ font-size: 0.8rem; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 12px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>HelioStack v{esc(__version__)} — Bankable Yield &amp; ESS Audit Report</h1>
  <p class="sub">{esc(s.site_name)} ({s.latitude:.4f}, {s.longitude:.4f}) &middot; Mode: <strong>{esc(s.mounting_mode)}</strong> &middot; {s.dc_kwp:.1f} kWp DC / {s.grid_export_limit_kw:.1f} kW Export Cap</p>
  <div class="grid">
    <div class="kpi"><div class="v">{wf.specific_yield_kwh_kwp:,.1f}</div><div class="k">Specific Yield (kWh/kWp/yr)</div></div>
    <div class="kpi"><div class="v">{wf.performance_ratio * 100:.2f}%</div><div class="k">Performance Ratio (PR)</div></div>
    <div class="kpi"><div class="v">{wf.p90_kwh_yr / 1000.0:,.2f} MWh</div><div class="k">P90 Annual Exceedance</div></div>
    <div class="kpi"><div class="v">{ess.curtailment_recovery_pct:.1f}%</div><div class="k">ESS Curtailment Recovery</div></div>
    <div class="kpi"><div class="v">EUR {ess.lcoe_eur_kwh:.4f}/kWh</div><div class="k">20-Year LCOE</div></div>
  </div>
  <h2>Monthly AC Energy &amp; Remaining Curtailment</h2>
  {svg}
  <h2>Energy Loss Waterfall &amp; Thermal Summary</h2>
  <table>
    <tr><th>Metric</th><th>Value</th><th>Notes</th></tr>
    <tr><td>Horizontal Irradiation (GHI)</td><td>{wf.ghi_kwh_m2:.1f} kWh/m&sup2;</td><td>Source: {esc(str(result.weather_provenance.get("source", "PVGIS")))} (SHA {esc(weather_sha)})</td></tr>
    <tr><td>Global Tilted POA (Unshaded)</td><td>{wf.poa_global_kwh_m2:.1f} kWh/m&sup2;</td><td>Transposition gain: {wf.transposition_gain_pct:+.2f}%</td></tr>
    <tr><td>3D Beam Shading + Diffuse SVF</td><td>-{wf.shading_loss_pct:.2f}%</td><td>Diffuse Sky-View Factor: {wf.diffuse_svf:.3f}</td></tr>
    <tr><td>IAM + Soiling + Bifacial Gain</td><td>-{wf.iam_loss_pct:.2f}% / -{wf.soiling_loss_pct:.2f}% / +{wf.bifacial_gain_pct:.2f}%</td><td>Module bifaciality: {result.module.bifaciality_factor:.2f}</td></tr>
    <tr><td>Thermal Loss &amp; Daytime T<sub>cell</sub></td><td>-{wf.thermal_loss_pct:.2f}% ({wf.mean_cell_temp_day_c:.1f} &deg;C)</td><td>Mounting thermal physics: {esc(s.mounting_mode)}</td></tr>
    <tr><td>Inverter Eff. &amp; Clipping Losses</td><td>-{wf.inverter_eff_loss_pct:.2f}% / -{wf.clipping_loss_pct:.2f}%</td><td>{esc(result.inverter.manufacturer)} {esc(result.inverter.model)}</td></tr>
    <tr><td>P50 / P75 / P90 / P99 Yield</td><td>{wf.p50_kwh_yr:,.0f} / {wf.p75_kwh_yr:,.0f} / {wf.p90_kwh_yr:,.0f} / {wf.p99_kwh_yr:,.0f} kWh</td><td>Combined 1-sigma 4.40% analytical uncertainty</td></tr>
  </table>
  <h2>8,760-Hour HiGHS ESS &amp; Curtailment Dispatch</h2>
  <table>
    <tr><th>Metric</th><th>Baseline (No ESS)</th><th>Optimized ({s.ess_energy_kwh:.0f} kWh / {s.ess_power_kw:.0f} kW)</th></tr>
    <tr><td>Curtailed Energy</td><td>{ess.curtailed_no_ess_kwh_yr:,.1f} kWh/yr</td><td>{ess.curtailed_with_ess_kwh_yr:,.1f} kWh/yr ({ess.curtailment_recovery_pct:.1f}% recovered)</td></tr>
    <tr><td>Net Grid Export</td><td>{ess.net_export_no_ess_kwh_yr:,.1f} kWh/yr</td><td>{ess.net_export_with_ess_kwh_yr:,.1f} kWh/yr</td></tr>
    <tr><td>Annual Cycles &amp; HVAC Aux</td><td>0.0 / 0.0 kWh</td><td>{ess.annual_cycles:.1f} cycles / {ess.ess_hvac_aux_kwh_yr:,.1f} kWh aux</td></tr>
    <tr><td>Annual Export Revenue &amp; Payback</td><td>EUR {ess.revenue_no_ess_eur_yr:,.0f}/yr</td><td>EUR {ess.revenue_with_ess_eur_yr:,.0f}/yr (+{ess.revenue_uplift_eur_yr:,.0f}/yr, ESS payback {esc(payback_txt)})</td></tr>
  </table>
  <div class="foot">
    Deterministic execution with 0% generative AI at runtime &middot; HiGHS LP max hourly residual: {ess.max_hourly_conservation_err_kw:.2e} kW &middot; Verified AGPL-3.0-or-later Open Source (`heliostack` v{esc(__version__)}).
  </div>
</div>
</body>
</html>
"""


def write_audit_bundle(
    result: SimulationResult,
    output_dir: Path,
    input_files: list[Path] | None = None,
) -> dict[str, Path]:
    """Write deterministic audit JSON, bankable HTML, SHA-256 manifest, and RO-Crate 1.1."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_path = output_dir / "audit_report.json"
    html_path = output_dir / "bankable_report.html"
    repro_path = output_dir / "repro-manifest.json"
    rocrate_path = output_dir / "ro-crate-metadata.json"

    audit_data = result.to_dict()
    audit_data["ess_metrics"].pop("solve_time_s", None)
    audit_path.write_text(json.dumps(audit_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_bankable_html(result), encoding="utf-8")

    artifacts: list[dict[str, Any]] = [
        {"relative_path": "audit_report.json", "role": "simulation_result", "sha256": _sha256_file(audit_path)},
        {"relative_path": "bankable_report.html", "role": "bankable_report", "sha256": _sha256_file(html_path)},
    ]
    for fpath in input_files or []:
        if fpath.is_file():
            artifacts.append(
                {
                    "relative_path": fpath.name,
                    "role": "input_specification",
                    "sha256": _sha256_file(fpath),
                }
            )

    repro_payload = {
        "schema": "heliostack.repro-manifest.v1",
        "engine_version": __version__,
        "license": "AGPL-3.0-or-later",
        "runtime_environment": {
            "external_llm_used_at_runtime": False,
            "deterministic_physics_solver": "pvlib_single_diode + scipy_highs_lp",
        },
        "weather_provenance": result.weather_provenance,
        "artifacts": artifacts,
    }
    repro_path.write_text(json.dumps(repro_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    graph: list[dict[str, Any]] = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": f"HelioStack Bankable Simulation Audit: {result.site.site_name}",
            "license": "https://www.gnu.org/licenses/agpl-3.0.html",
            "hasPart": [
                {"@id": "audit_report.json"},
                {"@id": "bankable_report.html"},
                {"@id": "repro-manifest.json"},
            ],
        },
        {"@id": "audit_report.json", "@type": "File", "encodingFormat": "application/json"},
        {"@id": "bankable_report.html", "@type": "File", "encodingFormat": "text/html"},
        {"@id": "repro-manifest.json", "@type": "File", "encodingFormat": "application/json"},
    ]
    rocrate_payload = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": graph,
    }
    rocrate_path.write_text(json.dumps(rocrate_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "audit_report": audit_path,
        "bankable_report": html_path,
        "repro_manifest": repro_path,
        "ro_crate": rocrate_path,
    }
