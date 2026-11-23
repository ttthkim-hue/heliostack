"""Command-line entrypoint for HelioStack equipment validation, simulation, and preview."""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
from pathlib import Path
from typing import Any

from heliostack import __version__
from heliostack.audit import write_audit_bundle
from heliostack.ess_optimizer import run_full_simulation
from heliostack.formats import parse_ond, parse_pan, validate_equipment_path
from heliostack.models import ObstacleBox3D, SiteConfig
from heliostack.terrain import (
    compare_horizon_profiles,
    fetch_copernicus_dem_horizon,
    fetch_pvgis_horizon,
)
from heliostack.weather import fetch_pvgis_tmy, load_cached_tmy


def _load_site_from_json(path: Path) -> tuple[SiteConfig, Path | None, Path | None]:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    obstacles = [ObstacleBox3D(**obs) for obs in raw.pop("obstacles", [])]
    pan_path = Path(raw.pop("module_file")) if "module_file" in raw else None
    ond_path = Path(raw.pop("inverter_file")) if "inverter_file" in raw else None
    if pan_path and not pan_path.is_absolute():
        pan_path = (path.parent / pan_path).resolve()
    if ond_path and not ond_path.is_absolute():
        ond_path = (path.parent / ond_path).resolve()
    site = SiteConfig(**raw, obstacles=obstacles)
    return site, pan_path, ond_path


def _cmd_validate(args: argparse.Namespace) -> int:
    target = Path(args.target)
    if not target.exists():
        print(f"Path not found: {target}", file=sys.stderr)
        return 2
    records, code = validate_equipment_path(target)
    if args.json:
        print(json.dumps({"exit_code": code, "files": records}, indent=2))
    else:
        for rec in records:
            tag = "PASS" if rec["passed"] else "FAIL"
            print(f"[{tag}] {rec['file']} ({rec['kind']}): errors={rec['errors']}, warnings={rec['warnings']}")
            for issue in rec["issues"]:
                print(f"  - {issue['severity']} [{issue['code']}]: {issue['message']}")
    return code


def _cmd_simulate(args: argparse.Namespace) -> int:
    cfg_path = Path(args.config)
    if not cfg_path.is_file():
        print(f"Config not found: {cfg_path}", file=sys.stderr)
        return 2

    site, pan_path, ond_path = _load_site_from_json(cfg_path)
    pkg_root = Path(__file__).resolve().parent.parent.parent
    pan_file = pan_path or (pkg_root / "fixtures" / "equipment" / "ref_550w_bifacial.pan")
    ond_file = ond_path or (pkg_root / "fixtures" / "equipment" / "ref_250kw_inverter.ond")

    mod, mod_issues = parse_pan(pan_file)
    inv, inv_issues = parse_ond(ond_file)
    if mod is None or inv is None:
        print("Equipment validation failed:", mod_issues + inv_issues, file=sys.stderr)
        return 1

    if args.weather:
        weather, prov = load_cached_tmy(Path(args.weather))
    else:
        cache_dir = Path(args.cache_dir) if args.cache_dir else None
        weather, prov = fetch_pvgis_tmy(site.latitude, site.longitude, cache_dir=cache_dir)

    auto_hor = getattr(args, "auto_horizon", "none")
    if auto_hor != "none":
        hor_cache = Path(args.cache_dir) if args.cache_dir else None
        if auto_hor == "copernicus":
            site.horizon_elev_deg_36, _ = fetch_copernicus_dem_horizon(
                site.latitude, site.longitude, cache_dir=hor_cache
            )
        elif auto_hor == "pvgis":
            site.horizon_elev_deg_36, _ = fetch_pvgis_horizon(
                site.latitude, site.longitude, cache_dir=hor_cache
            )

    result = run_full_simulation(
        weather=weather,
        weather_provenance=prov,
        site=site,
        module=mod,
        inverter=inv,
    )
    out_dir = Path(args.output)
    paths = write_audit_bundle(result, out_dir, input_files=[cfg_path, pan_file, ond_file])
    wf = result.loss_waterfall
    ess = result.ess_metrics
    print(
        f"HelioStack v{__version__} | {site.site_name} ({site.mounting_mode}): "
        f"{wf.specific_yield_kwh_kwp:.1f} kWh/kWp/yr | PR={wf.performance_ratio:.3f} | "
        f"Curtailment Recovery={ess.curtailment_recovery_pct:.1f}% | LCOE=EUR {ess.lcoe_eur_kwh:.4f}/kWh"
    )
    print(f"RO-Crate bundle written to: {paths['ro_crate']}")
    return 0


