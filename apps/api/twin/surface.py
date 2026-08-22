"""
WORKFACE — the Work Face Thermal Twin surface model.  T3, Day 6, Task D.

    from apps.api.twin.surface import derive_coefficients, surface_offset_c, t_surf_c
    coeff = derive_coefficients(capture)          # a WorkFaceTwinCapture (T2's Day-5 handoff)
    t = t_surf_c(t_air=41.0, ghi=0.0, wind_ms=1.2, cloud_octas=0.0, coeff=coeff)

Handoff #4 (T2 -> T3): the raw FortyGuard `satellite` + `streetview` segmentation
per work face becomes the first-order surface energy balance of
WORKFACE_TECH_SPEC §6.2:

    T_surf(t) = T_air(t) + (alpha * GHI(t) * psi - eps * dLW_night(t)) / (h_c(V) + h_r)
    h_c(V) = 5.7 + 3.8 * V         h_r ~= 5 W/m2K
    dLW_night = Q_lw_clear * (1 - cloud_octas / 8)      (both solar gain and the
    night longwave loss scale with the single-hemisphere sky fraction psi)

This REPLACES the Day-4.5 guess in scripts/make_thermal_fixtures.py, which keyed
alpha / eps off a single `surface_class` string because the twin had not landed.
Now alpha and eps are the fraction-weighted mean of the real satellite land
cover, and psi is the real streetview sky fraction.

    NOTE (report): this is a NEW file. apps/api/twin/capture.py and
    apps/api/twin/twin_capture.py are T2's live-capture path; surface.py is T3's
    transform of that capture and does not collide with either.

THREE HONESTY REQUIREMENTS THIS FILE ENFORCES
---------------------------------------------
1. `shadow` IS NOT A MATERIAL (WORKFACE_T3_DAY56 §6 D1). It is an artefact of
   when the satellite image was taken. Averaging an absorptivity into it is
   meaningless, and treating it as reduced insolation would assert the shadow is
   present at ALL hours, which it is not. So `shadow` (and any non-material class)
   is DROPPED and the remaining fractions are renormalised.

2. `back` IS EMPTY ON ALL 40 CAPTURES (§6 D2). Only the front hemisphere was
   segmented, so psi is a single-hemisphere estimate presented as a whole-sky
   one. Under §6.2's "degrade gracefully" rule that is a real confidence
   downgrade — one step below whatever the capture claims — and the downgrade
   reaches the UI via `SurfaceCoefficients.confidence`.

3. THE TWIN'S SKY % MATCHES work_faces.geojson's sky_view_factor EXACTLY
   (45 <-> 0.45, 97 <-> 0.97) because T2's replay fixture was seeded from the
   same generator record. THIS IS NOT INDEPENDENT VALIDATION AND IS NEVER
   PRESENTED AS ANY. `tests/test_surface.py` asserts the derivation PATH runs; it
   does NOT assert twin/generator agreement (that would check nothing).

THE COEFFICIENT THAT DECIDES THE DEMO (§6 D3)
---------------------------------------------
`eps` for galvanised steel (segmentation class `metal`) is the single most
load-bearing number in the project. Bright new galvanising has a LOW thermal
emissivity (~0.2-0.3); weathered galvanising is far higher (~0.7-0.9). The hero
dawn closure IS the `eps * dLW_night` undershoot, so it lives or dies on this
number. `EPS_METAL_WEATHERED = 0.85` is the default and it assumes a WEATHERED,
erected galvanised deck ("four months of Phoenix sun"). `eps_metal` is a
parameter precisely so the sensitivity can be run at both ends of that range —
see scripts/make_surface_fixtures.py --sensitivity and the Day-6 report.

Coefficient sources are cited in docs/CITATIONS.md.

# ---------------------------------------------------------------------------
# WORKFACE NAMING RULE — do not violate.
#   activity_id     = a scheduled construction task (from P6 / the generator)
#   fg_activity_id  = a FortyGuard async job handle (from submit -> /v1/status/{id})
# ---------------------------------------------------------------------------
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from packages.schemas.twin_segmentation import (
    Confidence,
    Segmentation,
    WorkFaceTwinCapture,
)

# --------------------------------------------------------------------------- #
# Coefficients — published ranges, cited in docs/CITATIONS.md.
# Keyed on the SEGMENTATION model's own class taxonomy (metal/concrete/shadow/
# vegetation/other for satellite), NOT on the work_face surface_class string.
# --------------------------------------------------------------------------- #

# Solar (shortwave) absorptivity per land-cover class (WORKFACE_T3_DAY56 §6 D1;
# ASHRAE Fundamentals ch. 26 surface-property tables). `metal` is bright
# galvanised steel — a LOW absorber that runs hot from near-zero thermal mass.
ALPHA_BY_CLASS: dict[str, float] = {
    "asphalt": 0.90,
    "concrete": 0.65,          # aged concrete
    "metal": 0.25,             # galvanised steel
    "coated_steel": 0.45,
    "vegetation": 0.75,
    "bare_soil": 0.75,         # dry desert soil (ADDED; ASHRAE ch.26 soil range 0.70-0.80)
    "building": 0.60,          # streetview built surface, mid-range (rarely used for alpha)
    "ground": 0.70,
}

# Thermal (longwave) emissivity per land-cover class. `metal` (galvanised) is the
# load-bearing one (see module docstring) and is a parameter, not a constant.
EPS_METAL_WEATHERED = 0.85     # DEFAULT: weathered, erected galvanised deck
EPS_METAL_BRIGHT = 0.23        # bright new galvanising — the low end of the range
EPS_BY_CLASS: dict[str, float] = {
    "asphalt": 0.93,
    "concrete": 0.90,
    "coated_steel": 0.88,
    "vegetation": 0.95,
    "bare_soil": 0.92,
    "building": 0.90,
    "ground": 0.92,
}

# Policy for `other` (§6 D1): a recognised-but-unclassified MATERIAL (unlike
# shadow). Given a neutral mid-range built-surface value rather than being
# dropped, so its mass still counts. Documented as a policy default, cited.
OTHER_ALPHA = 0.60
OTHER_EPS = 0.90

# Non-material classes: DROPPED before renormalising (see honesty requirement 1).
NON_MATERIAL_CLASSES = frozenset({"shadow"})

# Energy-balance constants (WORKFACE_TECH_SPEC §6.2; docs/CITATIONS.md).
Q_LW_CLEAR_W_M2 = 130.0        # clear-sky net longwave loss flux, arid climate
H_C_A, H_C_B = 5.7, 3.8        # convective coefficient 5.7 + 3.8 * V
H_R = 5.0                      # linearised radiative coefficient, W/m2K


class SurfaceCoefficients(BaseModel):
    """The derived twin coefficients for one work face, with provenance.

    `confidence` is the DERIVED confidence after the §6.2 downgrades — it does
    NOT simply inherit the capture's `capture_confidence` (all 40 claim high; a
    front-hemisphere-only psi makes the honest answer medium)."""
    model_config = ConfigDict(extra="forbid")

    work_face_id: str
    alpha: float = Field(..., description="Fraction-weighted solar absorptivity (shadow excluded).")
    eps: float = Field(..., description="Fraction-weighted thermal emissivity; eps_metal is load-bearing.")
    psi: float = Field(..., ge=0.0, le=1.0, description="Sky view factor from the FRONT streetview sky %.")
    confidence: Confidence
    eps_metal_used: float = Field(..., description="The galvanised-steel emissivity assumed (weathering).")
    psi_front_only: bool = Field(..., description="True when back hemisphere was not segmented (all 40).")
    alpha_from_land_cover: bool = Field(..., description="False when satellite segmentation was absent.")
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# D1 — alpha (and eps) from the satellite land-cover segmentation
# --------------------------------------------------------------------------- #

def _weighted_material_mean(segments: dict[str, float], table: dict[str, float],
                            other_value: float) -> tuple[float, list[str]]:
    """Fraction-weighted mean of a per-class property, with `shadow` (and any
    non-material class) DROPPED and the remaining fractions renormalised.

    A recognised class not in `table` but not a non-material artefact (e.g.
    `other`) uses `other_value`. Returns (value, notes)."""
    notes: list[str] = []
    kept = {c: f for c, f in segments.items()
            if c not in NON_MATERIAL_CLASSES and f and f > 0}
    dropped = sorted(set(segments) & NON_MATERIAL_CLASSES)
    if dropped:
        notes.append(f"dropped non-material class(es) {dropped} and renormalised "
                     f"(shadow is an image artefact, not a surface present at all hours)")
    total = sum(kept.values())
    if total <= 0:
        notes.append("no material fractions after dropping artefacts — using neutral default")
        return other_value, notes

    acc = 0.0
    used_other: list[str] = []
    for cls, frac in kept.items():
        w = frac / total
        if cls in table:
            acc += w * table[cls]
        else:
            acc += w * other_value
            used_other.append(cls)
    if used_other:
        notes.append(f"unclassified material(s) {sorted(used_other)} took the neutral "
                     f"'other' policy value {other_value:g}")
    return acc, notes


def alpha_from_satellite(seg: Segmentation) -> tuple[float, list[str]]:
    return _weighted_material_mean(seg.segments, ALPHA_BY_CLASS, OTHER_ALPHA)


def eps_from_satellite(seg: Segmentation, eps_metal: float = EPS_METAL_WEATHERED
                       ) -> tuple[float, list[str]]:
    table = {**EPS_BY_CLASS, "metal": eps_metal}
    return _weighted_material_mean(seg.segments, table, OTHER_EPS)


# --------------------------------------------------------------------------- #
# D2 — psi from the streetview sky fraction (front hemisphere only)
# --------------------------------------------------------------------------- #

def psi_from_streetview(capture: WorkFaceTwinCapture) -> tuple[float, bool, list[str]]:
    """psi = the `sky` fraction of the FRONT streetview segmentation, 0-1.

    Returns (psi, front_only, notes). `front_only` is True whenever the back
    hemisphere was not segmented (true for all 40 captures) — a real confidence
    downgrade, not merely a note."""
    sv = capture.streetview
    if sv is None:
        return 1.0, False, ["no streetview — psi assumed 1.0 (full sky), confidence low (§6.2)"]
    sky_pct = sv.front.segmentation.segments.get("sky", 0.0)
    psi = max(0.0, min(1.0, sky_pct / 100.0))
    front_only = sv.back is None or not getattr(sv.back, "segmentation", None)
    notes: list[str] = []
    if front_only:
        notes.append("psi is a FRONT-hemisphere estimate presented as whole-sky "
                     "(back not segmented) — confidence downgraded one step (§6.2)")
    return psi, front_only, notes


# --------------------------------------------------------------------------- #
# D4 — confidence downgrades
# --------------------------------------------------------------------------- #

_LADDER = [Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW]


def _step_down(conf: Confidence, steps: int = 1) -> Confidence:
    i = min(len(_LADDER) - 1, _LADDER.index(conf) + steps)
    return _LADDER[i]


def derive_coefficients(capture: WorkFaceTwinCapture,
                        eps_metal: float = EPS_METAL_WEATHERED) -> SurfaceCoefficients:
    """Derive (alpha, eps, psi, confidence) for one work face from its capture.

    Confidence follows §6.2's degrade-gracefully ladder and does NOT inherit the
    capture's claimed `capture_confidence`:
      * satellite + streetview present -> HIGH, then front-hemisphere-only psi
        steps it down to MEDIUM (the reality for all 40 captures);
      * satellite only (no streetview) -> psi assumed 1.0 -> MEDIUM;
      * no satellite segmentation      -> alpha cannot come from land cover -> LOW.
    """
    notes: list[str] = []

    if capture.satellite is not None:
        alpha, an = alpha_from_satellite(capture.satellite.segmentation)
        eps, en = eps_from_satellite(capture.satellite.segmentation, eps_metal)
        alpha_from_land = True
        notes += an + en
    else:
        alpha, eps, alpha_from_land = OTHER_ALPHA, OTHER_EPS, False
        notes.append("no satellite segmentation — alpha/eps fall back to neutral defaults")

    psi, front_only, pn = psi_from_streetview(capture)
    notes += pn

    # Base confidence from source coverage, then apply the front-only downgrade.
    if capture.satellite is not None and capture.streetview is not None:
        conf = Confidence.HIGH
        if front_only:
            conf = _step_down(conf)                 # -> MEDIUM
    elif capture.satellite is not None:
        conf = Confidence.MEDIUM                     # land-cover alpha, psi assumed
    else:
        conf = Confidence.LOW                        # no land-cover alpha

    return SurfaceCoefficients(
        work_face_id=capture.work_face_id,
        alpha=round(alpha, 4), eps=round(eps, 4), psi=round(psi, 4),
        confidence=conf, eps_metal_used=eps_metal, psi_front_only=front_only,
        alpha_from_land_cover=alpha_from_land, notes=notes,
    )


# --------------------------------------------------------------------------- #
# The energy balance (§6.2)
# --------------------------------------------------------------------------- #

def surface_offset_c(*, t_air: float, ghi: float, wind_ms: float, cloud_octas: float,
                     coeff: SurfaceCoefficients) -> float:
    """T_surf - T_air, degrees C. Both solar gain and night longwave loss scale
    with the single-hemisphere psi (an open deck heats hardest in sun AND sheds
    heat fastest to a clear night sky)."""
    h_c = H_C_A + H_C_B * max(0.0, wind_ms)
    net_flux = coeff.alpha * ghi - coeff.eps * Q_LW_CLEAR_W_M2 * (1.0 - cloud_octas / 8.0)
    return net_flux * coeff.psi / (h_c + H_R)


def t_surf_c(*, t_air: float, ghi: float, wind_ms: float, cloud_octas: float,
             coeff: SurfaceCoefficients) -> float:
    return t_air + surface_offset_c(t_air=t_air, ghi=ghi, wind_ms=wind_ms,
                                    cloud_octas=cloud_octas, coeff=coeff)


__all__ = [
    "ALPHA_BY_CLASS", "EPS_BY_CLASS", "EPS_METAL_WEATHERED", "EPS_METAL_BRIGHT",
    "OTHER_ALPHA", "OTHER_EPS", "NON_MATERIAL_CLASSES",
    "Q_LW_CLEAR_W_M2", "H_C_A", "H_C_B", "H_R",
    "SurfaceCoefficients", "alpha_from_satellite", "eps_from_satellite",
    "psi_from_streetview", "derive_coefficients", "surface_offset_c", "t_surf_c",
]
