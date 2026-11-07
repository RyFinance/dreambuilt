"""Layout signatures: what a design *is*, independent of exact dimensions, so candidates can
be compared for real difference (topology, arrangement, massing, roof) rather than pixels.

    sig = signature(house)          # a frozenset of tokens
    distance(sig_a, sig_b)          # 0 = the same design, 1 = nothing in common
"""
from __future__ import annotations

from collections import Counter

from ..model import House

KEY_ROOMS = ("living", "kitchen", "dining", "family", "office", "garage", "stair", "entry")


def _zone(r, x0: float, y0: float, x1: float, y1: float) -> str:
    """Where a room sits on its floor: front / middle / rear and left / centre / right."""
    cx, cy = r.x + r.w / 2, r.y + r.h / 2
    fx = (cx - x0) / max(x1 - x0, 1e-6)
    fy = (cy - y0) / max(y1 - y0, 1e-6)
    # left and right are merged: a mirror image is not a different design
    col = "S" if fx < 0.36 or fx > 0.64 else "C"
    row = "F" if fy < 0.36 else ("B" if fy > 0.64 else "M")
    return row + col


def _kind(r) -> str:
    if r.kind == "bedroom":
        return "primary" if r.name.startswith("Primary") else "bedroom"
    return r.kind


def signature(h: House) -> frozenset:
    from ..checks.planning import door_graph
    tokens = set()
    tokens.add(f"storeys:{len(h.levels)}")
    tokens.add(f"style:{h.style}")
    # facade: the street windows' proportion and grouping, and how many there are
    street = [o for o in h.levels[0].openings if o.kind == "window" and o.face == "S" and o.height >= 3.5]
    for o in street:
        shape = "wide" if o.width > o.height * 1.2 else "tall" if o.height > o.width * 1.6 else "square"
        tokens.add(f"facade:{shape}")
        tokens.add(f"facade:w{round(o.width)}")
    tokens.add(f"facade:n{min(len(street), 6)}")
    tokens.add(f"basement:{h.basement is not None}")
    for i, lv in enumerate(h.levels):
        rooms = [r for r in lv.rooms if r.kind != "void"]
        if not rooms:
            continue
        fp = lv.footprint
        x0, y0, x1, y1 = fp.bounds
        # massing: how far the floor departs from its bounding box (L, U, wings)
        fill = fp.area / max((x1 - x0) * (y1 - y0), 1e-6)
        tokens.add(f"L{i}:fill:{round(fill * 5) / 5:.1f}")
        tokens.add(f"L{i}:aspect:{'wide' if (x1 - x0) > 1.25 * (y1 - y0) else 'deep' if (y1 - y0) > 1.25 * (x1 - x0) else 'square'}")
        # arrangement: where the rooms that define a plan sit
        for r in rooms:
            k = _kind(r)
            if k in KEY_ROOMS or k == "primary":
                tokens.add(f"L{i}:{k}@{_zone(r, x0, y0, x1, y1)}")
        # relations between the defining rooms: same side or opposite sides (mirror-proof)
        key = {}
        for r in rooms:
            k = _kind(r)
            if k in ("living", "kitchen", "garage", "stair", "primary", "entry") and k not in key:
                key[k] = (r.x + r.w / 2 - (x0 + x1) / 2) / max(x1 - x0, 1e-6)
        ks = sorted(key)
        for a_i, a in enumerate(ks):
            for b_ in ks[a_i + 1:]:
                fa, fb = key[a], key[b_]
                rel = "mid" if abs(fa) < 0.14 or abs(fb) < 0.14 else ("same" if fa * fb > 0 else "opp")
                tokens.add(f"L{i}:{a}|{b_}:{rel}")
        # openness: how much of the plan flows without doors (open concept vs separate rooms)
        cased = [d for d in lv.doors if getattr(d, "kind", "") in ("cased", "open")]
        tokens.add(f"L{i}:open:{min(len(cased) // 2, 4)}")
        # rooms that flow into each other through a wide opening (9'+): the open-plan core
        for d in cased:
            if d.width < 9:
                continue
            if d.axis == "x":
                a, b_ = lv.room_at(d.x, d.y - 0.3), lv.room_at(d.x, d.y + 0.3)
            else:
                a, b_ = lv.room_at(d.x - 0.3, d.y), lv.room_at(d.x + 0.3, d.y)
            if a is not None and b_ is not None:
                ka, kb = sorted((_kind(a), _kind(b_)))
                tokens.update({f"L{i}:open-plan", f"L{i}:{ka}~{kb}", f"L{i}:flow:{ka}", f"L{i}:flow:{kb}"})
        # topology: which kinds of room open into which
        by_id = {id(r): r for r in rooms}
        g = door_graph(lv)
        edges = Counter()
        for a, ns in g.items():
            for b in ns:
                if a < b and a in by_id and b in by_id:
                    edges[tuple(sorted((_kind(by_id[a]), _kind(by_id[b]))))] += 1
        for (a, b), n in edges.items():
            if a in ("closet",) or b in ("closet",):
                continue
            tokens.add(f"L{i}:{a}-{b}")
    # roof: masses and ridge directions
    for m in h.roofs:
        if m.name.startswith(("Porch", "Dormer")):
            continue
        tokens.add(f"roof:{m.kind}:{m.ridge if m.kind != 'shed' else m.low_side}")
    tokens.add(f"roofs:{min(4, sum(1 for m in h.roofs if not m.name.startswith(('Porch', 'Dormer'))))}")
    return frozenset(tokens)


def distance(a: frozenset, b: frozenset) -> float:
    """Jaccard distance between two signatures."""
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def novelty(sig: frozenset, others: list[frozenset]) -> float:
    """How different a design is from the closest of the others (1.0 when there are none)."""
    return min((distance(sig, o) for o in others), default=1.0)