def _cmd_horizon(args: argparse.Namespace) -> int:
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    h_cop, meta_cop = fetch_copernicus_dem_horizon(args.lat, args.lon, cache_dir=cache_dir)
    h_pvgis, meta_pvg = fetch_pvgis_horizon(args.lat, args.lon, cache_dir=cache_dir)
    stats = compare_horizon_profiles(h_cop, h_pvgis)
    payload = {
        "latitude": args.lat,
        "longitude": args.lon,
        "comparison": stats,
        "copernicus_meta": meta_cop,
        "pvgis_meta": meta_pvg,
        "copernicus_horizon_deg_36": h_cop,
        "pvgis_horizon_deg_36": h_pvgis,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"Horizon ({args.lat:.4f}, {args.lon:.4f}) | Elev={meta_cop['site_elevation_m']} m | "
            f"Copernicus mean={stats['mean_copernicus_deg']:.2f} deg vs PVGIS mean={stats['mean_pvgis_deg']:.2f} deg | "
            f"MAE={stats['mae_deg']:.2f} deg, RMSE={stats['rmse_deg']:.2f} deg"
        )
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    serve_dir = Path(args.dir)
    if not serve_dir.is_dir():
        print(f"Directory not found: {serve_dir}", file=sys.stderr)
        return 2
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(serve_dir))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"Serving HelioStack UI at http://127.0.0.1:{args.port}/ (Ctrl+C to stop)")
        httpd.serve_forever()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="heliostack", description="HelioStack open solar PV & ESS simulation CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="Validate .pan/.ond/.json equipment specifications")
    p_val.add_argument("target", help="File or directory to validate")
    p_val.add_argument("--json", action="store_true", help="Emit structured JSON validation report")
    p_val.set_defaults(func=_cmd_validate)

    p_sim = sub.add_parser("simulate", help="Run 8,760-hr PV + 3D shading + ESS optimization and emit RO-Crate audit")
    p_sim.add_argument("--config", required=True, help="Site JSON configuration file")
    p_sim.add_argument("-o", "--output", default="outputs/run", help="Output bundle directory")
    p_sim.add_argument("--weather", default="", help="Optional cached CSV/PVGIS JSON weather file")
    p_sim.add_argument("--cache-dir", default="", help="Optional cache directory for PVGIS downloads")
    p_sim.add_argument(
        "--auto-horizon",
        choices=("none", "pvgis", "copernicus"),
        default="none",
        help="Automatically fetch 36-azimuth terrain horizon from Copernicus DEM or EU PVGIS",
    )
    p_sim.set_defaults(func=_cmd_simulate)

    p_hor = sub.add_parser("horizon", help="Compute Copernicus DEM horizon and compare with EU PVGIS")
    p_hor.add_argument("--lat", type=float, required=True, help="Site latitude")
    p_hor.add_argument("--lon", type=float, required=True, help="Site longitude")
    p_hor.add_argument("--cache-dir", default="", help="Optional cache directory for elevation downloads")
    p_hor.add_argument("--json", action="store_true", help="Emit JSON payload")
    p_hor.set_defaults(func=_cmd_horizon)

    p_srv = sub.add_parser("serve", help="Serve static standalone Web UI locally")
    p_srv.add_argument("--dir", default="docs", help="Directory containing index.html")
    p_srv.add_argument("--port", type=int, default=8780, help="Local HTTP port")
    p_srv.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
