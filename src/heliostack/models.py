"""Core immutable-friendly data models for HelioStack simulations and audits."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ValidationIssue:
    """Single validation finding emitted by equipment or site integrity checks."""

    severity: str  # "ERROR" | "WARNING"
    code: str
    message: str
    field: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PVModuleSpec:
    """Physical and single-diode model parameters for a photovoltaic module (.PAN)."""

    manufacturer: str
    model: str
    p_nom_w: float
    v_mp_v: float
    i_mp_a: float
    v_oc_v: float
    i_sc_a: float
    cells_in_series: int = 72
    cells_in_parallel: int = 2
    alpha_sc_a_per_c: float = 0.0052
    beta_voc_pct_per_c: float = -0.25
    gamma_pmp_pct_per_c: float = -0.30
    gamma_ref: float = 1.02
    mu_gamma: float = 0.0
    r_s_ohm: float = 0.18
    r_sh_ref_ohm: float = 420.0
    r_sh_0_ohm: float = 1600.0
    r_sh_exp: float = 5.5
    eg_ref_ev: float = 1.121
    iam_b0: float = 0.05
    bifaciality_factor: float = 0.80
    width_m: float = 1.134
    length_m: float = 2.278
    source_format: str = "pan"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InverterSpec:
    """Electrical and efficiency curve parameters for a PV inverter (.OND)."""

    manufacturer: str
    model: str
    p_nom_ac_kw: float
    p_max_ac_kw: float
    v_mpp_min_v: float
    v_mpp_max_v: float
    v_abs_max_v: float = 1500.0
    eff_max_pct: float = 98.8
    eff_euro_pct: float = 98.4
    p_threshold_kw: float = 0.5
    night_loss_kw: float = 0.03
    efficiency_curve_pct: list[tuple[float, float]] = field(default_factory=list)
    source_format: str = "ond"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["efficiency_curve_pct"] = [
            [float(x), float(y)] for x, y in self.efficiency_curve_pct
        ]
        return data


@dataclass(slots=True)
class ObstacleBox3D:
    """Axis-aligned 3D obstacle box near the PV array (site-local ENU meters)."""

    name: str
    center_east_m: float
    center_north_m: float
    width_east_m: float
    depth_north_m: float
    height_m: float
    base_elevation_m: float = 0.0

    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        hx = max(0.05, self.width_east_m * 0.5)
        hy = max(0.05, self.depth_north_m * 0.5)
        bmin = (self.center_east_m - hx, self.center_north_m - hy, self.base_elevation_m)
        bmax = (
            self.center_east_m + hx,
            self.center_north_m + hy,
            self.base_elevation_m + max(0.05, self.height_m),
        )
        return bmin, bmax

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SiteConfig:
    """Complete site, geometry, mounting, grid cap, ESS, and financial setup."""

    site_name: str
    latitude: float
    longitude: float
    elevation_m: float = 10.0
    surface_tilt_deg: float = 35.0
    surface_azimuth_deg: float = 180.0
    dc_kwp: float = 100.0
    gcr: float = 0.45
    array_height_m: float = 1.2
    row_length_m: float = 20.0
    row_depth_m: float = 2.3
    albedo: float = 0.20
    soiling_loss_frac: float = 0.02
    dc_wiring_loss_frac: float = 0.015
    mismatch_loss_frac: float = 0.015
    availability_frac: float = 0.99
    mounting_mode: str = "open_rack"  # "open_rack" | "convective_land" | "floating_pv"
    use_3d_shading: bool = True
    obstacles: list[ObstacleBox3D] = field(default_factory=list)
    horizon_elev_deg_36: list[float] = field(default_factory=lambda: [0.0] * 36)
    grid_export_limit_kw: float = 95.0
    ess_energy_kwh: float = 0.0
    ess_power_kw: float = 0.0
    ess_eta_charge: float = 0.95
    ess_eta_discharge: float = 0.95
    ess_soc_min: float = 0.10
    ess_soc_max: float = 0.90
    tariff_export_eur_kwh: float = 0.11
    tariff_peak_eur_kwh: float = 0.16
    capex_pv_eur_kwp: float = 780.0
    capex_ess_eur_kwh: float = 240.0
    opex_eur_kwp_yr: float = 14.0
    discount_rate: float = 0.05
    project_life_years: int = 20

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["obstacles"] = [obs.to_dict() for obs in self.obstacles]
        return data


@dataclass(slots=True)
class LossWaterfall:
    """PVsyst-compatible annual energy & loss waterfall summary."""

    ghi_kwh_m2: float
    poa_global_kwh_m2: float
    poa_effective_kwh_m2: float
    transposition_gain_pct: float
    iam_loss_pct: float
    shading_loss_pct: float
    diffuse_svf: float
    soiling_loss_pct: float
    bifacial_gain_pct: float
    thermal_loss_pct: float
    mean_cell_temp_day_c: float
    dc_nominal_kwh_yr: float
    dc_after_losses_kwh_yr: float
    mismatch_wiring_loss_pct: float
    inverter_eff_loss_pct: float
    clipping_loss_pct: float
    net_ac_before_curtail_kwh_yr: float
    specific_yield_kwh_kwp: float
    performance_ratio: float
    p50_kwh_yr: float
    p75_kwh_yr: float
    p90_kwh_yr: float
    p99_kwh_yr: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ESSMetrics:
    """8,760-hour LP optimization outputs for curtailment recovery and economics."""

    solver_success: bool
    solver_message: str
    solve_time_s: float
    pv_ac_available_kwh_yr: float
    curtailed_no_ess_kwh_yr: float
    curtailed_with_ess_kwh_yr: float
    curtailment_recovery_pct: float
    net_export_no_ess_kwh_yr: float
    net_export_with_ess_kwh_yr: float
    ess_charge_kwh_yr: float
    ess_discharge_kwh_yr: float
    ess_hvac_aux_kwh_yr: float
    annual_cycles: float
    revenue_no_ess_eur_yr: float
    revenue_with_ess_eur_yr: float
    revenue_uplift_eur_yr: float
    lcoe_eur_kwh: float
    simple_payback_ess_yr: float | None
    npv_20yr_eur: float
    max_hourly_conservation_err_kw: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SimulationResult:
    """Full end-to-end deterministic simulation output bundle."""

    site: SiteConfig
    module: PVModuleSpec
    inverter: InverterSpec
    weather_provenance: dict[str, Any]
    loss_waterfall: LossWaterfall
    ess_metrics: ESSMetrics
    monthly_ac_kwh: list[float]
    monthly_curtailed_no_ess_kwh: list[float]
    monthly_curtailed_with_ess_kwh: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site.to_dict(),
            "module": self.module.to_dict(),
            "inverter": self.inverter.to_dict(),
            "weather_provenance": self.weather_provenance,
            "loss_waterfall": self.loss_waterfall.to_dict(),
            "ess_metrics": self.ess_metrics.to_dict(),
            "monthly_ac_kwh": [round(v, 3) for v in self.monthly_ac_kwh],
            "monthly_curtailed_no_ess_kwh": [
                round(v, 3) for v in self.monthly_curtailed_no_ess_kwh
            ],
            "monthly_curtailed_with_ess_kwh": [
                round(v, 3) for v in self.monthly_curtailed_with_ess_kwh
            ],
        }
