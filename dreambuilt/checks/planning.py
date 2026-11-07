"""Hard planning rules: how people move through the house.

These are not building code; they are the rules any architect would reject a
plan for. Each rule reads the real door graph built from the plan's doors.

P1 every room can be reached from the front door (upper floors: from the stair)
P2 no room is reached only by walking through a bedroom, bathroom or closet;
   only a suite's own bath and closets may sit behind a bedroom
P3 the kitchen opens onto a dining, family, living room or nook
P4 the front door opens into an entry, hall or living space
P5 every bedroom has its own door to a hall, landing or entry
P6 a shared bathroom opens off circulation, not off a kitchen or dining room
P7 the garage opens into a mudroom, laundry or hall, never a bedroom or kitchen
P8 rooms keep usable proportions: no bathroom strips, no corridor bedrooms, no oversized halls
P9 the primary bedroom has its own ensuite and walk-in closet; every bedroom has a closet
P10 the primary is the biggest bedroom; P11 baths stack over wet rooms; P12 no twin baths
P13 no row of bathrooms (only a closet between them)
"""
from __future__ import annotations

from collections import defaultdict

from ..model import House, Level, Room

PRIVATE = {"bedroom", "bath", "powder", "closet"}
SUITE = {"bath", "closet"}  # may hang behind a bedroom
CIRCULATION = {"entry", "hall", "stair", "living", "family", "dining", "mud"}
OPEN_TO_KITCHEN = {"dining", "family", "living"}
SKIP = {"void"}


def door_graph(level: Level) -> dict[int, set[int]]:
    """Room adjacency through doors and cased openings, keyed by id(room)."""
    g: dict[int, set[int]] = defaultdict(set)
    for d in level.doors:
        if d.axis == "x":
            a, b = level.room_at(d.x, d.y - 0.3), level.room_at(d.x, d.y + 0.3)
        else:
            a, b = level.room_at(d.x - 0.3, d.y), level.room_at(d.x + 0.3, d.y)
        if a is not None and b is not None and a is not b:
            g[id(a)].add(id(b))
            g[id(b)].add(id(a))
    return g


def front_room(house: House) -> Room | None:
    from ..views.scene import _normal, place_opening
    lv = house.levels[0]
    for op in lv.openings:
        if op.kind == "door" and op.face == "S":
            pl = place_opening(lv, op)
            if pl:
                (px, py), (qx, qy) = pl.plan_points()
                nx, ny = _normal(pl.edge)
                return lv.room_at((px + qx) / 2 - nx, (py + qy) / 2 - ny)
    return next((r for r in lv.rooms if r.kind == "entry"), None)


def suite_entries(level: Level):
    """Rooms just inside each exterior door of a level (the suites' own entrances)."""
    from ..views.scene import _normal, place_opening
    out = []
    for op in level.openings:
        if op.kind != "door":
            continue
        pl = place_opening(level, op)
        if pl:
            (px, py), (qx, qy) = pl.plan_points()
            nx, ny = _normal(pl.edge)
            out.append(level.room_at((px + qx) / 2 - nx, (py + qy) / 2 - ny))
    return out


def is_ensuite(r: Room) -> bool:
    n = r.name.lower()
    return "ensuite" in n or n.startswith("primary bath") or n.endswith("closet") or n == "closet" \
        or "walk-in" in n or n == "wic"


# (min short side, max long side, max long/short) per kind; None = no limit
SHAPE = {
    "bath": (5.0, 12.5, 2.2), "powder": (3.5, 8.5, 2.4), "bedroom": (9.0, None, 2.1),
    "kitchen": (9.0, None, 2.2), "living": (11.0, None, 2.3), "family": (10.0, None, 2.3),
    "dining": (9.0, None, 2.3), "office": (8.0, None, 2.3), "laundry": (5.0, None, 3.0),
    "mud": (5.0, None, 3.0), "spice": (6.0, None, 3.0),
}


def proportions(house: House):
    from . import Finding
    out = []
    for lv in house.all_levels:
        for r in lv.rooms:
            lo, hi = sorted((r.w, r.h))
            if lo <= 0.01:
                out.append(Finding("P8 proportions", "fail", r.name, "zero-width room"))
                continue
            if r.kind == "closet" and r.area >= 24 and ("walk-in" in r.name.lower() or r.name == "Closet"):
                if lo < 4.0 or hi / lo > 3.5:
                    out.append(Finding("P8 proportions", "fail", r.name,
                                       f"{lo:g}' x {hi:g}' closet is a corridor"))
                continue
            if r.kind == "hall" and lo > 6.5 and r.name not in ("Gallery", "Foyer", "Entry", "Landing"):
                out.append(Finding("P8 proportions", "fail", f"{lv.name}: {r.name}",
                                   f"hall is {lo:g}' wide; 3'6\"-6' is plenty"))
                continue
            rule = SHAPE.get("living" if r.kind == "kitchen" and "Living" in r.name else r.kind)
            if not rule:
                continue
            mn, mx, ar = rule
            if r.kind == "bath" and r.name.startswith("Primary"):
                mx = 14.0
            bad = []
            if lo < mn - 1e-6:
                bad.append(f"under {mn:g}' wide")
            if mx and hi > mx + 1e-6:
                bad.append(f"over {mx:g}' long")
            if ar and hi / max(lo, 0.1) > ar + 1e-6:
                bad.append(f"{hi / lo:.1f}:1 is too long and narrow")
            if bad:
                out.append(Finding("P8 proportions", "fail", r.name, f"{lo:g}' x {hi:g}': " + ", ".join(bad)))
    return out


