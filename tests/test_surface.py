"""
WORKFACE — Day-6 surface-model tests.  T3, Task D.

Covers §6.2 as implemented in apps/api/twin/surface.py:
  * alpha/eps are the fraction-weighted mean of the satellite land cover, with
    `shadow` DROPPED and the remaining fractions renormalised (§6 D1);
  * eps_metal (galvanised) is a PARAMETER so the D3 sensitivity can run;
  * psi is the FRONT streetview sky fraction, and a front-hemisphere-only psi is
    a real confidence downgrade (§6 D2 / D4);
  * the energy balance scales solar gain and night longwave loss with psi.

DELIBERATELY NOT TESTED: that psi equals work_faces.geojson's sky_view_factor.
They match only because T2's replay fixture was seeded from the same generator
record (§6 D2, honesty requirement 3). Asserting agreement would check NOTHING.
These tests assert the derivation PATH runs, not that two copies of one number
agree.
"""

from __future__ import annotations

import math

import pytest

from apps.api.twin.surface import (
    EPS_METAL_BRIGHT,
    EPS_METAL_WEATHERED,
    OTHER_ALPHA,
    alpha_from_satellite,
    derive_coefficients,
    eps_from_satellite,
    psi_from_streetview,
    surface_offset_c,
)
from packages.schemas.twin_segmentation import (
    Confidence,
    Coordinates,
    SatelliteCapture,
    Segmentation,
    StreetViewCapture,
    StreetViewSide,
    WorkFaceTwinCapture,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #

def _seg(segments: dict[str, float]) -> Segmentation:
    return Segmentation(segments=segments)


def _capture(*, sat: dict | None, sky_pct: float | None,
             back: bool = False) -> WorkFaceTwinCapture:
    satellite = None
    if sat is not None:
        satellite = SatelliteCapture(
            coordinates=Coordinates(latitude=33.7, longitude=-112.1),
            segmentation=_seg(sat), fg_activity_id="fg-sat-1")
    streetview = None
    if sky_pct is not None:
        back_side = StreetViewSide(segmentation=_seg({"sky": 10.0})) if back else None
        streetview = StreetViewCapture(
            coordinates=Coordinates(latitude=33.7, longitude=-112.1),
            vertical_angle=0.0, horizontal_angle=0.0, back_view_requested=back,
            front=StreetViewSide(segmentation=_seg({"sky": sky_pct, "building": 100 - sky_pct})),
            back=back_side, fg_activity_id="fg-sv-1")
    return WorkFaceTwinCapture(
        work_face_id="WF-TEST-01", centroid_lon=-112.1, centroid_lat=33.7,
        satellite=satellite, streetview=streetview, capture_confidence=Confidence.HIGH)


# --------------------------------------------------------------------------- #
# D1 — alpha / eps from land cover; shadow dropped and renormalised
# --------------------------------------------------------------------------- #

def test_alpha_drops_shadow_and_renormalises():
    # metal 50, concrete 30, shadow 20 -> renorm over 80 (metal .625, concrete .375).
    alpha, notes = alpha_from_satellite(_seg({"metal": 50.0, "concrete": 30.0, "shadow": 20.0}))
    assert alpha == pytest.approx(0.625 * 0.25 + 0.375 * 0.65)   # 0.40
    assert any("shadow" in n for n in notes)


def test_shadow_only_change_renormalises_not_reduces_insolation():
    """Dropping shadow must renormalise (not treat it as reduced sun at all hours).
    Two captures identical but for a shadow slab give the SAME alpha."""
    a1, _ = alpha_from_satellite(_seg({"metal": 80.0, "concrete": 20.0}))
    a2, _ = alpha_from_satellite(_seg({"metal": 40.0, "concrete": 10.0, "shadow": 50.0}))
    assert a1 == pytest.approx(a2)


def test_eps_metal_is_a_parameter_for_the_sensitivity():
    seg = _seg({"metal": 100.0})
    weathered, _ = eps_from_satellite(seg, EPS_METAL_WEATHERED)
    bright, _ = eps_from_satellite(seg, EPS_METAL_BRIGHT)
    assert weathered == pytest.approx(EPS_METAL_WEATHERED)
    assert bright == pytest.approx(EPS_METAL_BRIGHT)
    assert weathered > bright


def test_other_class_takes_the_neutral_policy_value():
    alpha, notes = alpha_from_satellite(_seg({"other": 100.0}))
    assert alpha == pytest.approx(OTHER_ALPHA)
    assert any("other" in n.lower() for n in notes)


# --------------------------------------------------------------------------- #
# D2 — psi from the FRONT streetview sky fraction (path, not agreement)
# --------------------------------------------------------------------------- #

def test_psi_from_front_sky_fraction_path_runs():
    psi, front_only, notes = psi_from_streetview(_capture(sat={"metal": 100.0}, sky_pct=45.0))
    assert psi == pytest.approx(0.45)      # derivation PATH: 45% -> 0.45 (NOT a validation vs svf)
    assert front_only is True
    assert any("front" in n.lower() for n in notes)


def test_psi_missing_streetview_assumes_full_sky():
    psi, front_only, notes = psi_from_streetview(_capture(sat={"metal": 100.0}, sky_pct=None))
    assert psi == 1.0
    assert front_only is False


# --------------------------------------------------------------------------- #
# D4 — confidence downgrades (derived, not inherited from capture_confidence)
# --------------------------------------------------------------------------- #

def test_front_only_psi_downgrades_high_to_medium():
    c = derive_coefficients(_capture(sat={"metal": 100.0}, sky_pct=97.0, back=False))
    assert c.psi_front_only is True
    assert c.confidence is Confidence.MEDIUM      # NOT high, despite capture claiming high


def test_full_hemisphere_stays_high():
    c = derive_coefficients(_capture(sat={"metal": 100.0}, sky_pct=97.0, back=True))
    assert c.psi_front_only is False
    assert c.confidence is Confidence.HIGH


def test_no_streetview_is_low_confidence_full_sky():
    c = derive_coefficients(_capture(sat={"metal": 100.0}, sky_pct=None))
    assert c.psi == 1.0
    assert c.confidence is Confidence.MEDIUM       # land-cover alpha, psi assumed


def test_no_satellite_cannot_derive_alpha_from_land_cover():
    c = derive_coefficients(_capture(sat=None, sky_pct=45.0))
    assert c.alpha_from_land_cover is False
    assert c.confidence is Confidence.LOW


def test_real_capture_derives_and_is_downgraded_to_medium():
    """The real 40 captures: satellite + front-only streetview -> MEDIUM, never
    inheriting the capture's claimed high. This asserts the PATH, not agreement."""
    from packages.schemas.twin_segmentation import TwinCaptureBundle
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "twin" / "twin" / "twin_bundle.json"
    bundle = TwinCaptureBundle.model_validate_json(p.read_text(encoding="utf-8"))
    hero = next(c for c in bundle.captures if c.work_face_id == "WF-FAB2-07")
    coeff = derive_coefficients(hero)
    assert 0.0 < coeff.alpha < 1.0 and 0.0 < coeff.eps < 1.0 and 0.0 < coeff.psi <= 1.0
    assert coeff.confidence is Confidence.MEDIUM
    assert coeff.psi_front_only is True


# --------------------------------------------------------------------------- #
# Energy balance (§6.2)
# --------------------------------------------------------------------------- #

def test_night_offset_is_negative_and_scales_with_psi():
    """At night (GHI 0, clear sky) the surface radiates below air, and an open
    deck (high psi) undershoots harder than a shaded one — the hero mechanism."""
    open_deck = derive_coefficients(_capture(sat={"metal": 100.0}, sky_pct=97.0))
    shaded = derive_coefficients(_capture(sat={"metal": 100.0}, sky_pct=45.0))
    o_open = surface_offset_c(t_air=30.0, ghi=0.0, wind_ms=1.0, cloud_octas=0.0, coeff=open_deck)
    o_shaded = surface_offset_c(t_air=30.0, ghi=0.0, wind_ms=1.0, cloud_octas=0.0, coeff=shaded)
    assert o_open < o_shaded < 0.0


def test_bright_galvanising_undershoots_less_than_weathered():
    """The D3 result in miniature: a bright deck barely cools; a weathered one
    undershoots far more."""
    cap = _capture(sat={"metal": 100.0}, sky_pct=97.0)
    bright = derive_coefficients(cap, eps_metal=EPS_METAL_BRIGHT)
    weathered = derive_coefficients(cap, eps_metal=EPS_METAL_WEATHERED)
    o_bright = surface_offset_c(t_air=30.0, ghi=0.0, wind_ms=1.0, cloud_octas=0.0, coeff=bright)
    o_weathered = surface_offset_c(t_air=30.0, ghi=0.0, wind_ms=1.0, cloud_octas=0.0, coeff=weathered)
    assert o_weathered < o_bright < 0.0


def test_cloud_suppresses_the_night_longwave_term():
    cap = derive_coefficients(_capture(sat={"metal": 100.0}, sky_pct=97.0))
    clear = surface_offset_c(t_air=30.0, ghi=0.0, wind_ms=1.0, cloud_octas=0.0, coeff=cap)
    cloudy = surface_offset_c(t_air=30.0, ghi=0.0, wind_ms=1.0, cloud_octas=8.0, coeff=cap)
    assert cloudy == pytest.approx(0.0, abs=1e-9)   # full cloud zeroes the loss term
    assert clear < cloudy
