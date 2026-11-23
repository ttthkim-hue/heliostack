"""Generate a crisp 1280x640 4-panel verified benchmark hero SVG (and optional PNG) for GitHub README."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
P2_JSON = ROOT / "results" / "phase2_validation_v02.json"
P3_JSON = ROOT / "results" / "phase3_validation_v03.json"
OUT_SVG = ROOT / "docs" / "assets" / "heliostack_hero_validation.svg"
OUT_PNG = ROOT / "docs" / "assets" / "heliostack_social_preview.png"


def _polyline(pts: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


def _render_svg(p2: dict[str, Any], p3: dict[str, Any]) -> str:
    # Panel 1: Zermatt Alpine Copernicus vs PVGIS horizon
    zermatt = next(x for x in p2["pillar_a_alpine_terrain"] if x["id"] == "zermatt")
    h_cop = zermatt["copernicus_horizon_deg_36"]
    h_pvg = zermatt["pvgis_horizon_deg_36"]
    p1_x0, p1_y0, p1_w, p1_h = 68.0, 260.0, 520.0, 145.0
    cop_pts = [
        (p1_x0 + i * (p1_w / 35.0), p1_y0 - (min(36.0, v) / 36.0) * p1_h)
        for i, v in enumerate(h_cop)
    ]
    pvg_pts = [
        (p1_x0 + i * (p1_w / 35.0), p1_y0 - (min(36.0, v) / 36.0) * p1_h)
        for i, v in enumerate(h_pvg)
    ]
    cop_area = f"{p1_x0:.1f},{p1_y0:.1f} " + _polyline(cop_pts) + f" {p1_x0 + p1_w:.1f},{p1_y0:.1f}"

    # Panel 2: EU Cyprus 12-month DC (convective_land)
    cy_dc = p3["eu_cyprus_field_validation"]["models"]["convective_land"]["dc_power"]
    cy_meas = cy_dc["monthly_measured_kwh"]
    cy_mod = cy_dc["monthly_modeled_kwh"]
    p2_x0, p2_y0, p2_w, p2_h = 695.0, 260.0, 520.0, 145.0
    cy_bars = []
    months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    for i, m_lbl in enumerate(months):
        bx = p2_x0 + i * (p2_w / 12.0) + 4
        h1 = (cy_meas[i] / 270.0) * p2_h
        h2 = (cy_mod[i] / 270.0) * p2_h
        cy_bars.append(f'<rect x="{bx:.1f}" y="{p2_y0 - h1:.1f}" width="15" height="{h1:.1f}" rx="2" fill="#0f766e" />')
        cy_bars.append(f'<rect x="{bx + 17:.1f}" y="{p2_y0 - h2:.1f}" width="15" height="{h2:.1f}" rx="2" fill="#d97706" opacity="0.88" />')
        cy_bars.append(f'<text x="{bx + 16:.1f}" y="{p2_y0 + 18:.1f}" font-size="11" text-anchor="middle" fill="#475569">{m_lbl}</text>')

    # Panel 3: US DOE PVDAQ #2107 2024 (convective_land, Jan-Nov)
    pv = p2["pillar_b_pvdaq_2107_field"]["models"]["convective_land"]
    pv_meas = pv["monthly_measured_mwh"][:11]
    pv_mod = pv["monthly_modeled_mwh"][:11]
    p3_x0, p3_y0, p3_w, p3_h = 68.0, 535.0, 520.0, 145.0
    pv_bars = []
    for i, m_lbl in enumerate(months[:11]):
        bx = p3_x0 + i * (p3_w / 11.0) + 4
        h1 = (pv_meas[i] / 175.0) * p3_h
        h2 = (pv_mod[i] / 175.0) * p3_h
        pv_bars.append(f'<rect x="{bx:.1f}" y="{p3_y0 - h1:.1f}" width="16" height="{h1:.1f}" rx="2" fill="#0f766e" />')
        pv_bars.append(f'<rect x="{bx + 18:.1f}" y="{p3_y0 - h2:.1f}" width="16" height="{h2:.1f}" rx="2" fill="#d97706" opacity="0.88" />')
        pv_bars.append(f'<text x="{bx + 17:.1f}" y="{p3_y0 + 18:.1f}" font-size="11" text-anchor="middle" fill="#475569">{m_lbl}{"*" if i == 10 else ""}</text>')

    # Panel 4: OpenFOAM 14 28-deg Tilted PV total cooling (Land vs Floating PV)
    land_cases = p3["openfoam14_thermal_surrogate"]["surfaces"]["land_rack"]["cases"]
    fpv_cases = p3["openfoam14_thermal_surrogate"]["surfaces"]["floating_pv"]["cases"]
    p4_x0, p4_y0, p4_w, p4_h = 695.0, 535.0, 520.0, 145.0

    def _of_pt(wind: float, htot: float) -> tuple[float, float]:
        px = p4_x0 + ((wind - 1.0) / 5.0) * (p4_w - 40.0) + 20.0
        py = p4_y0 - ((htot - 15.0) / 37.0) * p4_h
        return px, py

    land_pts = [_of_pt(c["wind_speed_ms"], c["h_total_with_rad_w_m2k"]) for c in land_cases]
    fpv_pts = [_of_pt(c["wind_speed_ms"], c["h_total_with_rad_w_m2k"]) for c in fpv_cases]
    of_marks = []
    for (lx, ly), (fx, fy), c in zip(land_pts, fpv_pts, fpv_cases, strict=True):
        of_marks.append(f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="5" fill="#0f766e" />')
        of_marks.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="#d97706" />')
        of_marks.append(f'<text x="{fx:.1f}" y="{p4_y0 + 18:.1f}" font-size="11" text-anchor="middle" fill="#475569">{int(c["wind_speed_ms"])} m/s</text>')
        of_marks.append(f'<text x="{fx:.1f}" y="{fy - 10:.1f}" font-size="10.5" font-weight="700" text-anchor="middle" fill="#0f766e">{c["h_total_with_rad_w_m2k"]:.1f}</text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 640" width="1280" height="640" font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif">
  <rect width="1280" height="640" rx="18" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2" />
  <rect x="0" y="0" width="1280" height="68" rx="18" fill="#0f172a" />
  <rect x="0" y="50" width="1280" height="18" fill="#0f172a" />
  <text x="34" y="34" font-size="22" font-weight="800" fill="#ffffff">HelioStack v0.3.0 — Open-Source Solar PV, Terrain, OpenFOAM CFD &amp; ESS Validation</text>
  <text x="34" y="56" font-size="12.5" fill="#94a3b8">MIT License · pip install heliostack · 0% Runtime Generative AI · Verified Across Alps, EU Cyprus &amp; US DOE Utility Telemetry</text>

  <!-- 4 Cards -->
  <rect x="24" y="84" width="604" height="258" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5" />
  <rect x="652" y="84" width="604" height="258" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5" />
  <rect x="24" y="358" width="604" height="258" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5" />
  <rect x="652" y="358" width="604" height="258" rx="12" fill="#ffffff" stroke="#e2e8f0" stroke-width="1.5" />

  <!-- Panel 1 -->
  <text x="44" y="109" font-size="15" font-weight="700" fill="#0f172a">1. Copernicus DEM vs EU PVGIS Horizon (Zermatt Alps)</text>
  <rect x="442" y="94" width="168" height="22" rx="11" fill="#ccfbf1" />
  <text x="526" y="109" font-size="11.5" font-weight="700" text-anchor="middle" fill="#0f766e">MAE 1.57° · Loss -15.7%</text>
  <line x1="{p1_x0}" y1="{p1_y0}" x2="{p1_x0 + p1_w}" y2="{p1_y0}" stroke="#cbd5e1" stroke-width="1.5" />
  <line x1="{p1_x0}" y1="{p1_y0 - p1_h/2:.1f}" x2="{p1_x0 + p1_w}" y2="{p1_y0 - p1_h/2:.1f}" stroke="#e2e8f0" stroke-dasharray="4 4" />
  <text x="56" y="{p1_y0 + 4}" font-size="10.5" text-anchor="end" fill="#64748b">0°</text>
  <text x="56" y="{p1_y0 - p1_h + 10}" font-size="10.5" text-anchor="end" fill="#64748b">36°</text>
  <polygon points="{cop_area}" fill="#0f766e" opacity="0.14" />
  <polyline fill="none" stroke="#0f766e" stroke-width="2.8" points="{_polyline(cop_pts)}" />
  <polyline fill="none" stroke="#d97706" stroke-width="2.2" stroke-dasharray="6 4" points="{_polyline(pvg_pts)}" />
  <text x="{p1_x0}" y="{p1_y0 + 18}" font-size="11" fill="#475569">0° N</text>
  <text x="{p1_x0 + p1_w/2:.1f}" y="{p1_y0 + 18}" font-size="11" text-anchor="middle" fill="#475569">180° S (Solar South)</text>
  <text x="{p1_x0 + p1_w:.1f}" y="{p1_y0 + 18}" font-size="11" text-anchor="end" fill="#475569">350°</text>
  <text x="44" y="328" font-size="12" fill="#475569">Teal: Copernicus 30m DEM Ray-Cast | Dashed Amber: EU PVGIS Official Horizon (-13.99%)</text>

  <!-- Panel 2 -->
  <text x="672" y="109" font-size="15" font-weight="700" fill="#0f172a">2. EU Cyprus 1-Year Field (8,784 hrs)</text>
  <rect x="1058" y="94" width="180" height="22" rx="11" fill="#ccfbf1" />
  <text x="1148" y="109" font-size="11.5" font-weight="700" text-anchor="middle" fill="#0f766e">R² 0.9887 · RMSE 2.18°C</text>
  <line x1="{p2_x0}" y1="{p2_y0}" x2="{p2_x0 + p2_w}" y2="{p2_y0}" stroke="#cbd5e1" stroke-width="1.5" />
  <text x="686" y="{p2_y0 - p2_h + 10}" font-size="10.5" text-anchor="end" fill="#64748b">270</text>
  <text x="686" y="{p2_y0 + 4}" font-size="10.5" text-anchor="end" fill="#64748b">0</text>
  {"".join(cy_bars)}
  <text x="672" y="328" font-size="12" fill="#475569">Teal: Measured DC (2,450 kWh) | Amber: HelioStack (2,410 kWh, Pure OpenFOAM R²=0.9835)</text>

  <!-- Panel 3 -->
  <text x="44" y="383" font-size="15" font-weight="700" fill="#0f172a">3. Real 892.8 kWp US Plant (DOE PVDAQ #2107, 2024)</text>
  <rect x="442" y="368" width="168" height="22" rx="11" fill="#ccfbf1" />
  <text x="526" y="383" font-size="11.5" font-weight="700" text-anchor="middle" fill="#0f766e">R² 0.9101 · MBE +3.81%</text>
  <line x1="{p3_x0}" y1="{p3_y0}" x2="{p3_x0 + p3_w}" y2="{p3_y0}" stroke="#cbd5e1" stroke-width="1.5" />
  <text x="56" y="{p3_y0 - p3_h + 10}" font-size="10.5" text-anchor="end" fill="#64748b">175</text>
  <text x="56" y="{p3_y0 + 4}" font-size="10.5" text-anchor="end" fill="#64748b">0</text>
  {"".join(pv_bars)}
  <text x="44" y="602" font-size="12" fill="#475569">3,255 valid operating hrs (Jan-Nov*): Measured 1,221 MWh vs Modeled 1,268 MWh (nRMSE 6.79%)</text>

  <!-- Panel 4 -->
  <text x="672" y="383" font-size="15" font-weight="700" fill="#0f172a">4. OpenFOAM 14 28° CFD Cooling</text>
  <rect x="1058" y="368" width="180" height="22" rx="11" fill="#fef3c7" />
  <text x="1148" y="383" font-size="11.5" font-weight="700" text-anchor="middle" fill="#b45309">+14–20% Cooling Gain</text>
  <line x1="{p4_x0}" y1="{p4_y0}" x2="{p4_x0 + p4_w}" y2="{p4_y0}" stroke="#cbd5e1" stroke-width="1.5" />
  <line x1="{p4_x0}" y1="{p4_y0 - p4_h/2:.1f}" x2="{p4_x0 + p4_w}" y2="{p4_y0 - p4_h/2:.1f}" stroke="#e2e8f0" stroke-dasharray="4 4" />
  <text x="686" y="{p4_y0 - p4_h + 10}" font-size="10.5" text-anchor="end" fill="#64748b">52</text>
  <text x="686" y="{p4_y0 + 4}" font-size="10.5" text-anchor="end" fill="#64748b">15</text>
  <polyline fill="none" stroke="#0f766e" stroke-width="3" points="{_polyline(fpv_pts)}" />
  <polyline fill="none" stroke="#d97706" stroke-width="2.4" stroke-dasharray="6 4" points="{_polyline(land_pts)}" />
  {"".join(of_marks)}
  <text x="672" y="602" font-size="12" fill="#475569">W/m²K total (conv + rad): Pontoon FPV (0.25m, 21°C water) vs Land Rack (0.85m, 35°C soil)</text>
</svg>
"""


