from dreambuilt import checks
from dreambuilt.samples import ashbury


def test_ashbury_has_no_failures():
    s = checks.summary(checks.run(ashbury()))
    assert s["fail"] == 0 and s["pass"] >= 4


def test_small_bedroom_fails():
    h = ashbury()
    bed = next(r for r in h.levels[0].rooms if r.name == "Bedroom 3")
    bed.w = 6
    rules = {(f.rule, f.status) for f in checks.run(h)}
    assert ("R304 room size", "fail") in rules


def test_no_egress_window_fails():
    h = ashbury()
    h.levels[0].openings = [o for o in h.levels[0].openings if not (o.face == "N" and o.start == 24.0)]
    found = [f for f in checks.run(h) if f.where == "Bedroom 3" and f.rule.startswith("R310")]
    assert found and found[0].status == "fail"
