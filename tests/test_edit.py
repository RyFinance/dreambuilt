"""Editing a finished design: fixed titles, edits that keep the same house, dragged walls,
drawings read as edits, breeding and taste."""
import copy
import math

import pytest

from dreambuilt import checks, edit
from dreambuilt.brief import parse_text
from dreambuilt.design import candidates, offspring, options
from dreambuilt.design.signature import novelty, signature

BRIEF = "craftsman 4 bed 3 bath 2800 sqft 2 storey 60x130 with garage"


@pytest.fixture(scope="module")
def design():
    b = parse_text(BRIEF)
    return b, options(b, 3)


def unchanged(a, b):
    return sum(1 for la, lb in zip(a.all_levels, b.all_levels) for x in la.rooms for y in lb.rooms
               if x.label == y.label and abs(x.x - y.x) < .1 and abs(x.y - y.y) < .1
               and abs(x.w - y.w) < .1 and abs(x.h - y.h) < .1)


def test_every_room_has_a_unique_title(design):
    _b, opts = design
    for o in opts:
        t = edit.titles(o.house)
        assert len(t) == len(set(t))
        assert o.house.genome  # the decisions an edit keeps


def test_words_become_ops(design):
    _b, opts = design
    h = opts[0].house
    said = lambda text: [o.describe() for o in edit.parse(text, h)]
    assert said("make Bedroom 3 bigger") == ["Bedroom 3 bigger"]
    assert said("Bedroom 2 20% smaller and keep the Kitchen") == ["Bedroom 2 smaller", "keep Kitchen"]
    assert said("move the kitchen to the front") == ["Kitchen to the front"]
    assert said("remove Bedroom 4, add an office") == ["remove Bedroom 4", "add office"]
    assert said("swap Bedroom 2 and Bedroom 3") == ["swap Bedroom 2 and Bedroom 3"]
    assert said("I like warm floors") == []


@pytest.mark.parametrize("text", ["make Bedroom 3 bigger", "make the kitchen bigger", "swap Bedroom 2 and Bedroom 3"])
def test_an_edit_keeps_the_house(design, text):
    b, opts = design
    h = opts[0].house
    res = edit.apply(h, b, edit.parse(text, h))
    assert res.done and not res.couldnt
    total = sum(len(lv.rooms) for lv in h.all_levels)
    assert unchanged(h, res.house) >= total * 0.75  # the same design with one thing changed
    assert not [f for f in checks.run(res.house) if f.status == "fail"]


def test_bigger_means_bigger(design):
    b, opts = design
    h = opts[0].house
    # (a kitchen: a bedroom grown past the primary would trade names with it, by the
    # primary-is-biggest rule)
    res = edit.apply(h, b, edit.parse("make the kitchen bigger", h))
    before = next(r for lv in h.all_levels for r in lv.rooms if r.label == "Kitchen")
    after = next(r for lv in res.house.all_levels for r in lv.rooms if r.label == "Kitchen")
    assert after.area > before.area * 1.08


def test_dragging_a_wall(design):
    _b, opts = design
    h = copy.deepcopy(opts[0].house)
    li = len(h.all_levels) - 1
    # the first long wall that can move a foot (some sit against a minimum-size closet)
    for axis, line, lo, hi in [w for w in edit.walls(h, li) if w[0] == "y" and w[3] - w[2] > 8]:
        if edit.move_wall(h, li, axis, line, lo, hi, line + 1.0) == "":
            break
    else:
        raise AssertionError("no wall could move")
    assert not [f for f in checks.run(h) if f.rule.startswith("G") and f.status == "fail"]  # model still agrees
    assert edit.move_wall(copy.deepcopy(opts[0].house), li, axis, line, lo, hi, line + 12) != ""  # refused


def test_drawing_on_the_plan(design):
    _b, opts = design
    h = opts[0].house
    li = len(h.all_levels) - 1
    lv = h.all_levels[li]
    b3 = next(r for r in lv.rooms if r.label == "Bedroom 3")
    b4 = next(r for r in lv.rooms if r.label == "Bedroom 4")
    cx, cy = b3.x + b3.w / 2, b3.y + b3.h / 2
    loop = [(cx + 3 * math.cos(t / 10 * 6.28), cy + 3 * math.sin(t / 10 * 6.28)) for t in range(11)]
    swap = [(b3.x + 2, b3.y + 3), (b4.x + 3, b4.y + 4)]
    x1 = [(b4.x + 2, b4.y + 2), (b4.x + 6, b4.y + 6)]
    x2 = [(b4.x + 6, b4.y + 2), (b4.x + 2, b4.y + 6)]
    ops, selected = edit.strokes(h, li, [loop, swap, x1, x2])
    assert selected == ["Bedroom 3"]
    kinds = sorted(o.describe() for o in ops)
    assert kinds == ["remove Bedroom 4", "swap Bedroom 3 and Bedroom 4"]


def test_breeding_makes_new_designs(design):
    b, opts = design
    kids = offspring(b, opts[0].house, opts[1].house, 3)
    assert kids
    parents = [signature(opts[0].house), signature(opts[1].house)]
    for k in kids:
        assert novelty(signature(k.house), parents) >= 0.04
        assert not checks.blocking(checks.run(k.house))


def test_taste_learns(tmp_path, monkeypatch, design):
    monkeypatch.setenv("DREAMBUILT_HISTORY", str(tmp_path))
    _b, opts = design
    liked, passed = signature(opts[1].house), signature(opts[0].house)
    candidates.react(liked, True)
    candidates.react(passed, False)
    assert candidates.taste_score(liked) > 0 > candidates.taste_score(passed)
