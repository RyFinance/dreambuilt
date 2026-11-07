"""The glue around the local model: everything here runs without it."""
from dreambuilt import brief as briefs
from dreambuilt.llm import removed_wishes


def test_describe_round_trips_through_the_parser():
    b = briefs.from_fields({"style": "westcoast", "stories": 2, "beds": 5, "baths": 4.5, "sqft": 5000,
                            "lot": "50x120", "basement": True, "suites": [2, 1],
                            "must_haves": ["garage", "spice kitchen", "fireplace"]})
    again = briefs.parse_text(briefs.describe(b))
    for f in ("style", "stories", "beds", "baths", "sqft", "lot_width", "lot_depth", "basement", "suites"):
        assert getattr(again, f) == getattr(b, f), f
    assert set(again.must_haves) == set(b.must_haves)


def test_model_answers_are_clamped():
    b = briefs.from_fields({"style": "Spanish castle", "stories": 9, "beds": "40", "baths": 2.3,
                            "sqft": "1,000,000", "lot": "huge", "must_haves": ["moat", "porch"],
                            "suites": ["two", 2, 9]})
    assert b.stories == 3 and b.beds == 7 and b.baths == 2.5 and b.sqft == 8000
    assert b.must_haves == ["porch"] and b.suites == [2]


def test_make_sane_fixes_impossible_combinations():
    b = briefs.DesignBrief("westcoast", 1, 5, 6, 900, 50, 120, [], basement=True, suites=[2])
    briefs.make_sane(b)
    # a bungalow keeps its single storey over the basement
    assert b.sqft >= 380 + 150 * 5 + 45 * b.baths and b.baths <= 6.5 and b.stories == 1


def test_stated_fields_ignore_suite_bedrooms():
    said = briefs.stated_fields("add a 1 bed rental suite in the basement")
    assert "beds" not in said
    assert {"beds", "lot_width"} <= briefs.stated_fields("4 bed on a 50 foot lot")


def test_thin_briefs_are_spotted():
    assert briefs.is_thin("big house in surrey")
    assert not briefs.is_thin("Craftsman two-storey, 4 bed 3 bath, 2,600 sq ft, 50 x 120 lot")


def test_removals():
    assert removed_wishes("swap the fireplace for an office") == {"fireplace"}
    assert removed_wishes("no porch, and drop the mudroom") == {"porch", "mudroom"}
    assert removed_wishes("add a porch") == set()


def test_change_without_model_uses_rules(monkeypatch):
    from dreambuilt import llm
    monkeypatch.setattr(llm, "revise", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no model")))
    base = briefs.parse_text("Surrey two-storey, 4 bed 3.5 bath, 3,800 sq ft, 66 x 140 lot, fireplace")
    out = llm.revise_brief(base, "make it 5 bed, add a 1 bed rental suite, drop the fireplace")
    assert out.beds == 5 and out.suites == [1] and out.basement and "fireplace" not in out.must_haves


def test_history_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAMBUILT_HISTORY", str(tmp_path))
    from dreambuilt.app import history
    from dreambuilt.design import Option
    from dreambuilt.samples import ashbury
    opts = [Option(ashbury(), 0, [])]
    v1 = history.save("craftsman bungalow", opts, brief=briefs.parse_text("craftsman 3 bed"))
    v2 = history.save("craftsman bungalow\n→ add a porch", opts, parent=v1)
    v3 = history.save("craftsman bungalow\n→ 4 bed", opts, parent=v2)
    groups = history.grouped()
    assert len(groups) == 1 and groups[0][0].id == v1.id
    assert [e.version for e in groups[0][1]] == [3, 2] and v3.family == v1.id
    first = next(e for e in history.all_entries() if e.id == v1.id)  # saved in the same second
    assert first.load_brief().beds == 3
