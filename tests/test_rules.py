"""Custom rules: words -> rules in a small language -> generators that obey them -> checks
that say whether each was kept. Plus the phrase library that learns."""
import pytest

from dreambuilt import checks, custom_rules as cr
from dreambuilt.brief import describe, parse_text
from dreambuilt.design import options

USER = "ensuite bathrooms only open floor plan grand middle entrance"


def test_validate_keeps_only_the_language():
    assert cr.validate("entry:middle") == "entry:center"
    assert cr.validate("floor:office:upper") == "floor:office:upper"
    assert cr.validate("scale:kitchen:1.3") == "scale:kitchen:1.3"
    for bad in ["entry:roof", "floor:attic:upper", "scale:kitchen:9", "build_a_pool", "", None, 3]:
        assert cr.validate(bad) is None


def test_the_users_message_becomes_rules():
    b = parse_text(USER)
    assert {"ensuite_each", "entry:center", "open:on"} <= set(b.rules)
    assert not b.notes  # nothing left as "not understood"
    assert b.sqft < 4000  # "grand entrance" is not a size word


def test_rules_survive_the_written_brief():
    b = parse_text("craftsman 4 bed 2 storey 3200 sqft 60x130 " + USER)
    again = parse_text(describe(b))
    assert set(b.rules) <= set(again.rules)


def test_direction_words_guard_the_examples():
    assert cr.fuzzy("study downstairs by the front door") != ["floor:office:upper"]
    assert "open:off" not in cr.read("i hate walls between the kitchen and living, one big space")[0] + \
        cr.fuzzy("i hate walls between the kitchen and living, one big space")
    assert cr.read("we like separate rooms, not an open concept")[0] == ["open:off"]


@pytest.mark.parametrize("text", [
    "craftsman 4 bed 2 storey 3200 sqft 60x130 " + USER,
    "mediterranean 5 bed 2 storey 6000 sqft 80x160 " + USER,
    "craftsman 3 bed bungalow 1800 sqft 80x130 ensuite bathrooms only, open floor plan",
])
def test_generators_keep_the_rules(text):
    b = parse_text(text)
    h = options(b, 1)[0].house
    for rule in b.rules:
        kept, why = cr.check(h, rule)
        assert kept, (rule, why)
    assert not [f for f in checks.run(h) if f.status == "fail"]
    assert any(n.startswith("Custom rule kept") for n in h.notes)


def test_no_bathroom_rows_by_default():
    # (five bedrooms with three shared baths on one floor can't avoid it without ensuites:
    # a known limit; asking for ensuite bathrooms solves it)
    for text in ["craftsman 4 bed 3.5 bath 3200 sqft 2 storey 70x130",
                 "tudor 4 bed 3 bath 2800 sqft 2 storey 60x130 with garage"]:
        h = options(parse_text(text), 1)[0].house
        assert not cr.bath_rows(h)


def test_learned_phrases(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAMBUILT_HISTORY", str(tmp_path))
    assert cr.read("the bedrooms all get a little spa")[0] == []
    cr.learn("the bedrooms all get a little spa", ["ensuite_each", "nonsense:rule"])
    assert cr.learned() == {"the bedrooms all get a little spa": ["ensuite_each"]}
    assert cr.read("i want the bedrooms all get a little spa please")[0] == ["ensuite_each"]
    cr.forget("the bedrooms all get a little spa")
    assert cr.learned() == {}


def test_a_rule_that_cannot_be_kept_is_reported():
    b = parse_text("colonial 3 bed bungalow 1500 sqft 70x120 front door on the left")
    h = options(b, 1)[0].house
    kept, _ = cr.check(h, "entry:left")
    note = [n for n in h.notes if "front entrance on the left" in n]
    assert note and (("NOT kept" in note[0]) != kept)
