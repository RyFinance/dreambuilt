"""Fill a laid-out plan with openings, doors, fixtures, porch, roof, chimney and lot."""
from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import box
from shapely.ops import unary_union

from ..geometry import lines_of
from ..model import (Chimney, Fixture, InteriorDoor, Level, Lot, Opening, Porch, RoofMass, Room,
                     Steps)

EXT = 0.5  # exterior wall thickness
INT = 0.375 / 2  # half an interior partition

CASED = [{"entry", "hall"}, {"hall", "family"}, {"kitchen", "nook"}, {"spice", "kitchen"},
         {"living", "dining"}, {"dining", "kitchen"}, {"living", "entry"}, {"entry", "stair"},
         {"hall", "stair"}, {"living", "hall"}, {"living", "kitchen"}, {"kitchen", "family"},
         {"living", "family"}, {"dining", "family"}, {"dining", "hall"}]
PUBLIC = {"living", "dining", "kitchen", "entry", "family", "hall", "stair", "mud"}


# -- geometry helpers -----------------------------------------------------------

_FP = {"fp": None}


_OPEN = {"on": False}
OPEN_PLAN = [{"kitchen", "family"}, {"kitchen", "dining"}, {"family", "dining"}, {"living", "dining"}]


def use_open_plan(on: bool) -> None:
    """Open concept: the kitchen, great room and dining share one space (only a wall stub
    at each end of their shared edges)."""
    _OPEN["on"] = on


def use_footprint(fp) -> None:
    """Set the level outline that exterior-side tests use (None: the W x D rectangle)."""
    _FP["fp"] = fp


def sides_on_exterior(r: Room, W: float, D: float) -> dict[str, tuple[float, float]]:
    """Exterior sides of a room, with the part of each that lies on the outside wall."""
    fp = _FP["fp"]
    if fp is None:
        fp = box(0, 0, W, D)
    ring = fp.exterior
    out = {}
    sides = {"S": ((r.x, r.y), (r.x + r.w, r.y)), "N": ((r.x, r.y + r.h), (r.x + r.w, r.y + r.h)),
             "W": ((r.x, r.y), (r.x, r.y + r.h)), "E": ((r.x + r.w, r.y), (r.x + r.w, r.y + r.h))}
    from shapely.geometry import LineString
    for face, (a, b) in sides.items():
        seg = LineString([a, b])
        on = seg.intersection(ring.buffer(1e-6))
        parts = [g for g in lines_of(on) if g.length > 2.0]
        if not parts:
            continue
        g = max(parts, key=lambda g: g.length)
        (x0, y0), (x1, y1) = g.coords[0], g.coords[-1]
        span = (min(x0, x1), max(x0, x1)) if face in ("S", "N") else (min(y0, y1), max(y0, y1))
        out[face] = span
    return out


def shared_edge(a: Room, b: Room):
    """(axis, line, s0, s1) of the wall a and b share, or None. axis is the wall direction."""
    seg = [s for s in lines_of(a.rect.boundary.intersection(b.rect.boundary)) if s.length > 0.05]
    if not seg:
        return None
    s = max(seg, key=lambda g: g.length)
    (x0, y0), (x1, y1) = s.coords[0], s.coords[-1]
    if abs(y0 - y1) < 1e-6:
        return ("x", y0, min(x0, x1), max(x0, x1))
    return ("y", x0, min(y0, y1), max(y0, y1))


def inner(r: Room, W: float, D: float):
    """Clear floor rectangle inside the walls."""
    ext = sides_on_exterior(r, W, D)
    return (r.x + (EXT if "W" in ext else INT), r.y + (EXT if "S" in ext else INT),
            r.x + r.w - (EXT if "E" in ext else INT), r.y + r.h - (EXT if "N" in ext else INT))


# -- doors ----------------------------------------------------------------------

# which rooms a room may be entered from, best first (hard planning rules live here)
ENTER_FROM = {
    "bedroom": ["hall", "stair", "entry", "family", "living"],
    "bath": ["hall", "stair", "entry", "mud"],
    "powder": ["entry", "hall", "mud", "stair"],
    "office": ["entry", "hall", "living", "family"],
    "laundry": ["mud", "hall", "kitchen", "garage"],
    "mud": ["garage", "kitchen", "hall", "entry", "laundry"],
    "garage": ["mud", "laundry", "hall", "entry"],
    "spice": ["kitchen"],
    "kitchen": ["family", "dining", "living", "hall", "entry"],
    "dining": ["living", "kitchen", "family", "hall", "entry"],
    "family": ["kitchen", "hall", "living", "dining", "entry", "stair"],
    "living": ["entry", "hall", "dining", "family"],
    "hall": ["entry", "stair", "hall", "living", "family", "dining", "kitchen"],
    "stair": ["entry", "hall", "living", "family", "dining"],
    "closet": ["hall", "entry", "mud", "stair", "bedroom", "bath", "powder", "laundry", "kitchen",
               "living", "family", "office", "dining",
               "spice", "office"],
    "pantry": ["kitchen", "spice", "mud"],
}
OPEN_PAIRS = [("living", "dining"), ("dining", "kitchen"), ("kitchen", "family"),
              ("entry", "living"), ("entry", "stair"), ("hall", "stair"), ("living", "hall"),
              ("entry", "hall"), ("family", "dining"), ("hall", "family"), ("hall", "kitchen")]


def _suite_owner(r: Room, nbrs: list[Room]) -> list[str]:
    """Ensuites and walk-ins open from their bedroom (or the bedroom's bath)."""
    n = r.name.lower()
    if "ensuite" in n or n.startswith("primary bath"):
        return ["bedroom"]
    if r.kind == "closet" and (n == "closet" or "walk-in" in n or n == "wic"):
        return ["bedroom", "bath", "hall", "stair", "family", "office"]
    if r.name.startswith("Nook"):
        return ["kitchen", "family", "dining"]
    return []


def connections(rooms: list[Room]) -> list[tuple[Room, Room]]:
    """Which rooms get a door or opening between them (from, into), by the rules above."""
    rooms = [r for r in rooms if r.kind != "void"]
    adj: dict[int, list[Room]] = {}
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            if a.unit != b.unit:
                continue  # suites are sealed from each other and from the house
            e = shared_edge(a, b)
            if e and e[3] - e[2] >= 2.6:
                adj.setdefault(id(a), []).append(b)
                adj.setdefault(id(b), []).append(a)
    pairs: list[tuple[Room, Room]] = []

    def link(a: Room, b: Room):
        if (a, b) not in pairs and (b, a) not in pairs:
            pairs.append((a, b))

    def allowed(r: Room) -> list[str]:
        kinds = _suite_owner(r, adj.get(id(r), [])) or ENTER_FROM.get(r.kind, ["hall", "entry"])
        if any(n.name.startswith(("Rec Room", "Flex Room", "Games Room")) for n in adj.get(id(r), [])):
            kinds = kinds + ["family"]  # a basement rec room is the hall down there
        return kinds

    def best(r: Room, seen: set | None = None) -> Room | None:
        nbrs = adj.get(id(r), [])
        for kind in allowed(r):
            cands = [n for n in nbrs if n.kind == kind and (seen is None or id(n) in seen)]
            if r.name.lower().startswith("primary bath") or "ensuite" in r.name.lower():
                # prefer the matching bedroom: "Ensuite 3" -> "Bedroom 3", "Primary Bath" -> primary
                key = r.name.split()[-1]
                cands.sort(key=lambda n: (not n.name.endswith(key), not n.name.startswith("Primary")))
            if cands:
                return max(cands, key=lambda n: shared_edge(n, r)[3] - shared_edge(n, r)[2]) \
                    if not ("ensuite" in r.name.lower() or r.name.startswith("Primary Bath")) else cands[0]
        return None

    for r in rooms:
        if r.kind in ("entry",):
            continue
        t = best(r)
        if t is not None:
            link(t, r)
    for a_kind, b_kind in OPEN_PAIRS:
        for a in rooms:
            if a.kind != a_kind:
                continue
            for b in adj.get(id(a), []):
                if b.kind == b_kind:
                    link(a, b)
    # anything unreachable joins a reachable neighbour, but only one it may be entered from
    start = next((r for r in rooms if r.kind in ("entry",)), None) or \
        next((r for r in rooms if r.kind in ("stair", "living")), rooms[0])
    if any(r.unit for r in rooms):
        # each suite links up from its own hall; only the house part walks from the stair
        for unit in {r.unit for r in rooms if r.unit}:
            hall = next((r for r in rooms if r.unit == unit and r.kind == "hall"), None)
            if hall:
                for r in rooms:
                    if r.unit == unit and r is not hall and id(r) not in _reach(hall, pairs):
                        t = best(r, _reach(hall, pairs))
                        if t is not None:
                            link(t, r)
    for _ in range(len(rooms)):
        seen = _reach(start, pairs)
        missing = [r for r in rooms if id(r) not in seen]
        if not missing:
            break
        progressed = False
        for r in missing:
            t = best(r, seen)
            if t is not None:
                link(t, r)
                progressed = True
        if not progressed:
            break
    return pairs


