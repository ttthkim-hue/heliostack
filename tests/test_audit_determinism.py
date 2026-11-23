"""Determinism, RO-Crate 1.1, SHA-256 manifest, and bankable HTML report tests."""

from __future__ import annotations

import json
from pathlib import Path

from heliostack.cli import main as cli_main

ROOT = Path(__file__).resolve().parent.parent
WEATHER_CSV = ROOT / "fixtures" / "weather" / "amsterdam_pvgis_tmy_2023.csv"


def test_cli_simulate_determinism_and_rocrate_bundle(tmp_path: Path) -> None:
    cfg = tmp_path / "site.json"
    cfg.write_text(
        json.dumps(
            {
                "site_name": "Amsterdam Deterministic Check",
                "latitude": 52.37,
                "longitude": 4.90,
                "elevation_m": 3.0,
                "surface_tilt_deg": 35.0,
                "surface_azimuth_deg": 180.0,
                "dc_kwp": 100.0,
                "grid_export_limit_kw": 70.0,
                "ess_energy_kwh": 150.0,
                "ess_power_kw": 40.0,
                "mounting_mode": "floating_pv",
                "albedo": 0.08,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    out_a = tmp_path / "run_a"
    out_b = tmp_path / "run_b"
    assert cli_main(["simulate", "--config", str(cfg), "-o", str(out_a), "--weather", str(WEATHER_CSV)]) == 0
    assert cli_main(["simulate", "--config", str(cfg), "-o", str(out_b), "--weather", str(WEATHER_CSV)]) == 0

    for fname in ("audit_report.json", "bankable_report.html", "repro-manifest.json", "ro-crate-metadata.json"):
        fa = out_a / fname
        fb = out_b / fname
        assert fa.is_file()
        assert fb.is_file()
        assert fa.read_bytes() == fb.read_bytes(), f"Determinism mismatch in {fname}"

    repro = json.loads((out_a / "repro-manifest.json").read_text(encoding="utf-8"))
    assert repro["runtime_environment"]["external_llm_used_at_runtime"] is False
    assert repro["license"] == "AGPL-3.0-or-later"

    crate = json.loads((out_a / "ro-crate-metadata.json").read_text(encoding="utf-8"))
    assert crate["@context"] == "https://w3id.org/ro/crate/1.1/context"
    graph_ids = {node["@id"] for node in crate["@graph"]}
    assert {"./", "audit_report.json", "bankable_report.html", "repro-manifest.json"}.issubset(graph_ids)
    root_node = next(node for node in crate["@graph"] if node["@id"] == "./")
    assert root_node["license"] == "https://www.gnu.org/licenses/agpl-3.0.html"

    html_txt = (out_a / "bankable_report.html").read_text(encoding="utf-8")
    assert "Monthly PV Yield Chart" in html_txt
    assert "NaN" not in html_txt
