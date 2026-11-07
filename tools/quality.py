"""Design-quality benchmark: concrete flaws per house, and a 0-100 score.

    .venv/bin/python tools/quality.py            # tuning + held-out briefs
    .venv/bin/python tools/quality.py --json out.json

A flaw is something an architect would mark on a plan. Each one is counted once per house:

  hard        a hard planning / geometry / code failure
  missing     something the brief asked for that the drawing lacks
  preference  an architectural preference failure (P3, P6, P8, ...)
  bath row    bathrooms in a row (P13), or plumbing that doesn't stack (P11)
  narrow      a habitable room longer than 1.8x its width
  cramped     a bedroom under 10' x 10', a living room under 12' wide, a kitchen under 9'
  circulation halls and landings over 15% of the floor, or a hall longer than 30'
  fragments   closets / linen / storage under 12 sq ft that aren't real storage, beyond 2 a floor
  waste       closets + storage over 14% of the floor
  dark        a habitable room with no window, or a living / family room with only one
  stacking    under 80% of an upper floor's outside walls over walls below (G5)
  primary     the primary suite not clearly the best bedroom (area < 1.15x the next bedroom)
  realism     a room pairing real plans almost never have (from 4,299 CubiCasa plans)

The score is 100 minus weighted flaws (hard and missing weigh most), never below 0.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

TUNING = [
    "craftsman 4 bed 3 bath 2800 sqft 2 storey 60x130 with garage",
    "modern 4 bed 3.5 bath 3400 sqft 2 storey 70x140 2 car garage",
    "colonial 4 bed 2.5 bath 2600 sqft 70x140",
    "tudor 5 bed 4.5 bath 4200 sqft 2 storey 80x140 3 car garage",
    "farmhouse 4 bed 3 bath 3000 sqft 2 storey 80x150",
    "craftsman 3 bed 2.5 bath 2200 sqft 2 storey 50x120",
    "3 bed 2 bath 1600 sqft bungalow 70x120",
    "midcentury 3 bed 2 bath 1900 sqft one storey 80x130 with garage",
    "scandinavian 3 bed 2 bath 1800 sqft one storey 60x120",
    "mediterranean 4 bed 3.5 bath 3400 sqft 2 storey 75x130 3 car garage",
    "Surrey two-storey, 5 bed 4.5 bath, 4,800 sq ft, 66 x 140 lot, fireplace, office, spice kitchen",
    "Surrey 2 storey 5 bed 4.5 bath 5000 sq ft basement theatre gym wet bar 60 x 130",
    "craftsman 4 bed 3.5 bath 3600 sqft 2 storey 65x130 with a basement and garage",
    "3 storey modern townhouse 3 bed 2.5 bath 20x80 with a garage",
    "colonial 2 bed 1 bath 1100 sqft cottage 40x100",
    "craftsman 4 bed 2 storey 3200 sqft 60x130 ensuite bathrooms only, open floor plan, grand middle entrance",
    "farmhouse 4 bed 3 bath 3000 sqft 80x150 primary on main",
    "modern 5 bed 4.5 bath 4200 sqft 2 storey 80x140 3 car garage",
    "foursquare 4 bed 2.5 bath 2600 sqft 2 storey 60x130 fireplace mudroom office",
    "japanese 3 bed 2 bath 2000 sqft one storey 90x130 2 car garage",
    "tudor 3 bed 2.5 bath 2400 sqft 2 storey 60x120 garage",
    "modern 3 storey 4 bed 3.5 bath 3600 sqft 45x120",
    "craftsman 1 storey 3 bed 2 bath 3200 sq ft with basement 60 x 130",
    "colonial 5 bed 3.5 bath 3600 sqft 2 storey 80x140 office pantry",
]
HELDOUT = [  # never looked at while tuning
    "scandinavian 4 bed 3 bath 2900 sqft 2 storey 65x130 with garage and office",
    "mediterranean 3 bed 2.5 bath 2500 sqft 2 storey 60x140 courtyard feel",
    "farmhouse 5 bed 4 bath 3800 sqft 2 storey 90x160 3 car garage mudroom pantry",
    "modern 2 bed 2 bath 1400 sqft one storey 50x110",
    "tudor 4 bed 3.5 bath 3300 sqft 2 storey 70x140 fireplace",
    "colonial 4 bed 3 bath 3100 sqft 2 storey 75x150 basement with a 1 bed rental suite",
    "midcentury 4 bed 2.5 bath 2400 sqft one storey 100x140 with garage",
    "craftsman 3 bed 2 bath 1500 sqft bungalow 50x120 porch",
    "Surrey style 4 bed 3.5 bath 3800 sq ft 66 x 140 lot",
    "japanese 2 bed 2 bath 1600 sqft one storey 70x120",
    "modern 4 bed 4 bath 3200 sqft 2 storey 60x120 every bedroom has its own bathroom",
    "farmhouse 3 bed 2.5 bath 2300 sqft 2 storey 55x130 open floor plan",
    "foursquare 3 storey 5 bed 3.5 bath 3300 sqft 50x120 porch",
    "mediterranean 5 bed 4.5 bath 4600 sqft 2 storey 85x150 3 car garage office",
    "craftsman 2 bed 1.5 bath 1300 sqft 2 storey 35x110",
]

HABITABLE = {"bedroom", "living", "family", "dining", "kitchen", "office"}
WEIGHTS = {"hard": 12, "missing": 10, "preference": 5, "bath row": 4, "narrow": 3, "cramped": 3,
           "circulation": 3, "fragments": 2, "waste": 2, "dark": 3, "stacking": 2, "primary": 3, "realism": 1}


def flaws(h, b) -> dict[str, int]:
    from dreambuilt import checks
    from dreambuilt.design import missing, stats
    from dreambuilt.checks import clear_opening  # noqa: F401
    out = {k: 0 for k in WEIGHTS}
    found = checks.run(h)
    out["hard"] = len(checks.blocking(found))
    out["missing"] = len(missing(h, b))
    out["preference"] = sum(f.status == "fail" and f.tier == "preference" for f in found)
    out["bath row"] = sum(f.rule.startswith("P13") for f in found) + sum(
        f.rule.startswith("P11") and f.status == "warn" for f in found)
    out["stacking"] = sum(f.rule.startswith("G5") for f in found)
    from dreambuilt.checks import _windows_in
    beds = []
    for lv in h.all_levels:
        rooms = [r for r in lv.rooms if r.kind != "void"]
        area = sum(r.area for r in rooms) or 1
        halls = [r for r in rooms if r.kind == "hall"]
        if sum(r.area for r in halls) / area > 0.15 or any(max(r.w, r.h) > 30 for r in halls):
            out["circulation"] += 1
        small = [r for r in rooms if r.kind == "closet" and r.area < 12 and r.name not in ("Coat", "Pantry")]
        out["fragments"] += max(0, len(small) - 2)
        if sum(r.area for r in rooms if r.kind == "closet") / area > 0.14:
            out["waste"] += 1
        for r in rooms:
            lo, hi = sorted((r.w, r.h))
            if r.kind in HABITABLE and not r.unit:
                if hi / max(lo, 0.1) > 1.8:
                    out["narrow"] += 1
                if (r.kind == "bedroom" and lo < 10) or (r.kind in ("living", "family") and lo < 12) or \
                        (r.kind == "kitchen" and lo < 9):
                    out["cramped"] += 1
                if lv is not h.basement:
                    n = len([o for o in _windows_in(lv, r) if o.kind == "window"])
                    if n == 0 or (r.kind in ("living", "family") and n < 2):
                        out["dark"] += 1
            if r.kind == "bedroom" and not r.unit:
                beds.append(r)
    prim = [r for r in beds if r.name.startswith("Primary")]
    others = sorted((r.area for r in beds if not r.name.startswith("Primary")), reverse=True)
    if prim and others and prim[0].area < 1.15 * others[0]:
        out["primary"] = 1
    _pen, why = stats.layout_penalty(h.levels)
    out["realism"] = len(why)
    return out


def score(fl: dict) -> float:
    return max(0.0, 100.0 - sum(WEIGHTS[k] * v for k, v in fl.items()))


def run(briefs: list[str]) -> dict:
    from dreambuilt.brief import parse_text
    from dreambuilt.design import options
    rows = []
    for t in briefs:
        b = parse_text(t)
        try:
            h = options(b, 1)[0].house
        except Exception as e:  # a brief the engine can't draw counts as broken
            rows.append({"brief": t, "error": repr(e)[:120], "flaws": {k: (5 if k == "hard" else 0) for k in WEIGHTS},
                         "total": 5, "score": score({"hard": 5})})
            continue
        fl = flaws(h, b)
        rows.append({"brief": t, "flaws": fl, "total": sum(fl.values()), "score": score(fl)})
    return {"rows": rows,
            "flaws_per_house": round(statistics.mean(r["total"] for r in rows), 2),
            "score": round(statistics.mean(r["score"] for r in rows), 1),
            "by_kind": {k: sum(r["flaws"].get(k, 0) for r in rows) for k in WEIGHTS}}


if __name__ == "__main__":
    t0 = time.time()
    out = {"tuning": run(TUNING), "heldout": run(HELDOUT)}
    for name in ("tuning", "heldout"):
        r = out[name]
        print(f"{name:8s} flaws/house {r['flaws_per_house']:5.2f}   score {r['score']:5.1f}   {r['by_kind']}")
    print(f"({time.time() - t0:.0f}s)")
    if "--json" in sys.argv:
        Path(sys.argv[sys.argv.index("--json") + 1]).write_text(json.dumps(out, indent=1))
