"""Space used properly and briefs obeyed: real rooms over garages, main-floor primaries,
townhouse stacking, basements that hold what was asked, and a tidy exterior."""
from pathlib import Path

import pytest

from dreambuilt import checks
from dreambuilt.brief import parse_text
from dreambuilt.design import design, missing, options
from dreambuilt.roof.analytic import z_range

FILLER = {"Bonus Room", "Sitting Room", "Flex Room", "Bedroom Nook"}
TUDOR = (Path(__file__).parent / "data" / "tudor_brief.txt").read_text()


def fails(h):
    return [f for f in checks.run(h) if f.status == "fail"]


def names(h):
    return [r.name for lv in h.all_levels for r in lv.rooms]


def test_tudor_brief_is_read_whole():
    b = parse_text(TUDOR)
    assert (b.style, b.stories, b.beds, b.baths) == ("tudor", 2, 5, 4.5)
    assert b.suites == []  # "but no rental suite"
    assert b.sqft == 6300  # 4,200 above ground plus the basement
    assert b.primary_floor == "main" and b.cars == 3
    assert {"family room", "office", "mudroom", "fireplace"} <= set(b.must_haves)
    assert {"theatre", "gym", "wine room", "grand entrance"} <= set(b.features)
    assert "black window frames" in b.wishes and "warm lighting in the dining room" in b.wishes
    assert b.sizes["primary_bath"] > 1 and b.sizes["office"] < 1  # spa ensuite, small office
    assert "dining:front" in b.places and "kitchen:rear" in b.places


def test_tudor_brief_draws_everything_it_asked_for():
    b = parse_text(TUDOR)
    h = options(b, 1)[0].house
    assert not fails(h)
    assert not missing(h, b)
    assert not FILLER & set(names(h))
    main = [r.name for r in h.levels[0].rooms]
    assert "Primary Bedroom" in main and "Family Room" in main and "3-Car Garage" in main
    base = {r.name for r in h.basement.rooms}
    assert {"Theatre", "Gym", "Wine Room"} <= base
    # the space over the garage is bedrooms, not a bonus room
    gar = next(r for r in h.levels[0].rooms if r.kind == "garage")
    over = [r for r in h.levels[1].rooms if r.x >= gar.x - 0.1 and r.x + r.w <= gar.x + gar.w + 0.1]
    assert sum(r.kind == "bedroom" for r in over) >= 1


@pytest.mark.parametrize("text", [
    "craftsman 4 bed 3.5 bath 3200 sqft 2 storey 70x130 with a 2 car garage",
    "mediterranean 4 bed 3.5 bath 3400 sqft 2 storey 75x130 3 car garage",
    "craftsman 3 bed 2.5 bath 2400 sqft 2 storey 60x130 with garage",
    "modern farmhouse 4 bed 3 bath 3200 sqft 2 storey 80x140 with a 2 car garage and a big porch",
    "colonial 4 bed 3 bath 3000 sqft 2 storey 60x120 with a big kitchen and an office at the front, primary on main",
])
def test_two_storeys_use_their_space(text):
    b = parse_text(text)
    h = options(b, 1)[0].house
    assert not fails(h), [(f.rule, f.where) for f in fails(h)]
    assert not missing(h, b)
    assert not FILLER & set(names(h))


def test_townhouse_stacks_garage_living_bedrooms():
    b = parse_text("3 storey modern townhouse 3 bed 2.5 bath 20x80 with a garage")
    assert (b.lot_width, b.lot_depth) == (20, 80)
    h = design(b)
    assert not fails(h)
    ground, second, third = ([r.kind for r in lv.rooms] for lv in h.levels)
    assert "garage" in ground and "entry" in ground and "living" not in ground
    assert "living" in second and "kitchen" in second
    assert third.count("bedroom") == 2
    assert any(o.kind == "garage" for o in h.levels[0].openings)


def test_a_bungalow_stays_one_storey():
    h = design(parse_text("modern 4 bed 2 bath 1900 sqft bungalow 55x140 with a garage"))
    assert len(h.levels) == 1


def test_porch_columns_are_even_and_clear_of_the_door():
    for text in ["craftsman 3 bed 2.5 bath 2400 sqft 2 storey 60x130 with a porch",
                 "farmhouse 4 bed 3 bath 3200 sqft 2 storey 80x140 big porch",
                 "colonial 4 bed 2.5 bath 2800 sqft 2 storey 70x140 grand entrance"]:
        h = design(parse_text(text))
        door = next(o for o in h.levels[0].openings if o.kind == "door" and o.face == "S")
        mid = door.start + door.width / 2
        for p in h.porches:
            if p.columns:
                assert len(p.columns) % 2 == 0
                assert all(abs(cx - mid) >= door.width / 2 + 0.5 for cx, _ in p.columns)


def test_gables_meet_the_main_ridge_or_step_down_clearly():
    for text in ["craftsman 3 bed 2.5 bath 2400 sqft 2 storey 60x130 with garage",
                 "tudor 4 bed 3.5 bath 3000 sqft 2 storey 70x130 2 car garage"]:
        h = design(parse_text(text))
        main = next(r for r in h.roofs if r.name == "Main")
        top = z_range(main)[1]
        for r in h.roofs:
            if r.name in ("Garage wing", "Cross gable"):
                hi = z_range(r)[1]
                assert hi <= top + 0.05 and (abs(hi - top) < 0.05 or top - hi >= 2.5)
