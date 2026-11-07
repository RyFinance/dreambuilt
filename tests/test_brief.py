from dreambuilt.brief import from_dict, parse_text


def test_parse_sentence():
    b = parse_text("3 story foursquare, 4 bed 3.5 bath, about 2,900 sq ft, 50 by 120 lot, "
                   "big porch and a mudroom")
    assert (b.style, b.stories, b.beds, b.baths, b.sqft) == ("foursquare", 3, 4, 3.5, 2900)
    assert (b.lot_width, b.lot_depth) == (50, 120)
    assert {"porch", "mudroom"} <= set(b.must_haves)


def test_word_numbers_and_aliases():
    b = parse_text("two-story colonial with three bedrooms two baths 2200 sf 70x140 and an office")
    assert (b.style, b.stories, b.beds, b.baths) == ("colonial", 2, 3, 2.0)
    assert "office" in b.must_haves
    assert parse_text("mid century ranch 3br 2ba 1800 square feet").style == "midcentury"


def test_from_yaml_dict():
    b = from_dict({"style": "Craftsman", "stories": 1, "beds": 3, "baths": 2, "sqft": 1600,
                   "lot": "60' x 130'", "must_haves": ["Front porch", "fire place hearth"]})
    assert b.style == "craftsman" and b.lot_depth == 130
    assert b.must_haves == ["porch", "fireplace"]