def suites(house: House):
    """Primary: ensuite + walk-in opening off it. Every bedroom: a closet of some kind."""
    from . import Finding
    out = []
    full_baths = sum(r.kind == "bath" for lv in house.levels for r in lv.rooms)
    big = house.heated_area >= 1500
    for lv in house.all_levels:
        g = door_graph(lv)
        by_id = {id(r): r for r in lv.rooms}
        fixtures = lv.fixtures
        for r in lv.rooms:
            if r.kind != "bedroom":
                continue
            nbrs = [by_id[n] for n in g.get(id(r), ()) if n in by_id]
            if r.name.startswith("Primary") and not r.unit:
                ens = [n for n in nbrs if n.kind == "bath"]
                second = [by_id[m] for e in ens for m in g.get(id(e), ()) if m in by_id]
                wic = [n for n in nbrs + second if n.kind == "closet"]
                wic += [f for f in fixtures if f.kind == "closet" and max(f.w, f.h) >= 6 and
                        r.rect.buffer(0.01).contains(__import__("shapely.geometry", fromlist=["box"])
                                                     .box(f.x, f.y, f.x + f.w, f.y + f.h))]
                if not ens and full_baths >= 2:
                    out.append(Finding("P9 suites", "fail", r.name, "no ensuite opening off the primary bedroom"))
                built_in = any(f.kind == "closet" and r.rect.buffer(0.01).contains(
                    __import__("shapely.geometry", fromlist=["box"]).box(f.x, f.y, f.x + f.w, f.y + f.h))
                    for f in fixtures)
                if not wic and (big or not built_in):
                    out.append(Finding("P9 suites", "fail", r.name, "no walk-in closet in the primary suite"))
            else:
                has_room = any(n.kind == "closet" for n in nbrs)
                inside = any(f.kind == "closet" and r.rect.buffer(0.01).contains(
                    __import__("shapely.geometry", fromlist=["box"]).box(f.x, f.y, f.x + f.w, f.y + f.h))
                    for f in fixtures)
                if not (has_room or inside):
                    out.append(Finding("P9 suites", "fail", r.name, "bedroom has no closet"))
    return out


def check(house: House):
    from . import Finding
    out: list[Finding] = []
    fr = front_room(house)
    if fr is not None:
        if fr.kind in CIRCULATION - {"mud", "dining"} or fr.kind == "family":
            out.append(Finding("P4 front door", "pass", "Entry", f"front door opens into {fr.name}"))
        else:
            out.append(Finding("P4 front door", "fail", fr.name,
                               f"front door opens straight into the {fr.name.lower()}"))
    for lv in house.all_levels:
        i = house.levels.index(lv) if lv in house.levels else -1
        rooms = [r for r in lv.rooms if r.kind not in SKIP]
        by_id = {id(r): r for r in rooms}
        g = door_graph(lv)
        if i == 0:
            starts = [fr or next((r for r in rooms if r.kind in ("entry", "living")), rooms[0])]
        else:
            starts = [next((r for r in rooms if r.kind == "stair"), rooms[0])]
        if i == -1:
            # each rental suite is entered from its own outside door
            starts += [r for r in suite_entries(lv) if r is not None]
        # walk circulation; private rooms are entered but never walked through
        reached = {id(s) for s in starts}
        via_private: dict[int, Room] = {}
        frontier = list(starts)
        start = starts[0]
        while frontier:
            nxt = []
            for r in frontier:
                if r.kind in PRIVATE and r not in starts:
                    continue
                for n in g.get(id(r), ()):
                    if n in by_id and n not in reached:
                        reached.add(n)
                        nxt.append(by_id[n])
            frontier = nxt
        # suite rooms behind a bedroom (or behind its bath) are fine
        changed = True
        while changed:
            changed = False
            for rid in list(reached):
                r = by_id[rid]
                if r.kind not in PRIVATE:
                    continue
                for n in g.get(rid, ()):
                    if n in by_id and n not in reached:
                        room = by_id[n]
                        reached.add(n)
                        changed = True
                        if room.kind not in SUITE:
                            via_private[n] = r
        for r in rooms:
            if id(r) in via_private:
                p = via_private[id(r)]
                out.append(Finding("P2 no pass-through", "fail", r.name,
                                   f"only reachable by walking through the {p.name.lower()}"))
            elif id(r) not in reached:
                out.append(Finding("P1 reachable", "fail", f"{lv.name}: {r.name}",
                                   "no way in from the front door / stair"))
        for r in rooms:
            nbrs = [by_id[n] for n in g.get(id(r), ()) if n in by_id]
            kinds = {n.kind for n in nbrs}
            if r.kind == "kitchen" and r.name == "Kitchen":
                if not kinds & (OPEN_TO_KITCHEN | {"hall"}) and not any(n.name.startswith("Nook") for n in nbrs):
                    out.append(Finding("P3 kitchen", "fail", r.name,
                                       "kitchen doesn't open onto a dining, family or living room"))
            if r.kind == "bedroom" and not kinds & {"hall", "stair", "entry", "living", "family"}:
                out.append(Finding("P5 bedroom door", "fail", r.name,
                                   "no door to a hall or landing"))
            if r.kind in ("bath", "powder") and not is_ensuite(r):
                bad = kinds & {"kitchen", "dining"}
                if bad and not kinds & {"hall", "entry", "stair", "mud", "bedroom"}:
                    out.append(Finding("P6 bath location", "fail", r.name,
                                       f"opens straight off the {sorted(bad)[0]}"))
            if r.kind == "garage":
                if kinds & {"bedroom", "kitchen", "dining", "living"}:
                    out.append(Finding("P7 garage", "fail", r.name,
                                       "garage opens into a living space"))
    out += proportions(house)
    out += suites(house)
    out += primary_biggest(house)
    out += plumbing_stacks(house)
    out += no_twin_baths(house)
    out += no_bath_rows(house)
    if not any(f.status == "fail" and f.rule.startswith("P") for f in out):
        out.append(Finding("P1-P7 circulation", "pass", "Plan",
                           "every room reached properly; no pass-through rooms"))
    return out


