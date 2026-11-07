"""The rule reader: sizes, lots, features and pasted prompts."""
from dreambuilt.brief import parse_text, stated_fields


def test_k_sizes_and_lot_area():
    b = parse_text("big 3 story 10k lot 3k house basement only theatre room")
    assert b.sqft == 3000
    assert 60 <= b.lot_width <= 75 and b.lot_width * b.lot_depth > 9000
    assert b.basement and b.suites == []  # a basement, but nobody asked for a rental suite
    assert "theatre" in b.features


def test_room_sizes_are_not_a_lot():
    b = parse_text("two storey 3 bed, living room 18' x 20', kitchen 14 x 16")
    assert (b.lot_width, b.lot_depth) == (60.0, 130.0)  # default, not 18 x 20
    assert "lot_width" not in stated_fields("living room 18' x 20'")


def test_sq_ft_lot_is_the_lot_not_the_house():
    b = parse_text("modern 4 bed 3.5 bath 3800 sq ft on a 7,000 sq ft lot")
    assert b.sqft == 3800 and b.lot_width * b.lot_depth > 6000


def test_markdown_prompt_and_style_words():
    b = parse_text("# Two-Storey Modern Luxury House\n- **Large black-framed windows**\n- stone and wood")
    assert b.style == "modern" and b.stories == 2 and b.sqft >= 4000
    assert {"big windows", "stone", "wood"} <= set(b.features)


def test_westcoast_still_wins_over_modern():
    assert parse_text("surrey modern house 5 bed").style == "westcoast"
    assert parse_text("mid-century modern ranch").style == "midcentury"


def test_no_garage():
    b = parse_text("craftsman 3 bed, no garage, porch")
    assert "no garage" in b.features and "garage" not in b.must_haves


def test_long_structured_brief():
    from pathlib import Path
    t = (Path(__file__).parent / "data" / "townhouse_brief.txt").read_text()
    b = parse_text(t)
    assert (b.lot_width, b.lot_depth) == (18.0, 20.0)
    assert b.stories == 2 and b.beds == 2 and b.baths == 2.0
    assert not b.basement and b.garage == "none"
    assert b.style == "modern"
    assert {"townhouse", "strict lot", "roof terrace", "open plan", "wood", "big windows"} <= set(b.features)
    assert "stone" not in b.features  # stone countertops are inside
    assert any("oak" in w.lower() for w in b.wishes) and len(b.wishes) >= 15


def test_garage_primary_ceiling_fields():
    b = parse_text("craftsman 2 storey 4 bed 3 bath 2800 sq ft 60x130, side garage 3 car, "
                   "master on the main floor, 10 ft ceilings, kitchen facing the backyard")
    assert (b.garage, b.cars, b.primary_floor, b.ceiling) == ("side", 3, "main", 10.0)
    assert "kitchen:rear" in b.places  # a placement ask is now a checkable requirement


def test_casual_prompts():
    b = parse_text("I want a colonial, four bedrooms, three and a half baths, around 3000 square feet")
    assert (b.beds, b.baths, b.sqft) == (4, 3.5, 3000) and not b.notes
    b = parse_text("bungalow w/ basement suite (2 bed) and a triple garage")
    assert b.suites == [2] and b.beds == 3 and b.cars == 3 and b.stories == 1
    b = parse_text("4br/3.5ba craftsman, 2800 sqft, 40 by 120 lot, double garage")
    assert b.cars == 2 and (b.lot_width, b.lot_depth) == (40, 120)
    b = parse_text("family home with ensuites in every bedroom and walk in closets, 4 bed")
    assert b.baths == 4.5 and not b.notes
    b = parse_text("lil 2 bed crib for me n my girl, nothing crazy")
    assert b.sqft <= 1300 and not b.notes


def test_small_basement():
    b = parse_text("craftsman 2 storey 4 bed 3 bath 3400 sq ft small basement 600 sqft")
    assert b.sqft == 3400 and b.basement and b.basement_sqft == 600


def test_new_styles_and_size_words():
    assert parse_text("modern farmhouse 4 bed").style == "farmhouse"
    assert parse_text("spanish villa 3 bed").style == "mediterranean"
    assert parse_text("tudor cottage").style == "tudor"
    assert parse_text("scandi cabin 2 bed").style == "scandinavian"
    b = parse_text("craftsman 4 bed 2800 sq ft, big kitchen, small office, huge primary suite, big garage")
    assert b.sizes["kitchen"] > 1 and b.sizes["office"] < 1 and b.sizes["primary"] > 1 and b.cars == 3


def test_negation_scope():
    b = parse_text("Surrey two-storey, 5 bed 3.5 bath, 4,800 sq ft, 66 x 140 lot, fireplace open floor plan no walls office room")
    assert "office" in b.must_haves
    assert parse_text("without a garage").garage == "none"
    assert "porch" not in parse_text("not a big fan of porches but want a fireplace").must_haves
    assert not parse_text("i don't want a basement, 3 bed").basement
