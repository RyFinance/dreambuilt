"""Candidate generation: many independent designs from one brief, then a choice by four
objectives in strict priority:

1. feasibility    hard planning / code failures (geometry that doesn't work)
2. adherence      what the brief asked for and the drawing lacks
3. quality        proportions, circulation, real-plan statistics (design.score)
4. novelty        distance from the designs already chosen (layout signatures)

Each candidate is a *genome*: a set of architectural decisions (topology, core position,
where the primary sits, what goes over the garage, room order, building shape, style when
the client didn't name one). The engine never moves rooms at random; every genome is laid
out by the same rule-checked generators, so diversity comes from different decisions, not
from noise. Seeds make every run reproducible; a new seed explores a different sample and
leads with a different (equally good) design.
"""
from __future__ import annotations

import itertools
import random
import zlib
from dataclasses import dataclass, field

from ..brief import DesignBrief

# styles an unnamed-style brief may be drawn in, by storeys (the estate is never a default)
STYLE_POOL = {1: ["craftsman", "midcentury", "modern", "farmhouse", "scandinavian", "mediterranean", "japanese"],
              2: ["colonial", "modern", "farmhouse", "craftsman", "tudor", "mediterranean", "scandinavian",
                  "foursquare"]}


@dataclass
class Candidate:
    genome: dict
    house: object = None
    hard: int = 0          # feasibility: hard failures
    prefs: int = 0         # architectural preference failures (a clean plan beats one with any)
    missing: list = field(default_factory=list)  # adherence
    quality: float = 0.0   # lower is better
    notes: list = field(default_factory=list)
    sig: frozenset = frozenset()


def _rng(b: DesignBrief, seed: int) -> random.Random:
    return random.Random(zlib.crc32(f"{b.summary()}|{seed}".encode()))


def genomes(b: DesignBrief, seed: int = 0, budget: int = 12) -> list[dict]:
    """The decisions worth trying for this brief, sampled reproducibly. The house type's
    usual answers (mirror x variant) always come first so nothing that worked before is lost."""
    from .. import styles as style_lib
    from . import estate, micro
    rng = _rng(b, seed)
    base = [{"mirror": m, "variant": v} for m, v in ((False, True), (False, False), (True, True), (True, False))]
    dims: dict[str, list] = {"mirror": [False, True], "variant": [False, True]}
    style = style_lib.get(b.style)
    garage = b.garage != "none" and "no garage" not in b.features and (b.has("garage") or b.cars > 0)
    if b.stories == 1:
        if not b.basement:
            dims["plan1"] = [None, "ell", "ell-side"] + (["courtyard"] if garage else [])
    elif not (micro.applies(b) and micro.footprint(b)):
        if style.get("layout", {}).get("estate"):
            dims["estate"] = [True, False]
        dims["core"] = [None, "center", "side"]
        if b.stories == 2:
            dims["plan2"] = [None, "grid"]  # the three-column grid with a central stair core
            dims["upper"] = [None, "stacked"]  # the upper floor planned over the main floor
        # (a main-floor primary only when the client asks: it makes the main floor bigger than
        # the floor above, and floors stay the same size unless they say otherwise)
        if garage:
            dims["over_garage"] = [None, "none"]
        if not any(p.startswith("kitchen:") for p in b.places):
            dims["kitchen"] = [None, "rear"]
        if not any(p.startswith("dining:") for p in b.places):
            dims["dining"] = [None, "front"]
        if not b.places:
            dims["living"] = [None, "rear"]
    if not getattr(b, "_style_said", True):
        pool = [s for s in STYLE_POOL[min(b.stories, 2)] if s != b.style]
        rng.shuffle(pool)
        dims["style"] = [None] + pool[:2]
    # stratified: every decision tried on its own first (so each one's effect is seen), then
    # random mixes of decisions
    picked = list(base)
    singles = []
    for k, vals in dims.items():
        if k in ("mirror", "variant"):
            continue
        for v in vals:
            if v is None:
                continue
            singles.append({"mirror": rng.random() < 0.5, "variant": rng.random() < 0.5, k: v})
    rng.shuffle(singles)
    picked += singles
    keys = [k for k in dims if k not in ("mirror", "variant")]
    tries = 0
    while len(picked) < budget + len(singles) // 2 and keys and tries < 200:
        tries += 1
        g = {"mirror": rng.random() < 0.5, "variant": rng.random() < 0.5}
        for k in keys:
            g[k] = rng.choice(dims[k])
        if g not in picked:
            picked.append(g)
    picked = picked[:max(budget, len(base) + len(singles))]
    if "upper" in dims:
        # the stacked upper floor refines whatever main floor a genome draws: try it on the
        # usual answers and the first few others too
        twins = [dict(g, upper="stacked") for g in picked if g.get("upper") is None][:10]
        picked += [g for g in twins if g not in picked]
    return picked