def main() -> None:
    p2 = json.loads(P2_JSON.read_text(encoding="utf-8"))
    p3 = json.loads(P3_JSON.read_text(encoding="utf-8"))
    OUT_SVG.parent.mkdir(parents=True, exist_ok=True)
    svg = _render_svg(p2, p3)
    OUT_SVG.write_text(svg, encoding="utf-8")
    print(f"Generated {OUT_SVG} ({len(svg)} bytes)")

    browser = shutil.which("msedge") or shutil.which("chrome")
    if not browser:
        for cand in (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ):
            if Path(cand).is_file():
                browser = cand
                break

    if browser:
        with tempfile.TemporaryDirectory() as td:
            html_file = Path(td) / "wrap.html"
            html_file.write_text(
                f'<html><body style="margin:0;padding:0;overflow:hidden;"><img src="{OUT_SVG.resolve().as_uri()}" width="1280" height="640"/></body></html>',
                encoding="utf-8",
            )
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    f"--screenshot={OUT_PNG}",
                    "--window-size=1280,640",
                    html_file.as_uri(),
                ],
                capture_output=True,
                check=False,
            )
        if OUT_PNG.is_file() and OUT_PNG.stat().st_size > 1000:
            print(f"Generated PNG {OUT_PNG} ({OUT_PNG.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