def _reach(start: Room, pairs) -> set[int]:
    seen = {id(start)}
    changed = True
    while changed:
        changed = False
        for a, b in pairs:
            if (id(a) in seen) != (id(b) in seen):
                seen |= {id(a), id(b)}
                changed = True
    return seen


def make_doors(rooms: list[Room], known: Optional[list] = None) -> list[InteriorDoor]:
    """Doors from the rules; `known` pairs (from a real plan) come first and the rules fill in
    whatever those leave unreachable."""
    doors = []
    pairs = list(connections(rooms))
    if known:
        real = [(a, b) for a, b in known if a in rooms and b in rooms and shared_edge(a, b)
                and shared_edge(a, b)[3] - shared_edge(a, b)[2] >= 2.6]
        keep = [p for p in pairs if {p[0].kind, p[1].kind} in CASED]  # open plan stays open
        pairs = real + [p for p in keep if p not in real and (p[1], p[0]) not in real]
        start = next((r for r in rooms if r.kind == "entry"), rooms[0])
        seen = _reach(start, pairs)
        for p in connections(rooms):
            if (id(p[0]) in seen) != (id(p[1]) in seen) and p not in pairs:
                pairs.append(p)
                seen = _reach(start, pairs)
        # last resort for a real plan: storage, mechanical and garages open off any reachable
        # neighbour that isn't a bedroom or bath; a bath off its bedroom
        for _ in range(3):
            for r in rooms:
                if id(r) in seen or r.kind == "void":
                    continue
                ok = {"closet": None, "garage": None, "laundry": None, "mud": None}
                for n in rooms:
                    if id(n) not in seen or n is r:
                        continue
                    e = shared_edge(n, r)
                    if not e or e[3] - e[2] < 2.6:
                        continue
                    if r.kind in ok and n.kind not in ("bedroom", "bath", "powder"):
                        pairs.append((n, r))
                    elif r.kind == "bath" and n.kind == "bedroom":
                        pairs.append((n, r))
                    else:
                        continue
                    seen = _reach(start, pairs)
                    break
    for a, b in pairs:
        e = shared_edge(a, b)
        if not e:
            continue
        axis, line, s0, s1 = e
        L = s1 - s0
        cased = {a.kind, b.kind} in CASED
        if cased:
            w = min(L - 1.5, 6.0 if {a.kind, b.kind} in ({"living", "dining"}, {"dining", "kitchen"},
                                                          {"living", "family"}) else 3.5)
            w = max(w, min(3.0, L - 0.6))
            if _OPEN["on"] and {a.kind, b.kind} in OPEN_PLAN and L >= 6:
                w = L - 1.0
            c = (s0 + s1) / 2
            x, y = (c, line) if axis == "x" else (line, c)
            doors.append(InteriorDoor(x, y, axis, round(w * 2) / 2, kind="cased"))
            continue
        w = 2.67 if b.kind in ("bedroom", "office", "mud", "laundry", "family") else 2.5
        if b.kind == "closet" and L < 4:
            w = 2.0
        w = min(w, L - 0.6)
        # hinge near the corner of the shared wall, leaf swings into room b
        c = s0 + 0.35 + w / 2
        x, y = (c, line) if axis == "x" else (line, c)
        bx, by = b.center
        swing = "+" if ((by > line) if axis == "x" else (bx > line)) else "-"
        doors.append(InteriorDoor(x, y, axis, w, swing=swing, hinge="start"))
    return doors


# longest a small room may run before the rest becomes a closet
CAP = {"bath": 9.5, "powder": 7.0, "laundry": 9.5, "spice": 13.0}


def split_long(rooms: list[Room]) -> list[Room]:
    """Trim until nothing changes (a room can be too long in both directions)."""
    for _ in range(3):
        n = len(rooms)
        rooms = _split_once(rooms)
        if len(rooms) == n:
            break
    return rooms


