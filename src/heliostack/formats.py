"""Clean-room parsers and physical-integrity validators for .PAN, .OND, and JSON specs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from heliostack.models import InverterSpec, PVModuleSpec, ValidationIssue


def _parse_kv_file(text: str) -> dict[str, str]:
    """Parse key=value sections from PVsyst-style .PAN/.OND ASCII definitions."""
    raw: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", ";", "End of ")):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        raw[key.strip()] = value.strip()
    return raw


def _parse_float(
    raw: dict[str, Any],
    keys: tuple[str, ...],
    issues: list[ValidationIssue],
    field_name: str,
    default: float | None = None,
    required: bool = False,
) -> float | None:
    """Safely extract and finite-check a numeric field across alias keys."""
    for key in keys:
        if key in raw and raw[key] not in ("", None):
            try:
                val = float(raw[key])
            except (TypeError, ValueError):
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="NON_NUMERIC_VALUE",
                        message=f"Field '{key}' is not numeric: {raw[key]!r}",
                        field=field_name,
                    )
                )
                return None
            if not math.isfinite(val):
                issues.append(
                    ValidationIssue(
                        severity="ERROR",
                        code="NON_FINITE_VALUE",
                        message=f"Field '{key}' must be finite, got {val!r}",
                        field=field_name,
                    )
                )
                return None
            return val
    if required:
        issues.append(
            ValidationIssue(
                severity="ERROR",
                code="MISSING_MANDATORY_FIELD",
                message=f"Missing mandatory parameter for '{field_name}' ({', '.join(keys)})",
                field=field_name,
            )
        )
        return None
    return default


def _parse_eff_curve(raw: Any, issues: list[ValidationIssue]) -> list[tuple[float, float]]:
    """Parse inverter efficiency curve from either 'load:eff,...' string or nested list."""
    points: list[tuple[float, float]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                try:
                    lp = float(item[0])
                    ef = float(item[1])
                except (TypeError, ValueError):
                    issues.append(
                        ValidationIssue("ERROR", "INVALID_EFF_CURVE", f"Bad curve entry {item!r}", "efficiency_curve_pct")
                    )
                    continue
                if not (math.isfinite(lp) and math.isfinite(ef)):
                    issues.append(
                        ValidationIssue("ERROR", "NON_FINITE_CURVE", f"Non-finite curve point {item!r}", "efficiency_curve_pct")
                    )
                    continue
                points.append((lp, ef))
    elif isinstance(raw, str) and raw.strip():
        for chunk in raw.split(","):
            part = chunk.strip()
            if ":" not in part:
                continue
            lhs, rhs = part.split(":", 1)
            try:
                lp = float(lhs.strip())
                ef = float(rhs.strip())
            except ValueError:
                issues.append(
                    ValidationIssue("ERROR", "INVALID_EFF_CURVE", f"Bad curve entry {part!r}", "efficiency_curve_pct")
                )
                continue
            points.append((lp, ef))
    points.sort(key=lambda pair: pair[0])
    for lp, ef in points:
        if lp < 0.0 or lp > 150.0 or ef <= 0.0 or ef > 100.0:
            issues.append(
                ValidationIssue(
                    severity="ERROR",
                    code="OUT_OF_RANGE_CURVE_POINT",
                    message=f"Inverter curve point load={lp}%, eff={ef}% is physically invalid.",
                    field="efficiency_curve_pct",
                )
            )
    return points


def _load_structured_spec(path_or_text: str | Path) -> tuple[dict[str, Any], str]:
    """Load either a JSON spec or a PVsyst-style key=value text block."""
    if isinstance(path_or_text, Path) or (
        isinstance(path_or_text, str) and "\n" not in path_or_text and Path(path_or_text).exists()
    ):
        p = Path(path_or_text)
        text = p.read_text(encoding="utf-8", errors="replace")
        fmt = "json" if p.suffix.lower() == ".json" else p.suffix.lower().lstrip(".") or "txt"
    else:
        text = str(path_or_text)
        fmt = "json" if text.lstrip().startswith("{") else "txt"

    if fmt == "json":
        return json.loads(text), "json"
    return _parse_kv_file(text), fmt


def parse_pan(path_or_text: str | Path) -> tuple[PVModuleSpec | None, list[ValidationIssue]]:
    """Parse and physically validate a .PAN or JSON PV module specification."""
    issues: list[ValidationIssue] = []
    try:
        raw, fmt = _load_structured_spec(path_or_text)
    except Exception as exc:
        return None, [ValidationIssue("ERROR", "PARSE_ERROR", f"Cannot parse module spec: {exc}")]

    p_nom = _parse_float(raw, ("PNom", "p_nom_w"), issues, "p_nom_w", required=True)
    v_mp = _parse_float(raw, ("Vmp", "v_mp_v"), issues, "v_mp_v", required=True)
    i_mp = _parse_float(raw, ("Imp", "i_mp_a"), issues, "i_mp_a", required=True)
    v_oc = _parse_float(raw, ("Voc", "v_oc_v"), issues, "v_oc_v", required=True)
    i_sc = _parse_float(raw, ("Isc", "i_sc_a"), issues, "i_sc_a", required=True)

    c_ser = int(_parse_float(raw, ("NCelS", "cells_in_series"), issues, "cells_in_series", default=72.0) or 72)
    c_par = int(_parse_float(raw, ("NCelP", "cells_in_parallel"), issues, "cells_in_parallel", default=2.0) or 2)
    width_m = _parse_float(raw, ("Width", "width_m"), issues, "width_m", default=1.134) or 1.134
    length_m = _parse_float(raw, ("Height", "length_m"), issues, "length_m", default=2.278) or 2.278
    gamma_ref = _parse_float(raw, ("Gamma", "gamma_ref"), issues, "gamma_ref", default=1.02)
    mu_gamma = _parse_float(raw, ("muGamma", "mu_gamma"), issues, "mu_gamma", default=0.0)
    r_s = _parse_float(raw, ("RSerie", "r_s_ohm"), issues, "r_s_ohm", default=0.185)
    r_sh = _parse_float(raw, ("RShunt", "r_sh_ref_ohm"), issues, "r_sh_ref_ohm", default=440.0)
    r_sh_0 = _parse_float(raw, ("Rp_0", "Rshex0", "r_sh_0_ohm"), issues, "r_sh_0_ohm", default=1650.0)
    r_sh_exp = _parse_float(raw, ("Rp_Exp", "RshExp", "r_sh_exp"), issues, "r_sh_exp", default=5.5)
    bifi = _parse_float(raw, ("BifacialityFactor", "bifaciality_factor"), issues, "bifaciality_factor", default=0.80)
    iam_b0 = _parse_float(raw, ("IAM_b0", "iam_b0"), issues, "iam_b0", default=0.05)

    alpha_raw = _parse_float(raw, ("alpha_sc_a_per_c", "muISC"), issues, "alpha_sc_a_per_c", default=0.0052)
    if alpha_raw is not None and "alpha_sc_a_per_c" not in raw and abs(alpha_raw) > 0.2:
        alpha_sc = alpha_raw / 1000.0  # Standard PVsyst muISC unit is mA/degC
    else:
        alpha_sc = alpha_raw if alpha_raw is not None else 0.0052

    gamma_pmp = _parse_float(raw, ("muPmpReq", "gamma_pmp_pct_per_c"), issues, "gamma_pmp_pct_per_c", default=-0.30) or -0.30
    mu_voc = _parse_float(raw, ("muVocSpec", "beta_voc_pct_per_c"), issues, "beta_voc_pct_per_c", default=-0.25) or -0.25
    if "muVocSpec" in raw and v_oc and v_oc > 0:
        beta_voc_pct = ((mu_voc / 1000.0) if abs(mu_voc) > 2.0 else mu_voc) / v_oc * 100.0
    else:
        beta_voc_pct = mu_voc

    if None in (p_nom, v_mp, i_mp, v_oc, i_sc, gamma_ref, mu_gamma, r_s, r_sh, r_sh_0, r_sh_exp, bifi, iam_b0):
        return None, issues

    if p_nom <= 0 or v_mp <= 0 or i_mp <= 0 or v_oc <= 0 or i_sc <= 0:
        issues.append(ValidationIssue("ERROR", "NON_POSITIVE_ELECTRICAL", "Module PNom/Vmp/Imp/Voc/Isc must all be > 0."))
    if v_mp >= v_oc:
        issues.append(ValidationIssue("ERROR", "INVALID_VMP_VOC", f"Vmp ({v_mp} V) must be strictly less than Voc ({v_oc} V).", "v_mp_v"))
    if i_mp >= i_sc:
        issues.append(ValidationIssue("ERROR", "INVALID_IMP_ISC", f"Imp ({i_mp} A) must be strictly less than Isc ({i_sc} A).", "i_mp_a"))
    if p_nom > 0 and abs(p_nom - (v_mp * i_mp)) / p_nom > 0.15:
        issues.append(
            ValidationIssue(
                "ERROR",
                "POWER_PRODUCT_MISMATCH",
                f"Vmp*Imp ({v_mp * i_mp:.1f} W) deviates >15% from PNom ({p_nom:.1f} W).",
                "p_nom_w",
            )
        )
    if r_s < 0 or r_sh <= 0 or r_sh_0 <= 0:
        issues.append(ValidationIssue("ERROR", "INVALID_DIODE_RESISTANCE", "Series resistance >= 0 and shunt resistances > 0 required.", "r_s_ohm"))
    if not (0.5 <= gamma_ref <= 2.5):
        issues.append(ValidationIssue("ERROR", "INVALID_DIODE_GAMMA", f"Diode ideality factor Gamma={gamma_ref} out of physical bounds [0.5, 2.5].", "gamma_ref"))
    if not (0.0 <= bifi <= 1.0):
        issues.append(ValidationIssue("ERROR", "INVALID_BIFACIALITY", f"Bifaciality factor {bifi} must lie within [0, 1].", "bifaciality_factor"))
    if not (0.0 <= iam_b0 <= 0.5):
        issues.append(ValidationIssue("ERROR", "INVALID_IAM_B0", f"IAM_b0={iam_b0} must lie within [0, 0.5].", "iam_b0"))
    if c_ser <= 0 or c_par <= 0 or width_m <= 0 or length_m <= 0:
        issues.append(ValidationIssue("ERROR", "INVALID_MODULE_GEOMETRY", "Cell counts and module dimensions must be > 0."))

    if any(i.severity == "ERROR" for i in issues):
        return None, issues

    spec = PVModuleSpec(
        manufacturer=str(raw.get("Manufacturer", raw.get("manufacturer", "Unknown"))),
        model=str(raw.get("Model", raw.get("model", "Unknown"))),
        p_nom_w=float(p_nom),
        v_mp_v=float(v_mp),
        i_mp_a=float(i_mp),
        v_oc_v=float(v_oc),
        i_sc_a=float(i_sc),
        cells_in_series=c_ser,
        cells_in_parallel=c_par,
        alpha_sc_a_per_c=float(alpha_sc),
        beta_voc_pct_per_c=float(beta_voc_pct),
        gamma_pmp_pct_per_c=float(gamma_pmp),
        gamma_ref=float(gamma_ref),
        mu_gamma=float(mu_gamma),
        r_s_ohm=float(r_s),
        r_sh_ref_ohm=float(r_sh),
        r_sh_0_ohm=float(r_sh_0),
        r_sh_exp=float(r_sh_exp),
        iam_b0=float(iam_b0),
        bifaciality_factor=float(bifi),
        width_m=float(width_m),
        length_m=float(length_m),
        source_format="json" if fmt == "json" else "pan",
    )
    return spec, issues


def parse_ond(path_or_text: str | Path) -> tuple[InverterSpec | None, list[ValidationIssue]]:
    """Parse and physically validate a .OND or JSON inverter specification."""
    issues: list[ValidationIssue] = []
    try:
        raw, fmt = _load_structured_spec(path_or_text)
    except Exception as exc:
        return None, [ValidationIssue("ERROR", "PARSE_ERROR", f"Cannot parse inverter spec: {exc}")]

    p_nom = _parse_float(raw, ("PNomConv", "p_nom_ac_kw"), issues, "p_nom_ac_kw", required=True)
    p_max = _parse_float(raw, ("PMaxOUT", "p_max_ac_kw"), issues, "p_max_ac_kw", default=p_nom)
    v_min = _parse_float(raw, ("VMppMin", "v_mpp_min_v"), issues, "v_mpp_min_v", required=True)
    v_max = _parse_float(raw, ("VMPPMax", "VMppMax", "v_mpp_max_v"), issues, "v_mpp_max_v", required=True)
    v_abs = _parse_float(raw, ("VAbsMax", "v_abs_max_v"), issues, "v_abs_max_v", default=1500.0)
    eff_max = _parse_float(raw, ("EfficMax", "eff_max_pct"), issues, "eff_max_pct", default=98.8)
    eff_euro = _parse_float(raw, ("EfficEuro", "eff_euro_pct"), issues, "eff_euro_pct", default=98.4)
    p_thresh = _parse_float(raw, ("PSeuil", "p_threshold_kw"), issues, "p_threshold_kw", default=0.5)
    night_loss = _parse_float(raw, ("Night_Loss", "night_loss_kw"), issues, "night_loss_kw", default=0.03)
    curve = _parse_eff_curve(raw.get("TPNomEff", raw.get("efficiency_curve_pct", "")), issues)

    if None in (p_nom, p_max, v_min, v_max, v_abs, eff_max, eff_euro, p_thresh, night_loss):
        return None, issues

    if p_nom <= 0 or p_max < p_nom:
        issues.append(ValidationIssue("ERROR", "INVALID_INVERTER_POWER", "PNomConv > 0 and PMaxOUT >= PNomConv required.", "p_nom_ac_kw"))
    if v_min <= 0 or v_max <= v_min or v_abs < v_max:
        issues.append(ValidationIssue("ERROR", "INVALID_MPPT_WINDOW", "0 < VMppMin < VMPPMax <= VAbsMax required.", "v_mpp_min_v"))
    if not (0.0 < eff_max <= 100.0) or not (0.0 < eff_euro <= eff_max):
        issues.append(ValidationIssue("ERROR", "INVALID_EFFICIENCY", "0 < EfficEuro <= EfficMax <= 100 required.", "eff_max_pct"))
    if p_thresh < 0 or night_loss < 0:
        issues.append(ValidationIssue("ERROR", "NEGATIVE_LOSS_THRESHOLD", "Threshold and night loss cannot be negative."))

    if any(i.severity == "ERROR" for i in issues):
        return None, issues

    if not curve:
        curve = [(5.0, eff_euro - 1.5), (10.0, eff_euro - 0.5), (30.0, eff_max - 0.1), (50.0, eff_max), (100.0, eff_max - 0.5)]
        issues.append(ValidationIssue("WARNING", "DEFAULT_EFF_CURVE", "No TPNomEff points supplied; synthesized curve from EfficEuro/EfficMax.", "efficiency_curve_pct"))

    spec = InverterSpec(
        manufacturer=str(raw.get("Manufacturer", raw.get("manufacturer", "Unknown"))),
        model=str(raw.get("Model", raw.get("model", "Unknown"))),
        p_nom_ac_kw=float(p_nom),
        p_max_ac_kw=float(p_max),
        v_mpp_min_v=float(v_min),
        v_mpp_max_v=float(v_max),
        v_abs_max_v=float(v_abs),
        eff_max_pct=float(eff_max),
        eff_euro_pct=float(eff_euro),
        p_threshold_kw=float(p_thresh),
        night_loss_kw=float(night_loss),
        efficiency_curve_pct=curve,
        source_format="json" if fmt == "json" else "ond",
    )
    return spec, issues


def validate_equipment_path(target: Path) -> tuple[list[dict[str, Any]], int]:
    """Validate one .pan/.ond file or all equipment files in a directory."""
    files = (
        sorted(p for p in target.rglob("*") if p.is_file() and p.suffix.lower() in (".pan", ".ond", ".json"))
        if target.is_dir()
        else [target]
    )
    if not files:
        return [], 2

    records: list[dict[str, Any]] = []
    errors_total = 0
    for fpath in files:
        suffix = fpath.suffix.lower()
        if suffix == ".pan":
            spec, issues = parse_pan(fpath)
            kind = "module"
        elif suffix == ".ond":
            spec, issues = parse_ond(fpath)
            kind = "inverter"
        else:
            raw = json.loads(fpath.read_text(encoding="utf-8"))
            if "p_nom_ac_kw" in raw or "PNomConv" in raw:
                spec, issues = parse_ond(fpath)
                kind = "inverter"
            else:
                spec, issues = parse_pan(fpath)
                kind = "module"
        err_cnt = sum(1 for i in issues if i.severity == "ERROR")
        errors_total += err_cnt
        records.append(
            {
                "file": str(fpath),
                "kind": kind,
                "passed": err_cnt == 0 and spec is not None,
                "errors": err_cnt,
                "warnings": sum(1 for i in issues if i.severity == "WARNING"),
                "issues": [i.to_dict() for i in issues],
            }
        )
    return records, (1 if errors_total > 0 else 0)
