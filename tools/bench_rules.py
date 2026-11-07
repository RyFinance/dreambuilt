"""Benchmark the ways of turning client words into custom rules.

    .venv/bin/python tools/bench_rules.py [MODEL ...]

Methods: regex (the phrase library), fuzzy (nearest example phrasing), llm-free (the model
writes rules), llm-menu (the model picks numbers from a menu), and the pipeline the app uses.
Scores are precision / recall / exact-match over labelled phrases, plus seconds per phrase.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dreambuilt import custom_rules as cr, llm  # noqa: E402

CASES = [
    ("ensuite bathrooms only", ["ensuite_each"]),
    ("I want every bedroom to have its own bathroom", ["ensuite_each"]),
    ("each kid gets a private bath attached to their room", ["ensuite_each"]),
    ("no shared bathrooms for the kids please", ["ensuite_each"]),
    ("grand middle entrance", ["entry:center"]),
    ("put the front door right in the centre of the house", ["entry:center"]),
    ("the entry should be off to the left side", ["entry:left"]),
    ("open floor plan", ["open:on"]),
    ("I hate walls between the kitchen and the living room, make it one big space", ["open:on"]),
    ("we like separate rooms, not an open concept", ["open:off"]),
    ("bathrooms should never be lined up next to each other", ["no_bath_row"]),
    ("no parallel bathrooms", ["no_bath_row"]),
    ("my office has to be upstairs away from the noise", ["floor:office:upper"]),
    ("study downstairs by the front door", ["floor:office:main"]),
    ("washer and dryer on the bedroom floor", ["floor:laundry:upper"]),
    ("master bedroom on the ground level, my knees are bad", ["floor:primary:main"]),
    ("kitchen looking out to the backyard", ["side:kitchen:rear"]),
    ("living room facing the garden", ["side:living:rear"]),
    ("laundry right next to the master", ["near:laundry:primary"]),
    ("mudroom that opens into the kitchen", ["near:mudroom:kitchen"]),
    ("a walk-in pantry off the kitchen", ["near:pantry:kitchen"]),
    ("we don't want a basement", ["exclude:basement"]),
    ("skip the fireplace", ["exclude:fireplace"]),
    ("open plan living and every bedroom with its own ensuite", ["open:on", "ensuite_each"]),
    ("front door in the middle and no bathrooms side by side", ["entry:center", "no_bath_row"]),
    # nothing to make a rule from
    ("warm oak floors and black window frames", []),
    ("for me and my partner and our two dogs", []),
    ("something that feels calm", []),
    ("nice big windows in the living room", []),
    ("budget is tight", []),
]


# written after the tuning above, never used to tune: an honest check
HOLDOUT = [
    ("every one of the bedrooms needs an attached bathroom", ["ensuite_each"]),
    ("kids each get their own ensuite", ["ensuite_each"]),
    ("main door centred on the facade", ["entry:center"]),
    ("entrance on the right hand side", ["entry:right"]),
    ("kitchen, dining and living all in one open space", ["open:on"]),
    ("I prefer a formal layout with separate rooms", ["open:off"]),
    ("don't put two bathrooms back to back", ["no_bath_row"]),
    ("home office on the second floor", ["floor:office:upper"]),
    ("laundry room upstairs near the bedrooms", ["floor:laundry:upper"]),
    ("primary suite on the main floor", ["floor:primary:main"]),
    ("kitchen at the rear overlooking the yard", ["side:kitchen:rear"]),
    ("no garage, we'll park on the street", ["exclude:garage"]),
    ("a lovely porch swing out front", []),
    ("lots of storage everywhere", []),
    ("make it feel modern and bright", []),
]


def score(method, cases=None) -> dict:
    tp = fp = fn = exact = 0
    secs = []
    misses = []
    cases = cases or CASES
    for text, want in cases:
        t = time.time()
        try:
            got = method(text)
        except Exception as e:  # a method that crashes scores nothing
            got = []
            misses.append((text, f"error {e!r}"[:60]))
        secs.append(time.time() - t)
        g, w = set(got), set(want)
        tp += len(g & w)
        fp += len(g - w)
        fn += len(w - g)
        exact += g == w
        if g != w:
            misses.append((text[:45], sorted(g), sorted(w)))
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"precision": round(p, 2), "recall": round(r, 2), "exact": f"{exact}/{len(cases)}",
            "sec": round(sum(secs) / len(secs), 2), "misses": misses}


def regex(text):
    return cr.read(text.lower())[0]


def fuzzy(text):
    return cr.fuzzy(text)


def pipeline(path):
    """What the app does: the phrase library first; the model only when it finds nothing."""
    def run(text):
        got = regex(text)
        return got if got else llm.rules_menu(text, path)
    return run


def combo_rf(text):
    """The phrase library and the nearest example together."""
    return sorted(set(regex(text)) | set(fuzzy(text)))


def app_pipeline(path):
    """Exactly what the app runs: phrase library, then per clause examples, then the model."""
    def run(text):
        got = set(cr.read(text.lower())[0])
        for _c, rules, _how in cr.read_clauses(text, propose=lambda c: llm.rules_menu(c, path)):
            got |= set(rules)
        return sorted(got)
    return run


def verified(path, low=0.42):
    """Phrase library + nearest example, plus the model's menu picks that fuzzy agrees with
    at least loosely (the model proposes, the examples confirm)."""
    def run(text):
        got = set(regex(text)) | set(fuzzy(text))
        sc = cr.fuzzy_scores(text)
        for r in llm.rules_menu(text, path):
            if sc.get(r, 0) >= low and cr.plausible(r, text):
                got.add(r)
        return sorted(got)
    return run


if __name__ == "__main__":
    models = [a for a in sys.argv[1:] if not a.startswith("--")] or [llm.DEFAULT_MODEL]
    out = {"regex": score(regex), "fuzzy": score(fuzzy), "regex+fuzzy": score(combo_rf),
           "HOLDOUT regex+fuzzy": score(combo_rf, HOLDOUT)}
    for m in models:
        name = Path(m).name
        llm._load.cache_clear()
        if "--quick" not in sys.argv:
            out[f"llm-free/{name}"] = score(lambda t, m=m: llm.rules_free(t, m))
            out[f"llm-menu/{name}"] = score(lambda t, m=m: llm.rules_menu(t, m))
            out[f"pipeline/{name}"] = score(pipeline(m))
        out[f"verified/{name}"] = score(verified(m))
        out[f"HOLDOUT verified/{name}"] = score(verified(m), HOLDOUT)
        out[f"app/{name}"] = score(app_pipeline(m))
        out[f"HOLDOUT app/{name}"] = score(app_pipeline(m), HOLDOUT)
        out[f"HOLDOUT llm-menu/{name}"] = score(lambda t, m=m: llm.rules_menu(t, m), HOLDOUT)
    for k, v in out.items():
        print(f"{k:34s} precision {v['precision']:.2f}  recall {v['recall']:.2f}  exact {v['exact']:>6}  {v['sec']}s")
    Path(sys.argv[0]).with_suffix(".last.json").write_text(json.dumps(out, indent=1))
