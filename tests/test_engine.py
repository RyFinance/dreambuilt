"""The procedural design engine: seeded candidates that really differ, new building shapes,
style that comes from words (not places), one model behind every drawing, tiered rules."""
import itertools
import xml.etree.ElementTree as ET

import pytest

from dreambuilt import checks, render_svgs
from dreambuilt.brief import parse_text
from dreambuilt.design import build, options
from dreambuilt.design.signature import distance, signature
from dreambuilt.views.scene import build_scene, place_opening

BRIEFS = ["4 bed 3 bath 2800 sqft 2 storey 60x130 with garage",
          "colonial 4 bed 2.5 bath 2600 sqft 70x140",
          "craftsman 3 bed 2.5 bath 2200 sqft 2 storey 50x120",
          "tudor 3 bed 2.5 bath 2400 sqft 2 storey 60x120 garage"]


@pytest.mark.parametrize("text", BRIEFS)
def test_candidates_are_genuinely_different(text):
    opts = options(parse_text(text), 3)
    assert len(opts) >= 2
    sigs = [signature(o.house) for o in opts]
    for a, b in itertools.combinations(sigs, 2):
        assert distance(a, b) >= 0.08  # not a mirror or a resize of the same plan
    for o in opts:
        assert not checks.blocking(checks.run(o.house))


def test_same_seed_same_designs_new_seed_new_lead():
    b = parse_text(BRIEFS[0])
    a1 = [signature(o.house) for o in options(b, 3, seed=0)]
    a2 = [signature(o.house) for o in options(b, 3, seed=0)]
    assert a1 == a2  # reproducible
    leads = {signature(options(b, 1, seed=s)[0].house) for s in range(3)}
    assert len(leads) >= 2  # asking again doesn't always give the same house first


def test_a_place_is_not_a_style():
    assert parse_text("big family house in surrey 5 bed 4.5 bath").style != "westcoast"
    assert parse_text("a craftsman in burnaby").style == "craftsman"
    assert parse_text("surrey style home 5 bed").style == "westcoast"
    assert parse_text("Surrey two-storey, 4 bed").style == "westcoast"


@pytest.mark.parametrize("text,kind", [
    ("craftsman 3 bed 2 bath 1800 sqft bungalow 80x130", "ell"),
    ("craftsman 3 bed 2 bath 1600 sqft bungalow 70x120", "ell-side"),
    ("mediterranean 4 bed 3 bath 2800 sqft one storey 100x150 3 car garage", "courtyard"),
])
def test_wing_houses(text, kind):
    h = build(parse_text(text), False, False, genome={"plan1": kind})
    found = checks.run(h)
    assert not [f for f in found if f.status == "fail"], [(f.rule, f.where) for f in found if f.status == "fail"]
    x0, y0, x1, y1 = h.levels[0].footprint.bounds
    assert h.levels[0].footprint.area < 0.9 * (x1 - x0) * (y1 - y0)  # an L or a U, not a box
    assert len([m for m in h.roofs if not m.name.startswith(("Porch", "Dormer"))]) >= 2  # a roof per wing


@pytest.mark.parametrize("text", [BRIEFS[1], "modern 4 bed 3.5 bath 3400 sqft 2 storey 70x140 2 car garage",
                                  "3 storey modern townhouse 3 bed 2.5 bath 20x80 with a garage"])
def test_plans_and_elevations_share_one_model(text):
    h = options(parse_text(text), 1)[0].house
    assert not [f for f in checks.run(h) if f.rule.startswith("G") and f.status == "fail"]
    # every window in the plans sits on a real wall, and the elevations draw exactly those windows
    windows = [o for lv in h.all_levels for o in lv.openings if o.kind == "window"]
    assert all(place_opening(lv, o) for lv in h.all_levels for o in lv.openings if o.kind == "window")
    faces, _roof = build_scene(h)
    assert sum(f.role == "window" for f in faces) >= len(windows)


def test_svgs_are_valid(tmp_path):
    h = options(parse_text(BRIEFS[2]), 1)[0].house
    paths = render_svgs(h, tmp_path)
    assert len(paths) >= 8
    for p in paths:
        root = ET.parse(p).getroot()
        assert root.tag.endswith("svg") and root.get("viewBox")


def test_styles_differ_beyond_cladding():
    def street_windows(style):
        h = options(parse_text(f"{style} 3 bed 2 bath 1900 sqft one storey 80x130"), 1)[0].house
        return {(o.width, o.height) for o in h.levels[0].openings if o.kind == "window" and o.face == "S"
                and o.height >= 3.5}
    assert street_windows("colonial") != street_windows("japanese")
    assert parse_text("japandi 3 bed one storey").style == "japanese"


def test_rule_tiers():
    h = options(parse_text(BRIEFS[2]), 1)[0].house
    found = checks.run(h)
    tiers = {f.tier for f in found}
    assert {"hard", "code"} <= tiers
    assert all(f.tier == "code" for f in found if f.rule.startswith("R") and f.status != "warn")
    assert all(f.tier == "advisory" for f in found if f.status == "warn")
    assert checks.tier_of("P8 proportions") == "preference"
    assert checks.tier_of("G2 openings on walls") == "hard"
