"""Day-4.5 acceptance — the synthetic thermal twin and the deterministic builders.

The thermal bundle is the input the real ribbon is built from. These assert it
validates, covers every work face over the 72 h window, reproduces the hero
sky-view contrast, and — the reproducibility rule — that both builders emit
identical bytes on a second run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.schemas.thermal_series import ThermalSeriesBundle
from scripts import make_ribbon_fixture, make_thermal_fixtures

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"


@pytest.fixture(scope="module")
def bundle() -> ThermalSeriesBundle:
    return ThermalSeriesBundle.model_validate_json(
        (FIXTURES / "sample_thermal_bundle.json").read_text(encoding="utf-8"))


def test_bundle_validates_all_faces_72_hours(bundle: ThermalSeriesBundle) -> None:
    assert len(bundle.series) == 40                       # all work faces (>= the 21 touched)
    assert bundle.tier.value == "commit" and bundle.replay is True
    for s in bundle.series:
        assert s.source.value == "fixture"
        assert len(s.points) == 72
        assert all(p.wind_ms is not None for p in s.points)   # wind on every point (else Menzel NO_DATA)


def test_air_curve_is_unchanged(bundle: ThermalSeriesBundle) -> None:
    wf11 = next(s for s in bundle.series if s.work_face_id == "WF-FAB2-11")
    p05 = next(p for p in wf11.points if p.ts.hour == 5 and p.ts.day == 24)
    p15 = next(p for p in wf11.points if p.ts.hour == 15 and p.ts.day == 24)
    assert p05.t_air_c == pytest.approx(29.0)
    assert p15.t_air_c == pytest.approx(42.0)


def test_hero_pair_surface_temperatures_diverge(bundle: ThermalSeriesBundle) -> None:
    """The bare open deck (psi 0.97) radiates to a clear sky and cools far below the
    shaded deck (psi 0.45) by dawn — the whole hero rests on this, and it must come
    out of the physics without being told to."""
    bare = next(s for s in bundle.series if s.work_face_id == "WF-FAB2-07")     # psi 0.97
    shaded = next(s for s in bundle.series if s.work_face_id == "WF-FAB2-06")   # psi 0.45

    def dawn_undershoot(s):   # coldest (surface - air) across the pre-dawn hours
        return min(p.t_surf_c - p.t_air_c for p in s.points if p.ts.hour in (2, 3, 4, 5))

    bare_u, shaded_u = dawn_undershoot(bare), dawn_undershoot(shaded)
    assert bare_u < shaded_u - 2.0, (bare_u, shaded_u)      # a real, several-degree gap
    assert bare_u < 0                                      # the open deck drops below air


def test_thermal_builder_is_byte_reproducible() -> None:
    a = make_thermal_fixtures.build_bundle().model_dump_json(indent=2)
    b = make_thermal_fixtures.build_bundle().model_dump_json(indent=2)
    assert a == b


def test_ribbon_builder_is_byte_reproducible() -> None:
    a = make_ribbon_fixture.build_bundle().model_dump_json(indent=2)
    b = make_ribbon_fixture.build_bundle().model_dump_json(indent=2)
    assert a == b
