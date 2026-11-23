"""Tests for clean-room .PAN/.OND parsers and equipment validation CLI."""

from __future__ import annotations

from pathlib import Path

from heliostack.cli import main as cli_main
from heliostack.formats import parse_ond, parse_pan, validate_equipment_path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "equipment"


def test_parse_valid_pan_and_ond_fixtures() -> None:
    mod, mod_issues = parse_pan(FIXTURES / "ref_550w_bifacial.pan")
    assert mod is not None
    assert not any(i.severity == "ERROR" for i in mod_issues)
    assert mod.p_nom_w == 550.0
    assert 0.004 < mod.alpha_sc_a_per_c < 0.007  # converted mA/C -> A/C
    assert mod.bifaciality_factor == 0.80

    inv, inv_issues = parse_ond(FIXTURES / "ref_250kw_inverter.ond")
    assert inv is not None
    assert not any(i.severity == "ERROR" for i in inv_issues)
    assert inv.p_nom_ac_kw == 250.0
    assert len(inv.efficiency_curve_pct) == 7


def test_reject_physically_impossible_pan_and_ond() -> None:
    mod, mod_issues = parse_pan(FIXTURES / "invalid_module.pan")
    assert mod is None
    codes = {i.code for i in mod_issues}
    assert "NON_POSITIVE_ELECTRICAL" in codes
    assert "INVALID_VMP_VOC" in codes
    assert "INVALID_IMP_ISC" in codes
    assert "INVALID_DIODE_RESISTANCE" in codes

    inv, inv_issues = parse_ond(FIXTURES / "invalid_inverter.ond")
    assert inv is None
    inv_codes = {i.code for i in inv_issues}
    assert "INVALID_INVERTER_POWER" in inv_codes
    assert "INVALID_MPPT_WINDOW" in inv_codes
    assert "INVALID_EFFICIENCY" in inv_codes


def test_reject_nan_and_json_specs() -> None:
    bad_json = '{"p_nom_w": NaN, "v_mp_v": 40, "i_mp_a": 12, "v_oc_v": 48, "i_sc_a": 13}'
    mod, issues = parse_pan(bad_json)
    assert mod is None
    assert any(i.severity == "ERROR" for i in issues)

    good_json = (
        '{"manufacturer": "OpenTest", "model": "OT-400", "p_nom_w": 400, '
        '"v_mp_v": 34.0, "i_mp_a": 11.76, "v_oc_v": 41.0, "i_sc_a": 12.5}'
    )
    mod_ok, issues_ok = parse_pan(good_json)
    assert mod_ok is not None
    assert not any(i.severity == "ERROR" for i in issues_ok)


def test_cli_validate_exit_codes() -> None:
    assert cli_main(["validate", str(FIXTURES / "ref_550w_bifacial.pan"), "--json"]) == 0
    assert cli_main(["validate", str(FIXTURES / "invalid_module.pan")]) == 1
    assert cli_main(["validate", str(FIXTURES / "does_not_exist.pan")]) == 2

    records, code = validate_equipment_path(FIXTURES)
    assert code == 1
    assert len(records) == 6
    assert sum(1 for r in records if r["passed"]) == 4


def test_inverter_default_curve_warning_and_bad_curve_rejection() -> None:
    no_curve_json = (
        '{"manufacturer": "OpenInv", "model": "OI-100", "p_nom_ac_kw": 100.0, '
        '"p_max_ac_kw": 110.0, "v_mpp_min_v": 500.0, "v_mpp_max_v": 1000.0, '
        '"eff_max_pct": 98.5, "eff_euro_pct": 98.0}'
    )
    inv_ok, warn_issues = parse_ond(no_curve_json)
    assert inv_ok is not None
    assert any(i.code == "DEFAULT_EFF_CURVE" for i in warn_issues)
    assert len(inv_ok.efficiency_curve_pct) == 5

    bad_curve_json = (
        '{"p_nom_ac_kw": 100.0, "v_mpp_min_v": 500.0, "v_mpp_max_v": 1000.0, '
        '"efficiency_curve_pct": [[10, 105.0], [50, 98.0]]}'
    )
    inv_bad, err_issues = parse_ond(bad_curve_json)
    assert inv_bad is None
    assert any(i.code == "OUT_OF_RANGE_CURVE_POINT" for i in err_issues)