def primary_biggest(house: House):
    """P10: the primary bedroom is the biggest bedroom in the house (rental suites aside)."""
    from . import Finding
    beds = [r for lv in house.levels for r in lv.rooms if r.kind == "bedroom" and not r.unit]
    prim = [r for r in beds if r.name.startswith("Primary")]
    if not prim:
        return []
    p = prim[0]
    bigger = [r for r in beds if r is not p and r.area > p.area + 0.5]
    if bigger:
        r = max(bigger, key=lambda r: r.area)
        return [Finding("P10 primary biggest", "fail", p.name,
                        f"{r.name} is bigger ({r.area:.0f} vs {p.area:.0f} sq ft)")]
    return [Finding("P10 primary biggest", "pass", p.name, "the biggest bedroom")]


WET = {"bath", "powder", "kitchen", "laundry", "spice"}


def plumbing_stacks(house: House):
    """P11: an upstairs bath sits over a wet room below (bath, kitchen, laundry), or within a
    few feet of one, so its drain drops straight down a stack instead of across a ceiling."""
    from shapely.geometry import box
    from . import Finding
    out = []
    levels = house.all_levels
    for lower, upper in zip(levels, levels[1:]):
        wet = [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in lower.rooms if r.kind in WET]
        for r in upper.rooms:
            if r.kind not in ("bath", "powder") or r.unit:
                continue
            b = box(r.x, r.y, r.x + r.w, r.y + r.h)
            if any(b.intersection(w).area > 6 or b.distance(w) < 3.0 for w in wet):
                out.append(Finding("P11 plumbing stack", "pass", r.name, "over a wet room below"))
            else:
                out.append(Finding("P11 plumbing stack", "warn", r.name,
                                   f"no wet room under it on the {lower.name.lower()}: a long drain run"))
    return out


def no_twin_baths(house: House):
    """P12: no two bathrooms side by side (sharing a wall over 2'), rental suites aside."""
    from . import Finding
    out = []
    for lv in house.all_levels:
        bs = [r for r in lv.rooms if r.kind in ("bath", "powder") and not r.unit]
        for i, a in enumerate(bs):
            for b in bs[i + 1:]:
                ax0, ay0, ax1, ay1 = a.x, a.y, a.x + a.w, a.y + a.h
                bx0, by0, bx1, by1 = b.x, b.y, b.x + b.w, b.y + b.h
                vert = (abs(ax1 - bx0) < 1e-6 or abs(bx1 - ax0) < 1e-6) and min(ay1, by1) - max(ay0, by0) > 2
                horz = (abs(ay1 - by0) < 1e-6 or abs(by1 - ay0) < 1e-6) and min(ax1, bx1) - max(ax0, bx0) > 2
                if vert or horz:
                    out.append(Finding("P12 no twin baths", "fail", f"{a.name} / {b.name}",
                                       "two bathrooms side by side"))
    return out


def no_bath_rows(house: House):
    """P13: no row of bathrooms: two full baths with only a closet or linen cupboard (under
    5') between them read as a row as much as two sharing a wall (rental suites aside)."""
    from . import Finding
    from ..custom_rules import bath_rows
    rows = bath_rows(house, direct=False)  # (sharing a wall outright is P12)
    twins = {tuple(sorted(p)) for p in rows}
    out = []
    for a, b in sorted(twins):
        # a warning, not a failure: hand-drawn plans may have one; the design engine treats it
        # as a heavy penalty so generated plans avoid it
        out.append(Finding("P13 no bath rows", "warn", f"{a} / {b}",
                           "bathrooms in a row with only a closet between"))
    return out
