"""
WORKFACE — write the climatology-prior fixture.  T3, Day 5.

    python -m scripts.make_priors_fixture            # writes data/fixtures/climatology_priors.json
    python -m scripts.make_priors_fixture --check    # + validate + print the demo sentences

The maths lives in apps/api/climatology/priors.py; this only serialises it to a
committed fixture (the climatology_prior shape of 001_init.sql, plus the two
mandated provenance fields coverage / hour_of_day_source) and emits the per-face
planner sentences for the slide and the UI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps.api.climatology import formatter as F
from apps.api.climatology.priors import (
    Coverage,
    build_priors,
    face_tile_map,
    summarize_face,
)
from apps.api.windows.registry import load_registry

_REPO_ROOT = Path(__file__).resolve().parents[1]
HERO_FACE = "WF-FAB2-07"


def build_fixture() -> dict:
    reg = load_registry()
    rows = build_priors()
    prior_rows = [
        {**r.to_db_row(),
         "coverage": r.coverage.value,
         "hour_of_day_source": r.hour_of_day_source.value}
        for r in rows
    ]

    # One planner sentence per demo face, for each supported / hero trade.
    sentences: list[dict] = []
    for face_id in sorted(face_tile_map()):
        for trade in ("concrete_cip_hot_weather", "concrete_cip_cold_weather",
                      "sfrm_spray_applied_fireproofing", "coating_epoxy_structural_steel"):
            s = summarize_face(face_id, trade)
            sentences.append({
                "work_face_id": face_id, "tile_id": s.tile_id, "trade_id": trade,
                "coverage": s.coverage.value, "sentence": F.sentence_for(s),
            })

    return {
        "schema_note": "Tier-0 climatology priors — a PROBABILITY, not a forecast. "
                       "median_peak_c is None everywhere (sweep has no temperature "
                       "magnitude); hour_of_day_source names modelled vs observed timing.",
        "registry_version": reg.version,
        "month": 8,
        "n_tiles": len({r.tile_id for r in rows}),
        "n_rows": len(prior_rows),
        "coverage_counts": {
            c.value: sum(1 for r in rows if r.coverage is c) for c in Coverage
        },
        "priors": prior_rows,
        "planner_sentences": sentences,
        "replay": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="WORKFACE climatology-prior fixture (T3, Day 5)")
    ap.add_argument("--out", default="data/fixtures/climatology_priors.json", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    fixture = build_fixture()
    args.out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ok] {args.out}  {fixture['n_rows']} rows across {fixture['n_tiles']} tiles")
    print(f"[ok] coverage: {fixture['coverage_counts']}")

    if args.check:
        hero_hot = summarize_face(HERO_FACE, "concrete_cip_hot_weather")
        print(f"[hero] {HERO_FACE} concrete-hot -> {F.exceedance_sentence(hero_hot)}")
        print(f"[hero] {HERO_FACE} sfrm         -> {F.sentence_for(summarize_face(HERO_FACE, 'sfrm_spray_applied_fireproofing'))}")
        print(f"[hero] {HERO_FACE} coating      -> {F.sentence_for(summarize_face(HERO_FACE, 'coating_epoxy_structural_steel'))}")
        assert fixture["coverage_counts"]["insufficient_threshold"] == fixture["n_tiles"] * 9
        print("[ok] --check assertions passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