def _split_once(rooms: list[Room]) -> list[Room]:
    """Trim strip-shaped small rooms; the leftover becomes a closet for a neighbouring bedroom.

    The room keeps the end that touches circulation (hall, entry, kitchen, mud or its
    bedroom); the far end is cut off. Primary baths turn their leftover into the walk-in.
    """
    out = list(rooms)
    for r in list(rooms):
        cap = CAP.get(r.kind)
        if r.kind == "bedroom":
            cap = round(min(r.w, r.h) * 1.65 * 2) / 2  # deep bedrooms give their far end to a closet
        if r.kind == "office":
            cap = round(min(r.w, r.h) * 1.7 * 2) / 2
        if r.kind == "bath":
            cap = min(cap, round(min(r.w, r.h) * 2.1 * 2) / 2)
        if r.kind == "closet" and ("walk-in" in r.name.lower() or r.name == "Closet"):
            cap = max(6.0, round(min(r.w, r.h) * 3.0 * 2) / 2)
        if cap is None:
            continue
        if r.name.startswith("Primary") and r.kind == "bath":
            cap = 12.0
        lo, hi = sorted((r.w, r.h))
        if hi <= cap + 1e-6 or hi - cap < {"bath": 2.0, "closet": 2.0, "bedroom": 4.0,
                                            "office": 3.0}.get(r.kind, 3.5):
            continue
        along_y = r.h >= r.w
        keep = round(cap * 2) / 2
        # which end faces circulation?
        wants = {"hall", "entry", "stair", "kitchen", "mud", "family", "landing"}
        if r.kind == "bath" and ("ensuite" in r.name.lower() or r.name.startswith("Primary")):
            wants = {"bedroom"}
        if r.kind in ("laundry", "mud"):
            wants = wants | {"garage"}  # the end the garage door opens into stays
            touch = {n.kind for n in rooms if n is not r and shared_edge(r, n)}
            if "garage" in touch and touch & {"hall", "entry", "kitchen"}:
                continue  # a mud hall from the house to the garage: keep it whole
        lo_end = hi_end = 0.0
        for n in rooms:
            if n is r or n.kind not in wants:
                continue
            e = shared_edge(r, n)
            if not e:
                continue
            axis, line, s0, s1 = e
            if n.kind == "garage":
                # count the garage end three times over
                lo0, hi0 = lo_end, hi_end
                for _ in range(2):
                    if along_y and axis == "x" or not along_y and axis == "y":
                        if abs(line - (r.y if along_y else r.x)) < 1e-6:
                            lo_end += 10
                        else:
                            hi_end += 10
            if along_y and axis == "y":
                lo_end += max(0, min(s1, r.y + keep) - max(s0, r.y))
                hi_end += max(0, min(s1, r.y + r.h) - max(s0, r.y + r.h - keep))
            elif along_y and axis == "x":
                if abs(line - r.y) < 1e-6:
                    lo_end += 10
                else:
                    hi_end += 10
            elif not along_y and axis == "x":
                lo_end += max(0, min(s1, r.x + keep) - max(s0, r.x))
                hi_end += max(0, min(s1, r.x + r.w) - max(s0, r.x + r.w - keep))
            elif not along_y and axis == "y":
                if abs(line - r.x) < 1e-6:
                    lo_end += 10
                else:
                    hi_end += 10
        keep_low = lo_end >= hi_end
        cut_len = hi - keep

        def strip(low: bool):
            if along_y:
                return box(r.x, r.y + keep, r.x + r.w, r.y + r.h) if low else box(r.x, r.y, r.x + r.w, r.y + r.h - keep)
            return box(r.x + keep, r.y, r.x + r.w, r.y + r.h) if low else box(r.x, r.y, r.x + r.w - keep, r.y + r.h)

        def touches_suite(low: bool) -> bool:
            st = strip(low).buffer(0.02)
            return any((n.kind == "bath" or (n.kind == "closet" and n.name not in ("Linen", "Storage", "Coat")))
                       and n is not r and n.rect.intersection(st).area > 0.05 for n in rooms)

        if r.kind == "bedroom" and touches_suite(keep_low):
            if touches_suite(not keep_low):
                continue  # suite rooms on both ends: leave the bedroom whole
            keep_low = not keep_low  # cut the other end instead
        cut_strip = strip(keep_low)
        if r.kind == "bedroom":
            # never cut off a bedroom's outside wall (its egress window lives there)
            ext = sides_on_exterior(r, 1e9, 1e9) if _FP["fp"] is not None else {}
            low_face, high_face = ("S", "N") if along_y else ("W", "E")
            cut_face = high_face if keep_low else low_face
            if cut_face in ext and len(ext) == 1:
                continue
        bedroom_side = any(n.kind == "bedroom" and shared_edge(r, n) for n in rooms if n is not r)
        if r.kind == "office":
            name = "Storage"
        elif cut_len < 4.0:
            name = "Linen"  # too shallow to walk into
        elif r.kind == "bedroom":
            name = "Walk-in Closet" if r.name.startswith("Primary") else "Closet"
        else:
            name = "Walk-in Closet" if r.name.startswith("Primary") else ("Closet" if bedroom_side else "Linen")
        if along_y:
            if keep_low:
                rest = Room(name, "closet", r.x, r.y + keep, r.w, r.h - keep, r.unit)
                r.h = keep
            else:
                rest = Room(name, "closet", r.x, r.y, r.w, r.h - keep, r.unit)
                r.y, r.h = r.y + r.h - keep, keep
        else:
            if keep_low:
                rest = Room(name, "closet", r.x + keep, r.y, r.w - keep, r.h, r.unit)
                r.w = keep
            else:
                rest = Room(name, "closet", r.x, r.y, r.w - keep, r.h, r.unit)
                r.x, r.w = r.x + r.w - keep, keep
        out.append(rest)
    return out


def door_clearance(d: InteriorDoor):
    w = d.width
    if d.axis == "x":
        return box(d.x - w / 2, d.y - w, d.x + w / 2, d.y + w)
    return box(d.x - w, d.y - w / 2, d.x + w, d.y + w / 2)


# -- windows and exterior doors -------------------------------------------------