def evaluate(c: Candidate, b: DesignBrief) -> Candidate:
    from .. import checks
    from . import missing, score
    from .signature import signature
    found = checks.run(c.house)
    c.hard = len(checks.blocking(found))
    c.prefs = sum(f.status == "fail" and f.tier == "preference" for f in found)
    c.missing = missing(c.house, b)
    # the asked size is part of the brief: a design far off it doesn't satisfy the client
    # (with a basement, the floors above ground are measured: a basement's size follows the
    # main block above it, never the garage or the wings)
    h = c.house
    if b.basement and h.basement is not None:
        want = b.sqft - b.basement_sqft if b.basement_sqft else b.sqft * b.stories / (b.stories + 1)
        got = sum(lv.heated_area for lv in h.levels)
    else:
        want, got = b.sqft, h.heated_area
    if want and abs(got - want) / want > 0.12:
        c.missing.append(f"{want:,.0f} sq ft (drawn {got:,.0f})")
    c.quality, c.notes = score(c.house, b)
    c.sig = signature(c.house)
    return c


def choose(cands: list[Candidate], n: int, seed: int = 0, min_novelty: float = 0.08) -> list[Candidate]:
    """Best first by (feasibility, adherence, quality); then the most different of the good
    ones. A different seed leads with another design from the top band (same feasibility and
    adherence, quality within reach of the best)."""
    from .signature import novelty
    if not cands:
        return []
    # the client's taste (likes and passes so far) nudges quality: it reorders equals, it never
    # outranks feasibility or the brief
    w = taste()
    if w:
        for c in cands:
            c.quality -= 40.0 * taste_score(c.sig, w)
    ranked = sorted(cands, key=lambda c: (c.hard > 0, c.hard, len(c.missing), c.prefs > 0, c.quality))
    top = ranked[0]
    band = [c for c in ranked if c.hard == top.hard and len(c.missing) == len(top.missing)
            and (c.prefs > 0) == (top.prefs > 0) and c.quality <= top.quality + max(40.0, abs(top.quality) * 0.25)]
    # one design per signature: a near-copy never takes a slot
    uniq = []
    for c in band:
        if all(novelty(c.sig, [u.sig]) >= 0.04 for u in uniq):
            uniq.append(c)
    first = uniq[seed % len(uniq)] if uniq else top
    out = [first]
    pool = [c for c in ranked if c is not first]
    while len(out) < n and pool:
        best, best_u = None, None
        for c in pool:
            if c.hard > first.hard or len(c.missing) > len(first.missing) or (c.prefs > 0 and not first.prefs):
                continue  # never trade the brief or feasibility for variety
            nov = novelty(c.sig, [o.sig for o in out])
            if nov < min_novelty:
                continue
            u = nov - (c.quality - top.quality) / 300.0
            if best is None or u > best_u:
                best, best_u = c, u
        if best is None:
            break
        out.append(best)
        pool.remove(best)
    return out


# -- breeding and taste -------------------------------------------------------------------

def breed(b: DesignBrief, a: dict, c: dict, n: int = 3, seed: int = 0) -> list[dict]:
    """Children of two designs: each decision taken from one parent or the other (never a copy
    of either), so a child can have one parent's plan and the other's style or garage."""
    rng = random.Random(zlib.crc32(f"{sorted(a.items())}|{sorted(c.items())}|{seed}".encode()))
    keys = sorted(set(a) | set(c))
    kids: list[dict] = []
    for _ in range(40):
        g = {k: (a if rng.random() < 0.5 else c).get(k) for k in keys}
        g = {k: v for k, v in g.items() if v is not None}
        if g in (a, c) or g in kids:
            continue
        kids.append(g)
        if len(kids) >= n:
            break
    # plus mutations: each parent with one decision changed (mixing two similar parents can
    # only reproduce them, mutation makes something new nearby)
    pool = genomes(b, seed + 7, budget=24)
    muts = []
    for g in pool:
        for parent in (a, c):
            diff = [k for k in g if g[k] != parent.get(k) and k not in ("mirror", "variant")]
            if not diff:
                continue
            child = dict(parent)
            k = rng.choice(diff)
            child[k] = g[k]
            if child not in kids and child not in muts and child not in (a, c):
                muts.append(child)
    rng.shuffle(muts)
    return kids[:n] + muts[:2 * n]


def _taste_path():
    import os
    from pathlib import Path
    return Path(os.environ.get("DREAMBUILT_HISTORY") or Path.home() / ".dreambuilt") / "taste.json"


def taste() -> dict[str, float]:
    import json
    try:
        return json.loads(_taste_path().read_text())
    except (OSError, ValueError):
        return {}


def react(sig: frozenset, liked: bool) -> None:
    """Learn from a like or a pass: every token of the design's signature (arrangement,
    openness, massing, roof, facade, style) moves toward or away from the client's taste."""
    import json
    w = taste()
    for t in sig:
        w[t] = round(w.get(t, 0.0) * 0.95 + (1.0 if liked else -1.0), 3)
    try:
        p = _taste_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(w, sort_keys=True))
    except OSError:
        pass


def taste_score(sig: frozenset, w: dict | None = None) -> float:
    """-1..1: how much this design looks like the ones the client liked."""
    w = taste() if w is None else w
    if not w or not sig:
        return 0.0
    vals = [w.get(t, 0.0) for t in sig]
    peak = max(abs(v) for v in w.values()) or 1.0
    return max(-1.0, min(1.0, sum(vals) / (len(sig) * peak) * 3))