def make_openings(level: Level, W: float, D: float, style: dict, first: bool,
                  front_door_x: Optional[float], chimney_side: Optional[str],
                  chimney_span: Optional[tuple[float, float]]) -> list[Opening]:
    win = style.get("windows", {})
    sill = win.get("sill_height", 2.5)
    head = win.get("head_height", 7.0)
    op = win.get("operation", "double-hung")
    ops: list[Opening] = []
    taken: dict[str, list[tuple[float, float]]] = {f: [] for f in "SNEW"}

    def add(kind, face, start, width, height, sill_, operation, grille=None, line=None):
        ops.append(Opening(kind, face, round(start * 4) / 4, width, height, sill_, grille,
                           operation, line=line))
        taken[face].append((start - 0.5, start + width + 0.5))

    def line_of(r: Room, face: str) -> float:
        return {"S": r.y, "N": r.y + r.h, "W": r.x, "E": r.x + r.w}[face]

    def free(face, a, b):
        return all(b <= t0 or a >= t1 for t0, t1 in taken[face])

    # front and rear doors first
    if first:
        front_room = next((r for r in level.rooms if r.kind == "entry"), None) or \
            next((r for r in level.rooms if r.kind == "living"), None)
        ext = sides_on_exterior(front_room, W, D)
        a, b = ext.get("S", (front_room.x, front_room.x + front_room.w))
        fx = front_door_x if front_door_x is not None else (a + b) / 2
        fx = min(max(fx, a + 2.0), b - 2.0)
        add("door", "S", fx - 1.5, 3.0, 6.83, 0.0, "swing", line=line_of(front_room, "S"))
        rear = None
        for kind in ("mud", "laundry", "family", "kitchen"):
            rear = next((r for r in level.rooms if r.kind == kind and sides_on_exterior(r, W, D)), None)
            if rear:
                break
        rext = sides_on_exterior(rear, W, D) if rear else {}
        for face in ("N", "E", "W"):
            if face in rext:
                a, b = rext[face]
                if b - a >= 4.5:
                    # a kitchen keeps the middle of its wall for the sink window
                    st = b - 3.9 if rear.kind == "kitchen" else (a + b) / 2 - 1.33
                    add("door", face, st, 2.67, 6.83, 0.0, "swing", line=line_of(rear, face))
                    break
    egress_op = "casement" if op == "fixed" else op
    big = bool(win.get("big"))
    # facade composition: each style's window (unit x group, height, sill); see styles/*.yaml
    fac = style.get("facade") or {}
    fac_unit = float(fac.get("unit", 3.0))
    fac_w = fac_unit * int(fac.get("group", 1))
    fac_h = float(fac.get("height", head - sill))
    fac_sill = float(fac.get("sill", sill))
    fac_grille = f"{int(fac.get('group', 1))}/0" if int(fac.get("group", 1)) > 1 else None
    for r in level.rooms:
        ext = sides_on_exterior(r, W, D)
        if not ext:
            continue
        k = r.kind
        plan: list[tuple[str, int, float, float, float, str]] = []  # face, n, width, height, sill, op
        if k in ("living", "family", "dining", "office") and big:
            # big glass: one or two wide picture windows per wall, low sills, tall heads
            for face, (a, b) in ext.items():
                n = max(1, min(2, int((b - a) // 12)))
                w = round(min(8.0, max(4.0, (b - a) / n - 4.0)) * 2) / 2
                plan.append((face, n, w, head + 0.5 - 1.0, 1.0, "fixed"))
        elif k in ("living", "family", "dining", "office") and fac:
            # the style's own window: unit width, sashes grouped side by side, proportion
            for face, (a, b) in ext.items():
                w = fac_w if (b - a) >= fac_w + 2.5 else fac_unit
                n = max(1, min(3 if fac.get("rhythm") != "ribbon" else 2, int((b - a) // (w + 3.0))))
                if k in ("living", "family") and len(ext) == 1 and (b - a) >= 2 * w + 4.0:
                    n = max(n, 2)  # a living room lit from one wall gets two windows, not one
                plan.append((face, n, w, fac_h, fac_sill, op))
        elif k in ("living", "family", "dining", "office"):
            for face, (a, b) in ext.items():
                n = max(1, min(3, int((b - a) // 6)))
                if k in ("living", "family") and len(ext) == 1 and (b - a) >= 10.0:
                    n = max(n, 2)
                plan.append((face, n, 3.0, head - sill, sill, op))
        elif k == "void":
            for face, (a, b) in ext.items():
                plan.append((face, 2, 3.0, 6.5, 1.5, "fixed"))
        elif k == "bedroom":
            faces = sorted(ext.items(), key=lambda kv: (kv[0] not in ("S", "N"), -(kv[1][1] - kv[1][0])))
            for i, (face, (a, b)) in enumerate(faces[:2]):
                n = 2 if (b - a) >= 13 and i == 0 and not big else 1
                w = 5.0 if big and (b - a) >= 9 else 3.0
                hh, ss = max(head - sill, 4.0), min(sill, 3.0)
                if fac and not big:
                    # the style's window, kept big enough to climb out of (egress)
                    w = fac_w if (b - a) >= fac_w + 2.5 else max(fac_unit, 3.0)
                    n = 1 if fac.get("group", 1) > 1 or fac.get("rhythm") == "ribbon" else n
                    hh, ss = max(fac_h, 4.0), min(fac_sill, 3.0)
                plan.append((face, n, w, hh, ss, egress_op))
        elif k == "kitchen":
            face = "N" if "N" in ext else next(iter(ext))
            plan.append((face, 2, 3.0, 3.5, 3.5, op))
            for other in ext:
                if other != face:
                    plan.append((other, 1, 3.0, 3.5, 3.5, op))
        elif k in ("bath", "powder"):
            face = "N" if "N" in ext else next(iter(ext))
            plan.append((face, 1, 2.0, 3.0, 4.5, "awning" if op != "fixed" else "fixed"))
        elif k in ("stair", "hall", "laundry", "entry") and k != "entry":
            face, (a, b) = max(ext.items(), key=lambda kv: kv[1][1] - kv[1][0])
            if b - a >= 4:
                plan.append((face, 1, 2.0, 3.0, 4.5 if k != "stair" else 5.0, op))
        elif k == "entry":
            pass
        for face, n, w, h, s_, o in plan:
            a, b = ext[face]
            if chimney_side == face and chimney_span:
                spans = [(a, chimney_span[0] - 0.75), (chimney_span[1] + 0.75, b)]
                spans = [(p, q) for p, q in spans if q - p >= w + 1.0]
                per = [(p, q, 1) for p, q in spans]
            else:
                per = [(a, b, n)]
            for p, q, m in per:
                grille = None
                if fac_grille and w >= fac_w - 1e-6 and k in ("living", "family", "dining", "office", "bedroom"):
                    o = "casement" if o == "double-hung" else o  # (grouped sashes: casements in a row)
                    grille = fac_grille
                if o == "casement" and k in ("living", "family", "dining") and chimney_side == face:
                    grille = "2/0"
                margin = 1.25
                room = q - p - 2 * margin
                m = max(1, min(m, int(room // (w + 1.0)) if room > w else 1))
                if room < w:
                    continue
                if k == "kitchen":  # a mulled pair over the sink
                    start = (p + q) / 2 - w
                    for j in range(2):
                        if free(face, start + j * w, start + (j + 1) * w):
                            add("window", face, start + j * w, w, h, s_, o, grille, line_of(r, face))
                    continue
                step = room / m
                for j in range(m):
                    st = p + margin + step * (j + 0.5) - w / 2
                    if free(face, st, st + w):
                        add("window", face, st, w, h, s_, o, grille, line_of(r, face))
    return ops


# -- fixtures -------------------------------------------------------------------

def make_fixtures(level: Level, W: float, D: float, upper: bool, stair_dir: str = "N") -> list[Fixture]:
    clear = [door_clearance(d) for d in level.doors]
    from ..views.scene import place_opening
    for op in level.openings:
        if op.kind == "door":
            pl = place_opening(level, op)
            if pl:
                (px, py), (qx, qy) = pl.plan_points()
                clear.append(box(min(px, qx) - 0.2, min(py, qy) - 3.5, max(px, qx) + 0.2,
                                 max(py, qy) + 3.5))
    blocked = unary_union(clear) if clear else None
    out: list[Fixture] = []

    def ok(x0, y0, x1, y1, room_box) -> bool:
        b = box(x0, y0, x1, y1)
        if not room_box.buffer(1e-6).contains(b):
            return False
        if blocked is not None and b.intersects(blocked):
            return False
        return not any(b.intersects(box(f.x, f.y, f.x + f.w, f.y + f.h)) for f in out
                       if f.kind not in ("counter",))

    def against(r: Room, side: str, length: float, depth: float, offset: float = 0.0,
                align: str = "center"):
        """Rectangle of `length` x `depth` against `side` of the room's clear floor."""
        x0, y0, x1, y1 = inner(r, W, D)
        if side in ("N", "S"):
            span0, span1 = x0, x1
        else:
            span0, span1 = y0, y1
        if align == "start":
            a = span0 + offset
        elif align == "end":
            a = span1 - offset - length
        else:
            a = (span0 + span1) / 2 - length / 2 + offset
        b = a + length
        if side == "N":
            return (a, y1 - depth, b, y1)
        if side == "S":
            return (a, y0, b, y0 + depth)
        if side == "E":
            return (x1 - depth, a, x1, b)
        return (x0, a, x0 + depth, b)

    def put(kind, rect, back, room_box) -> bool:
        x0, y0, x1, y1 = rect
        if ok(x0, y0, x1, y1, room_box):
            out.append(Fixture(kind, x0, y0, x1 - x0, y1 - y0, back))
            return True
        return False

    def door_sides(r: Room) -> set[str]:
        sides = set()
        for d in level.doors:
            if d.axis == "x":
                if abs(d.y - r.y) < 1e-6 and r.x < d.x < r.x + r.w:
                    sides.add("S")
                if abs(d.y - r.y - r.h) < 1e-6 and r.x < d.x < r.x + r.w:
                    sides.add("N")
            else:
                if abs(d.x - r.x) < 1e-6 and r.y < d.y < r.y + r.h:
                    sides.add("W")
                if abs(d.x - r.x - r.w) < 1e-6 and r.y < d.y < r.y + r.h:
                    sides.add("E")
        return sides

    opposite = {"N": "S", "S": "N", "E": "W", "W": "E"}
    for r in level.rooms:
        ib = box(*inner(r, W, D))
        ix0, iy0, ix1, iy1 = ib.bounds
        iw, ih = ix1 - ix0, iy1 - iy0
        ext = sides_on_exterior(r, W, D)
        dsides = door_sides(r)
        backs = [s for s in ("N", "S", "E", "W") if s not in dsides]
        backs.sort(key=lambda s: (opposite[s] not in dsides, s not in ("N", "S")))
        k = r.kind
        if k == "stair":
            x0, y0, x1, y1 = ix0 + 0.05, iy0 + 0.25, ix1 - 0.05, iy1 - 0.25
            if min(r.w, r.h) >= 7.0:
                # a U stair: up the first flight from the south, landing at the north, and
                # the second flight back to the south end
                out.append(Fixture("stair-u-down" if upper else "stair-u", x0, y0, x1 - x0,
                                   y1 - y0, "N"))
            elif r.h >= r.w:
                # a code run (7 3/4" rise, 10" tread) for this storey; anything longer is a
                # landing at the foot, so the first step never sits against a wall
                risers = math.ceil((level.ceiling + 1.0) * 12 / 7.75)
                run = (risers - 1) * 10 / 12
                spare = (y1 - y0) - run
                if spare > 0.5:
                    if stair_dir == "N":
                        y0 += spare
                    else:
                        y1 -= spare
                out.append(Fixture("stair-down" if upper else "stair", x0, y0, x1 - x0, y1 - y0,
                                   stair_dir))
            else:
                out.append(Fixture("stair-down" if upper else "stair", x0, y0, x1 - x0, y1 - y0, "E"))
        elif k == "kitchen":
            side = "N" if "N" in ext else (next(iter(ext)) if ext else "N")
            run = (iw if side in ("N", "S") else ih) - 0.2
            put("counter", against(r, side, run, 2.0), side, ib)
            put("sink", against(r, side, 3.0, 2.0), side, ib)
            put("range", against(r, side, 2.5, 2.0, offset=1.0, align="start"), side, ib)
            put("fridge", against(r, side, 2.75, 2.25, offset=0.1, align="end"), side, ib)
            if iw >= 12 and ih >= 12:
                cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
                w_, h_ = (6.0, 3.0) if iw >= ih else (3.0, 6.0)
                put("counter", (cx - w_ / 2, cy - h_ / 2, cx + w_ / 2, cy + h_ / 2), "S", ib)
        elif k in ("bath", "powder"):
            for back in backs or ["N"]:
                along = iw if back in ("N", "S") else ih
                if k == "bath" and along >= 5.0 and put("tub", against(r, back, 5.0 if along < 5.6 else along - 0.1, 2.5), back, ib):
                    break
                if k == "bath" and put("shower", against(r, back, 3.0, 3.0, align="start"), back, ib):
                    break
                if k == "powder":
                    break
            placed_side = backs[0] if backs else "N"
            sides = [s for s in ("E", "W", "N", "S") if s not in dsides]
            for s in sides:
                if put("toilet", against(r, s, 1.5, 2.25, offset=0.3, align="end"), s, ib):
                    break
            for s in sides:
                wv = 4.5 if (k == "bath" and r.name.startswith("Primary") and
                             (iw if s in ("N", "S") else ih) >= 7) else 2.0
                if put("vanity", against(r, s, wv, 1.75, offset=0.3, align="start"), s, ib):
                    break
            _ = placed_side
        elif k == "laundry":
            for s in backs or ["N"]:
                along = iw if s in ("N", "S") else ih
                if along >= 5.5:
                    a = against(r, s, 5.25, 2.5)
                    if s in ("N", "S"):
                        w1 = (a[0], a[1], a[0] + 2.5, a[3])
                        w2 = (a[2] - 2.5, a[1], a[2], a[3])
                    else:
                        w1 = (a[0], a[1], a[2], a[1] + 2.5)
                        w2 = (a[0], a[3] - 2.5, a[2], a[3])
                    if ok(*w1, ib) and ok(*w2, ib):
                        put("washer", w1, s, ib)
                        put("dryer", w2, s, ib)
                        break
        elif k == "bedroom":
            interior = [s for s in ("N", "S", "E", "W") if s not in ext]
            interior.sort(key=lambda s: -(iw if s in ("N", "S") else ih))
            for s in interior:
                along = iw if s in ("N", "S") else ih
                ln = min(8.0, along - 3.2)
                if ln < 4:
                    continue
                done = False
                for align in ("end", "start", "center"):
                    if put("closet", against(r, s, ln, 2.0, offset=0.1, align=align), s, ib):
                        done = True
                        break
                if done:
                    break
        elif k == "closet" and r.area >= 12 and r.name not in ("Coat",):
            s = max(("N", "S", "E", "W"), key=lambda s: (s not in dsides, iw if s in ("N", "S") else ih))
            along = iw if s in ("N", "S") else ih
            put("closet", against(r, s, along - 0.2, min(2.0, (ih if s in ("N", "S") else iw) - 0.5)), s, ib)
    return out


# -- porch, roof, chimney, lot ------------------------------------------------------

def make_porch(style: dict, W: float, D: float, floor_z: float, plate_z: float,
               door_x: float, stories: int, wants_porch: bool):
    lay = style.get("layout", {})
    kind = lay.get("porch", "gable")
    if kind == "grand":  # the estate's covered entry, on a smaller house: a gabled portico
        kind, lay = "portico", {**lay, "porch_width": 12, "porch_depth": 6, "porch_pitch": 10}
    if style.get("roof", {}).get("kind") == "shed" and style.get("roof", {}).get("pitch", 6) < 1:
        kind = "canopy"  # a flat-roofed house gets a thin flat canopy over the door
    if kind == "stoop" and wants_porch:
        kind = "shed"
        lay = {**lay, "porch_width": 0.5, "porch_depth": 7, "porch_pitch": 3}
    pw = lay.get("porch_width", 0.42)
    width = pw * W if pw <= 1.0 else pw
    width = max(8.0, min(round(width * 2) / 2, W))
    depth = float(lay.get("porch_depth", 8))
    x = min(max(door_x - width / 2, 0.0), W - width)
    if kind == "shed" and pw == 1.0:
        x = 0.0  # "1.0": the full width of the house
    y = -depth
    risers = max(2, math.ceil(floor_z / 0.625))
    steps = [Steps(round((door_x - 3) * 2) / 2, 6.0, "S", risers=risers)]
    pitch = lay.get("porch_pitch", 8)
    col_kind = lay.get("columns", "square")
    roofs = []
    columns = []
    if kind == "canopy":
        width, depth = min(max(width, 10.0), W), min(depth, 5.0)
        x, y = min(max(door_x - width / 2, 0.0), W - width), -min(depth, 5.0)
        roofs.append(RoofMass("Porch", x, y, width, -y, kind="shed", pitch=0.25, overhang=0.75,
                              plate_z=floor_z + 8.5, low_side="S"))
    elif kind in ("gable", "portico", "shed"):
        # an even number of columns (an odd number of bays), and none in front of the door:
        # the door sits in a bay, centred where the porch is centred on it
        half_door = 3.5
        if abs((x + width / 2) - door_x) > 0.25 and kind != "shed":
            # pushed off-centre by the house's corner: narrow it to centre on the door instead
            room = 2 * min(door_x, W - door_x)
            if room >= 8.0:
                width = round(min(width, room) * 2) / 2
                x = door_x - width / 2
        n = max(1, round((width - 2) / 9.5))
        if n % 2 == 0:
            n = n + 1 if (width - 2) / (n + 1) >= 5.5 else n - 1
        columns = [(x + 1 + i * (width - 2) / n, y + 1) for i in range(n + 1)]
        if any(abs(cx - door_x) < half_door + 0.6 for cx, _ in columns):
            columns = [columns[0], columns[-1]]  # just the corners: the door stays clear
            if any(abs(cx - door_x) < half_door + 0.6 for cx, _ in columns):
                columns = []
        if kind == "shed":
            roofs.append(RoofMass("Porch", x, y, width, depth, kind="shed", pitch=pitch,
                                  overhang=1.0, plate_z=plate_z, low_side="S"))
        else:
            back = D / 2 if stories == 1 else 0.0
            hipped = style.get("roof", {}).get("kind") == "hip"
            roofs.append(RoofMass("Porch", x, y, width, depth + back, kind="hip" if hipped else "gable",
                                  ridge="x" if hipped else "y", pitch=min(pitch, 6) if hipped else pitch,
                                  overhang=1.25 if kind == "portico" else 1.5,
                                  plate_z=plate_z, gable_ends=() if hipped else ("S",)))
    porch = Porch(x, y, width, depth, floor_z=floor_z, columns=columns,
                  column=col_kind if columns else "none",
                  pier_height=3.0 if col_kind in ("tapered", "square") else 0.0, steps=steps)
    return porch, roofs


def drop_unplaced(levels) -> None:
    """Openings with no exterior wall under them (a wall taken by a chimney, a wing or a
    garage) leave the model, so the plans hold exactly what the elevations draw."""
    from ..views.scene import place_opening
    for lv in levels:
        lv.openings = [o for o in lv.openings if o.kind == "garage" or place_opening(lv, o) is not None]


def cover_gaps(levels, roofs: list) -> list:
    """A low roof over any part of a floor the main roofs miss (a bay or bump-out), so no
    room is ever open to the sky. Each gap gets a shed roof sloping away from the house."""
    from shapely.ops import unary_union
    from ..roof.analytic import eave_rect
    out = []
    cover = unary_union([eave_rect(m) for m in roofs]).buffer(0.05) if roofs else None
    for lv in levels:
        gap = lv.footprint if cover is None else lv.footprint.difference(cover)
        parts = getattr(gap, "geoms", [gap])
        for k, g in enumerate(parts):
            if g.area <= 1.0:
                continue
            x0, y0, x1, y1 = g.bounds
            fx0, fy0, fx1, fy1 = lv.footprint.bounds
            low = "S" if y0 <= fy0 + 0.1 else "N" if y1 >= fy1 - 0.1 else "W" if x0 <= fx0 + 0.1 else "E"
            out.append(RoofMass(f"Bay {k + 1}", x0, y0, x1 - x0, y1 - y0, kind="shed", pitch=3.0,
                                overhang=0.75, plate_z=lv.plate_z, low_side=low))
    return out


def match_peaks(main: RoofMass, others: list) -> None:
    """Gables that meet the main roof peak at exactly its height, or clearly lower (a stepped
    progression); never a near miss or a subordinate roof poking above the main ridge."""
    from ..roof.analytic import z_range
    top = z_range(main)[1]
    for r in others:
        if r is None or r.kind == "shed":
            continue
        hi = z_range(r)[1]
        rise = hi - r.plate_z
        if rise <= 0.1:
            continue
        if hi > top + 0.05 or top - hi < 2.5:
            target = top - r.plate_z
            if target > 0.5:
                r.pitch = round(r.pitch * target / rise, 3)


def make_roof(style: dict, W: float, D: float, plate_z: float, x0: float = 0.0) -> RoofMass:
    r = style.get("roof", {})
    # "front": the gable turns to the street (farmhouse, tudor, scandinavian)
    narrow = W <= (34.0 if plate_z > 15 else 30.0)  # a big street gable only suits a narrow front
    ridge = "y" if r.get("ridge") == "front" and r.get("kind", "gable") == "gable" and narrow \
        else ("x" if W >= D else "y")
    return RoofMass("Main", x0, 0, W, D, kind=r.get("kind", "gable"),
                    ridge=ridge, pitch=r.get("pitch", 6),
                    overhang=r.get("overhang", 1.5), plate_z=plate_z)


def make_chimney(living: Room, W: float, eave_z: float) -> Optional[Chimney]:
    """A fireplace box: a wide stone rectangle pushed 2' out of the wall, starting 3' off
    the ground and 10' tall (the flue vents through the roof, as modern houses do it)."""
    if abs(living.x) < 1e-6:
        side, x = "W", -2.0
    elif abs(living.x + living.w - W) < 1e-6:
        side, x = "E", W
    else:
        return None
    cy = living.y + living.h / 2
    wide = min(8.0, living.h - 4.0)
    top = min(13.0, eave_z - 0.5)
    return Chimney(x, cy - wide / 2, 2.0, wide, top_z=top, hearth_wall=side, flue=0.0,
                   base_z=max(1.0, top - 10.0))


def make_lot(lot_w: float, lot_d: float, W: float, D: float, porch_depth: float,
             chimney_side: Optional[str], street: str,
             yards: Optional[tuple[float, float, float]] = None) -> Lot:
    side, front, rear = 5.0, 25.0, 20.0
    if yards is not None:
        front, rear, side = yards
        return Lot(lot_w, lot_d, front=front, rear=rear, side=side,
                   house_x=round((side + max(lot_w - 2 * side - W, 0) / 2) * 2) / 2,
                   house_y=front, street=street)
    left_extra = 2.0 if chimney_side == "W" else 0.0
    right_extra = 2.0 if chimney_side == "E" else 0.0
    spare = lot_w - 2 * side - W - left_extra - right_extra
    # leave the wider side yard on the east for a drive
    hx = side + left_extra + max(spare, 0) * 0.3
    return Lot(lot_w, lot_d, front=front, rear=rear, side=side, house_x=round(hx * 2) / 2,
               house_y=front + porch_depth + 2.0, street=street)


def align_windows(levels: list[Level]) -> None:
    """Stack upper windows over the ones below: a window within 3' of one on the floor
    beneath slides over to line up with it, if it stays on its wall and clear of others."""
    from shapely.geometry import LineString as _L
    for upper_i in range(1, len(levels)):
        lower, upper = levels[upper_i - 1], levels[upper_i]
        ring = list(upper.footprint.exterior.coords)
        for o in upper.openings:
            if o.kind != "window":
                continue
            c = o.start + o.width / 2
            below = [p.start + p.width / 2 for p in lower.openings
                     if p.face == o.face and p.kind in ("window", "door")]
            if not below:
                continue
            target = min(below, key=lambda x: abs(x - c))
            if abs(target - c) < 0.1 or abs(target - c) > 3.0:
                continue
            start = target - o.width / 2
            # the window must stay on a wall edge of this face at its line
            on_wall = False
            for p, q in zip(ring, ring[1:]):
                horiz = abs(p[1] - q[1]) < 1e-6
                if o.face in "SN" and horiz:
                    lo, hi = sorted((p[0], q[0]))
                    if (o.line is None or abs(p[1] - o.line) < 0.6) and lo + 1.0 <= start and start + o.width <= hi - 1.0:
                        on_wall = True
                elif o.face in "EW" and not horiz:
                    lo, hi = sorted((p[1], q[1]))
                    if (o.line is None or abs(p[0] - o.line) < 0.6) and lo + 1.0 <= start and start + o.width <= hi - 1.0:
                        on_wall = True
            # and inside the same room, clear of its partitions
            host = None
            for r in upper.rooms:
                if o.face in "SN":
                    edge = r.y if o.face == "S" else r.y + r.h
                    if (o.line is None or abs(edge - o.line) < 0.6) and r.x <= c <= r.x + r.w:
                        host = (r.x, r.x + r.w)
                else:
                    edge = r.x if o.face == "W" else r.x + r.w
                    if (o.line is None or abs(edge - o.line) < 0.6) and r.y <= c <= r.y + r.h:
                        host = (r.y, r.y + r.h)
            if host is None or start < host[0] + 0.75 or start + o.width > host[1] - 0.75:
                continue
            clear = all(p is o or p.face != o.face or start + o.width + 0.5 <= p.start or
                        start >= p.start + p.width + 0.5 for p in upper.openings)
            if on_wall and clear:
                o.start = round(start * 4) / 4


def primary_biggest(levels: list[Level], footprints: Optional[list] = None) -> None:
    """Keep the primary the biggest bedroom. A bigger bedroom with its own ensuite simply
    becomes the primary suite (the two suites trade names); any other oversized bedroom gives
    a strip to a walk-in closet, or a study when the strip is wide, keeping its windows and
    its door to the hall."""
    beds = [(lv, r) for lv in levels for r in lv.rooms if r.kind == "bedroom" and not r.unit]
    prim = next(((lv, r) for lv, r in beds if r.name.startswith("Primary")), None)
    if prim is None:
        return
    plv, p = prim

    def touching(a: Room, rooms: list[Room]) -> list[Room]:
        return [r for r in rooms if r is not a and shared_edge(a, r) and
                shared_edge(a, r)[3] - shared_edge(a, r)[2] >= 2.5]

    for lv, x in sorted(beds, key=lambda t: -t[1].area):
        target = min(p.area - 6.0, p.area / 1.15)  # the primary clearly the best room
        if x is p or x.area <= target:
            continue
        num = x.name.split()[-1]
        ens = next((r for r in touching(x, lv.rooms) if r.kind == "bath" and r.name == f"Ensuite {num}"), None)
        if ens is not None and lv is plv and x.area > p.area - 6.0:
            pens = next((r for r in touching(p, lv.rooms) if r.kind == "bath" and
                         (r.name.startswith("Primary") or "Ensuite" in r.name)), None)
            pwic = [r for r in touching(p, lv.rooms) + (touching(pens, lv.rooms) if pens else [])
                    if r.kind == "closet" and "Walk-in" in r.name]
            xwic = [r for r in touching(x, lv.rooms) + touching(ens, lv.rooms)
                    if r.kind == "closet" and r.name.endswith(num)]
            x.name, p.name = p.name, x.name
            ens.name = "Primary Ensuite"
            if pens is not None:
                pens.name = f"Ensuite {num}"
            for r in xwic[:1]:
                r.name = "Walk-in Closet"
            for r in pwic[:1]:
                r.name = f"Walk-in {num}"
            p = x
            continue
        before = x.area
        _trim_bedroom(lv, x, target, levels.index(lv), touching)
        if x.area > p.area - 6.0:  # no well-proportioned cut: the old, looser one
            _trim_bedroom(lv, x, p.area - 6.0, levels.index(lv), touching, strict=False)
        if x.area > p.area and lv is plv and not any(
                r.kind in ("bath", "closet") and r.name.startswith(("Primary", "Walk-in Closet"))
                for r in touching(p, lv.rooms)):
            # a small house's "primary" has no suite of its own: the bigger room takes the name
            x.name, p.name = p.name, x.name
            p = x
        _ = before


def _trim_bedroom(lv: Level, x: Room, target: float, idx: int, touching, strict: bool = True) -> None:
    """Give one end of an oversized bedroom to a closet. The bedroom keeps its hall door, an
    outside wall for its window, and at least 10' each way."""
    links = [r for r in touching(x, lv.rooms) if r.kind in ("hall", "stair", "entry", "family")]
    if not links:
        return
    excess = x.area - target
    fp = lv.footprint.exterior
    num = x.name.split()[-1]

    def ok(rest: Room) -> bool:
        lo_min, ratio = (10.0, 1.8) if strict else (9.5, 2.0)
        if min(rest.w, rest.h) < lo_min or max(rest.w, rest.h) / min(rest.w, rest.h) > ratio:
            return False
        if not any(shared_edge(rest, l) and shared_edge(rest, l)[3] - shared_edge(rest, l)[2] >= 2.6
                   for l in links):
            return False
        edges = [((rest.x, rest.y), (rest.x + rest.w, rest.y)), ((rest.x, rest.y + rest.h), (rest.x + rest.w, rest.y + rest.h)),
                 ((rest.x, rest.y), (rest.x, rest.y + rest.h)), ((rest.x + rest.w, rest.y), (rest.x + rest.w, rest.y + rest.h))]
        from shapely.geometry import LineString as _L
        return any(_L(e).intersection(fp).length >= 3.0 for e in edges)

    best = None
    for side in ("S", "N", "W", "E"):
        span = x.w if side in "SN" else x.h
        t = max(2.0, round(excess / span * 2) / 2)
        if side == "S":
            strip, rest = Room("", "closet", x.x, x.y, x.w, t), Room(x.name, x.kind, x.x, x.y + t, x.w, x.h - t)
        elif side == "N":
            strip, rest = Room("", "closet", x.x, x.y + x.h - t, x.w, t), Room(x.name, x.kind, x.x, x.y, x.w, x.h - t)
        elif side == "W":
            strip, rest = Room("", "closet", x.x, x.y, t, x.h), Room(x.name, x.kind, x.x + t, x.y, x.w - t, x.h)
        else:
            strip, rest = Room("", "closet", x.x + x.w - t, x.y, t, x.h), Room(x.name, x.kind, x.x, x.y, x.w - t, x.h)
        if not ok(rest):
            continue
        def reach(c):  # can this closet still be opened from something other than the strip?
            others = [r for r in lv.rooms if r is not x and r is not c and r.kind != "closet"] + [rest]
            return any(shared_edge(c, r) and shared_edge(c, r)[3] - shared_edge(c, r)[2] >= 2.6 for r in others)
        walled = [r for r in lv.rooms if r.kind == "closet" and r is not x and shared_edge(strip, r)
                  and shared_edge(strip, r)[3] - shared_edge(strip, r)[2] > 0.5 and not reach(r)]
        if walled:
            # closets this cut would wall off join the new walk-in, if together they make a rectangle
            xs = [strip.x] + [r.x for r in walled]
            ys = [strip.y] + [r.y for r in walled]
            x1s = [strip.x + strip.w] + [r.x + r.w for r in walled]
            y1s = [strip.y + strip.h] + [r.y + r.h for r in walled]
            bx, by, bw, bh = min(xs), min(ys), max(x1s) - min(xs), max(y1s) - min(ys)
            if abs(bw * bh - strip.area - sum(r.area for r in walled)) > 0.01:
                continue
            strip = Room("", "closet", bx, by, bw, bh)
            strip.absorbs = walled
        # prefer a deep (walk-in) strip over a long thin one
        # prefer a deep (walk-in) strip over a long thin one
        score = (t < 4) * 10 + max(strip.w, strip.h) / t
        if best is None or score < best[0]:
            best = (score, strip, rest, t)
    if best is None:
        return
    _, strip, rest, t = best
    for r in getattr(strip, "absorbs", []):
        lv.rooms.remove(r)
    t = min(strip.w, strip.h)
    strip.name = f"Closet {num}" if t < 4 or max(strip.w, strip.h) / t > 3.5 else f"Walk-in {num}"
    strip.unit = x.unit
    x.x, x.y, x.w, x.h = rest.x, rest.y, rest.w, rest.h
    lv.rooms.append(strip)


def even_windows(levels: list[Level], face: str = "S") -> None:
    """One window size per floor on the street side: the most common width, height and sill
    for that floor's living-room and bedroom windows (bath and stair windows keep theirs).
    A facade reads as one composition when its windows match."""
    from collections import Counter
    for lv in levels:
        wins = [o for o in lv.openings if o.kind == "window" and o.face == face and o.height >= 3.5]
        if len(wins) < 2:
            continue
        w = Counter(o.width for o in wins).most_common(1)[0][0]
        h = Counter(o.height for o in wins).most_common(1)[0][0]
        sill = Counter(o.sill for o in wins).most_common(1)[0][0]
        for o in wins:
            c = o.start + o.width / 2
            o.width, o.height, o.sill = w, h, sill
            o.start = round((c - w / 2) * 4) / 4
        # two windows crowding each other across a partition read as a mistake: one window,
        # centred between them, keeps the rhythm
        wins.sort(key=lambda o: o.start)
        drop = set()
        for a, b2 in zip(wins, wins[1:]):
            if id(a) in drop or (a.line is not None and b2.line is not None and abs(a.line - b2.line) > 0.5):
                continue
            gap = b2.start - (a.start + a.width)
            if 0 <= gap < 2.5:
                c = (a.start + b2.start + b2.width) / 2
                a.start = round((c - a.width / 2) * 4) / 4
                drop.add(id(b2))
        lv.openings = [o for o in lv.openings if id(o) not in drop]


def absorb_closets(levels: list[Level]) -> None:
    """Oversized linen and leftover closets (an architect would never draw a 90 sq ft linen
    closet) give their floor to the room beside them: the neighbour grows straight through the
    closet across its own width, so both stay rectangles, and whatever is left of the closet
    stays only if it's still a usable closet. The neighbour may be a bath, a bedroom (never so
    much that it rivals the primary), a study or the laundry."""
    for lv in levels:
        for _ in range(6):
            if not _absorb_once(lv):
                break
        _join_orphans(lv)


def _join_orphans(lv: Level) -> None:
    """A closet walled in by other closets joins one of them (when the two make a rectangle)."""
    def edge(a, b):
        e = shared_edge(a, b)
        return e[3] - e[2] if e else 0.0
    for c in [r for r in lv.rooms if r.kind == "closet" and not r.unit]:
        if any(edge(c, o) >= 2.0 for o in lv.rooms if o is not c and o.kind != "closet"):
            continue
        for o in lv.rooms:
            if o is c or o.kind != "closet" or o.unit:
                continue
            x0, y0 = min(c.x, o.x), min(c.y, o.y)
            x1, y1 = max(c.x + c.w, o.x + o.w), max(c.y + c.h, o.y + o.h)
            if abs((x1 - x0) * (y1 - y0) - c.area - o.area) < 0.01 and edge(c, o) > 0:
                o.x, o.y, o.w, o.h = x0, y0, x1 - x0, y1 - y0
                lv.rooms.remove(c)
                break


def _shape_ok(r: Room) -> bool:
    """The room passes the P8 proportion rule as drawn."""
    from ..checks.planning import SHAPE
    lo, hi = sorted((r.w, r.h))
    if r.kind == "closet":
        return r.area < 24 or (lo >= 4.0 and hi / lo <= 3.5)
    rule = SHAPE.get(r.kind)
    if not rule:
        return True
    mn, mx, ar = rule
    if r.kind == "bath" and r.name.startswith("Primary"):
        mx = 14.0
    return lo >= mn - 1e-6 and not (mx and hi > mx + 1e-6) and not (ar and hi / max(lo, 0.1) > ar + 1e-6)


def _absorb_once(lv: Level) -> bool:
    prim = next((r for r in lv.rooms if r.name.startswith("Primary Bedroom")), None)
    for c in sorted([r for r in lv.rooms if r.kind == "closet" and not r.unit], key=lambda r: -r.area):
        linen = c.name.startswith("Linen")
        if not ((linen and c.area > 30) or (c.name == "Closet" and c.area > 60)):
            continue
        best = None
        for n in lv.rooms:
            if n is c or n.unit or n.kind not in ("bath", "bedroom", "office", "laundry"):
                continue
            e = shared_edge(c, n)
            if not e:
                continue
            axis, _line, lo, hi = e
            # n's whole side must lie on the shared wall; n then grows through the closet
            if axis == "y":   # vertical wall: n grows in x across its own height
                if abs(lo - n.y) > 0.05 or abs(hi - (n.y + n.h)) > 0.05:
                    continue
                grow = Room(n.name, n.kind, min(n.x, c.x), n.y, n.w + c.w, n.h)
                left = [Room(c.name, "closet", c.x, c.y, c.w, n.y - c.y),
                        Room(c.name, "closet", c.x, n.y + n.h, c.w, c.y + c.h - n.y - n.h)]
            else:
                if abs(lo - n.x) > 0.05 or abs(hi - (n.x + n.w)) > 0.05:
                    continue
                grow = Room(n.name, n.kind, n.x, min(n.y, c.y), n.w, n.h + c.h)
                left = [Room(c.name, "closet", c.x, c.y, n.x - c.x, c.h),
                        Room(c.name, "closet", n.x + n.w, c.y, c.x + c.w - n.x - n.w, c.h)]
            left = [r for r in left if r.w > 0.05 and r.h > 0.05]
            if any(min(r.w, r.h) < 2.5 or r.area < 10 for r in left):
                continue
            if not _shape_ok(grow) or not all(_shape_ok(r) for r in left):
                continue
            if n.kind == "bedroom" and n is not prim and prim is not None and grow.area > prim.area / 1.15:
                continue
            if n.kind == "bath" and grow.area > 140:
                continue
            if n.kind == "bath" and any(o is not n and o.kind in ("bath", "powder") and shared_edge(grow, o) and
                                        shared_edge(grow, o)[3] - shared_edge(grow, o)[2] > 2 for o in lv.rooms):
                continue  # never two bathrooms side by side
            lo_, hi_ = sorted((grow.w, grow.h))
            if n.kind in ("bedroom", "office", "bath") and hi_ / lo_ > (1.8 if n.kind != "bath" else 2.6):
                continue
            # the pieces left over must still open onto something
            def opens(r):
                return any(o is not c and o is not n and o.kind == "hall"
                           and shared_edge(r, o) and shared_edge(r, o)[3] - shared_edge(r, o)[2] >= 2.0
                           for o in lv.rooms) or (shared_edge(r, grow) and
                                                  shared_edge(r, grow)[3] - shared_edge(r, grow)[2] >= 2.0)
            if not all(opens(r) for r in left):
                continue
            rank = ({"bedroom": 0 if n is prim else 1, "bath": 2, "office": 3, "laundry": 4}[n.kind],
                    -c.area + sum(r.area for r in left))
            if best is None or rank < best[0]:
                best = (rank, n, grow, left)
        if best is None:
            continue
        _, n, grow, left = best
        n.x, n.y, n.w, n.h = grow.x, grow.y, grow.w, grow.h
        lv.rooms.remove(c)
        lv.rooms.extend(left)
        return True
    return False


def daylight(levels: list[Level]) -> None:
    """After the facades are tidied: every habitable room keeps a window, and a living or family
    room two (on a second wall when it has one). Side and rear walls first, so the composed
    street front stays as drawn."""
    from ..checks import _windows_in
    for lv in levels:
        if lv.footprint is None:
            continue
        W, D = lv.footprint.bounds[2], lv.footprint.bounds[3]
        use_footprint(lv.footprint)
        try:
            proto = next((o for o in lv.openings if o.kind == "window" and o.width >= 2.5), None)
            for r in lv.rooms:
                if r.kind not in ("bedroom", "living", "family", "dining", "kitchen", "office") or r.unit:
                    continue
                need = 2 if r.kind in ("living", "family") else 1
                have = [o for o in _windows_in(lv, r) if o.kind == "window"]
                if len(have) >= need:
                    continue
                ext = sides_on_exterior(r, W, D)
                lit = {o.face for o in have}
                faces = sorted(ext.items(), key=lambda kv: (kv[0] in lit, kv[0] == "S", -(kv[1][1] - kv[1][0])))
                for face, (a, b) in faces:
                    if len(have) >= need:
                        break
                    line = {"S": r.y, "N": r.y + r.h, "W": r.x, "E": r.x + r.w}[face]
                    busy = [(o.start - 0.75, o.start + o.width + 0.75) for o in lv.openings
                            if o.face == face and (o.line is None or abs(o.line - line) < 0.6)]
                    w = 3.0
                    span = int((b - a) / 2) + 1
                    offs = [0] + [s_ * d for d in range(1, span * 2) for s_ in (-0.5, 0.5)]
                    for st in [(a + b) / 2 - w / 2 + d for d in offs]:
                        st = round(st * 4) / 4
                        if st < a + 1.0 or st + w > b - 1.0:
                            continue
                        if any(not (st + w <= p or st >= q) for p, q in busy):
                            continue
                        o = Opening("window", face, st, w, proto.height if proto else 4.5,
                                    proto.sill if proto else 2.5, None,
                                    proto.operation if proto else "double-hung", line=line)
                        lv.openings.append(o)
                        if o in _windows_in(lv, r):
                            have.append(o)
                            busy.append((st - 0.75, st + w + 0.75))
                            if len(have) >= need:
                                break
                        else:
                            lv.openings.remove(o)
        finally:
            use_footprint(None)
