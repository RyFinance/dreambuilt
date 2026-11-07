"""Editing a finished design precisely.

Titles: every room in a design gets a fixed, unique title ("Bedroom 3", "Closet 2") that
stays the same across versions, so an edit names exactly one thing.

Two kinds of edit:

- **brief edits** (resize, add, remove, move to front / back): the brief changes and the design
  is rebuilt with the *same genome*, so it stays the same house with one thing changed;
- **direct edits** (drag a wall, swap two rooms): the building model itself changes, then doors,
  fixtures and checks are redone; elevations follow because they're drawn from the same model.

`parse(text, house)` reads "make Bedroom 3 bigger", "swap the Office and the Dining",
"move the kitchen to the back", "remove Closet 2", "add an office". `strokes()` turns a drawing
on the plan into the same operations: circle = select, line across rooms = swap, X = remove,
a stroke along a wall = move that wall there.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from typing import Optional

from .model import House, Room

GROW, SHRINK = 1.25, 0.8
WORDS_BIG = r"bigger|larger|wider|longer|roomier|more spacious|huge|a lot bigger|much bigger"
WORDS_SMALL = r"smaller|narrower|tighter|more compact|tiny|a lot smaller|much smaller"
ADDABLE = {"office": "office", "study": "office", "den": "office", "pantry": "pantry", "mudroom": "mudroom",
           "mud room": "mudroom", "fireplace": "fireplace", "porch": "porch", "family room": "family room",
           "bedroom": "bedroom", "bathroom": "bath", "bath": "bath", "powder room": "powder", "garage": "garage",
           "basement": "basement", "balcony": "balcony"}


@dataclass
class Op:
    kind: str                 # resize | move | swap | remove | add | wall | keep
    target: str = ""          # a room title (or an addable thing for add)
    other: str = ""           # swap partner
    value: float = 0.0        # resize factor, or the wall's new line
    side: str = ""            # front | rear for move
    wall: tuple = ()          # (level index, axis, line, lo, hi) for a wall move

    def describe(self) -> str:
        return {"resize": lambda: f"{self.target} {'bigger' if self.value > 1 else 'smaller'}",
                "move": lambda: f"{self.target} to the {self.side}",
                "swap": lambda: f"swap {self.target} and {self.other}",
                "remove": lambda: f"remove {self.target}",
                "add": lambda: f"add {self.target}",
                "wall": lambda: f"move the wall to {self.value:g}'",
                "keep": lambda: f"keep {self.target}"}[self.kind]()


@dataclass
class Result:
    house: Optional[House]
    brief: object
    done: list[str] = field(default_factory=list)
    couldnt: list[str] = field(default_factory=list)


# -- titles --------------------------------------------------------------------------------

def assign_titles(h: House) -> House:
    """Unique, stable titles: a name used once keeps it; repeats are numbered in reading order
    (floor by floor, front to back, left to right)."""
    rooms = [(li, r) for li, lv in enumerate(h.all_levels) for r in lv.rooms if r.kind != "void"]
    counts: dict[str, int] = {}
    for _li, r in rooms:
        counts[r.name] = counts.get(r.name, 0) + 1
    seen: dict[str, int] = {}
    used = {r.name for _li, r in rooms if counts[r.name] == 1}
    for _li, r in sorted(rooms, key=lambda t: (t[0], -(t[1].y + t[1].h / 2), t[1].x)):
        if counts[r.name] == 1:
            r.title = r.name
            continue
        n = seen.get(r.name, 1)
        while f"{r.name} {n}" in used:
            n += 1
        r.title = f"{r.name} {n}"
        used.add(r.title)
        seen[r.name] = n + 1
    return h


def titles(h: House) -> list[str]:
    return [r.label for lv in h.all_levels for r in lv.rooms if r.kind != "void"]


def find(h: House, title: str):
    """(level index, room) for a title (exact, case-insensitive)."""
    t = title.lower().strip()
    for li, lv in enumerate(h.all_levels):
        for r in lv.rooms:
            if r.label.lower() == t:
                return li, r
    return None, None


ALIASES = {"master bedroom": "Primary Bedroom", "master": "Primary Bedroom", "primary": "Primary Bedroom",
           "main bedroom": "Primary Bedroom", "master bath": "Primary Bath", "ensuite": "Primary Bath",
           "study": "Office", "den": "Office", "living room": "Living", "great room": "Living",
           "family room": "Family Room", "dining room": "Dining", "garage": "Garage"}


def _match_titles(text: str, h: House) -> list[tuple[int, str]]:
    """Titles mentioned in the text, as (position, title), longest names first."""
    t = text.lower()
    names = sorted(set(titles(h)), key=len, reverse=True)
    hits, taken = [], []
    for name in names:
        for m in re.finditer(r"\b" + re.escape(name.lower()) + r"\b", t):
            if any(a <= m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            hits.append((m.start(), name))
    for alias, base in ALIASES.items():
        for m in re.finditer(r"\b" + re.escape(alias) + r"\b", t):
            if any(a <= m.start() < b for a, b in taken):
                continue
            cands = [n for n in names if n.lower().startswith(base.lower()) or base.lower() in n.lower()]
            if len(cands) >= 1:
                taken.append((m.start(), m.end()))
                hits.append((m.start(), sorted(cands, key=len)[0]))
    return sorted(hits)


def parse(text: str, h: House) -> list[Op]:
    """Edit operations from words, each aimed at a titled room. Clauses split on ',', ';',
    'and then', '.'; a clause with no titled room or known verb gives nothing."""
    ops: list[Op] = []
    for clause in re.split(r"[.;\n]|,(?!\d)|\band then\b|\band (?=(?:also |then )?(?:keep|make|move|swap|switch|remove|"
                           r"delete|add|put|lock|leave|give|drop|get rid)\b)", text):
        c = clause.strip().lower()
        if not c:
            continue
        hits = _match_titles(c, h)
        names = [n for _p, n in hits]
        if re.search(r"\bswap\b|\bswitch\b|\btrade places\b|\bexchange\b", c) and len(names) >= 2:
            ops.append(Op("swap", names[0], names[1]))
            continue
        if m := re.search(r"\b(?:add|put in|include|i want|give me)\s+(?:an?\s+|another\s+|one more\s+|a second\s+)?"
                          r"(" + "|".join(sorted(map(re.escape, ADDABLE), key=len, reverse=True)) + r")\b", c):
            if not names or m.start() < (hits[0][0] if hits else 1e9):
                ops.append(Op("add", ADDABLE[m.group(1)]))
                continue
        if not names:
            continue
        target = names[0]
        if re.search(r"\b(?:remove|delete|drop|get rid of|lose|no more|take out)\b", c):
            ops.append(Op("remove", target))
        elif re.search(r"\b(?:keep|lock|don'?t (?:touch|change)|leave)\b", c):
            ops.extend(Op("keep", n) for n in names)
        elif m := re.search(r"\b(?:to|at|toward|towards|facing|on)\s+the\s+(front|back|rear|street|garden|yard)\b", c):
            side = "front" if m.group(1) in ("front", "street") else "rear"
            ops.append(Op("move", target, side=side))
        elif m := re.search(r"(\d{1,3})\s*%\s*(bigger|larger|smaller)", c):
            f = int(m.group(1)) / 100
            ops.append(Op("resize", target, value=1 + f if m.group(2) != "smaller" else max(0.5, 1 - f)))
        elif re.search(WORDS_BIG, c):
            ops.append(Op("resize", target, value=1.5 if re.search(r"huge|a lot|much", c) else GROW))
        elif re.search(WORDS_SMALL, c):
            ops.append(Op("resize", target, value=0.65 if re.search(r"a lot|much|tiny", c) else SHRINK))
    return ops


# -- applying ------------------------------------------------------------------------------

def _brief_copy(b):
    nb = copy.deepcopy(b)
    for k in ("_stories_said", "_style_said"):
        if hasattr(b, k):
            setattr(nb, k, getattr(b, k))
    return nb


def apply(h: House, b, ops: list[Op]) -> Result:
    """Apply edits. Direct edits change this house; brief edits rebuild the same design (same
    genome) from the changed brief, then direct edits are replayed by title where they still fit."""
    from .design import BriefError, build
    res = Result(None, _brief_copy(b))
    brief_ops = [o for o in ops if o.kind in ("resize", "move", "remove", "add")]
    direct = [o for o in ops if o.kind in ("swap", "wall")]
    keep = {o.target for o in ops if o.kind == "keep"}
    nb = res.brief
    for o in brief_ops:
        why = _to_brief(nb, h, o)
        (res.couldnt if why else res.done).append(o.describe() + (f" ({why})" if why else ""))
    house = h
    if any(o.describe() in res.done for o in brief_ops):
        g = dict(h.genome or {})
        try:
            from . import custom_rules
            bb = _brief_copy(nb)
            custom_rules.apply(bb)
            house = build(bb, g.get("mirror", False), g.get("variant", False), genome=g)
            house.genome = g
            assign_titles(house)
            house.name = h.name
        except BriefError as e:
            res.couldnt += [f"rebuild failed: {e}"]
            house = h
    house = copy.deepcopy(house)
    for o in direct:
        if o.kind == "swap" and ({o.target, o.other} & keep):
            res.couldnt.append(o.describe() + " (one of them is kept as is)")
            continue
        why = swap(house, o.target, o.other) if o.kind == "swap" else move_wall(house, *o.wall, o.value, keep=keep)
        (res.couldnt if why else res.done).append(o.describe() + (f" ({why})" if why else ""))
    if keep:
        res.done += [f"kept {k}" for k in sorted(keep)]
    res.house = house
    return res


def _to_brief(b, h: House, o: Op) -> str:
    """Change the brief for one op; '' when done, else why not."""
    if o.kind == "resize":
        li, r = find(h, o.target)
        if r is None:
            return "no such room"
        key = r.name.lower()
        kind_key = {"Primary Bedroom": "primary", "Primary Bath": "primary_bath", "Walk-in Closet": "wic",
                    "Kitchen": "kitchen", "Living": "living", "Dining": "dining", "Family Room": "family",
                    "Office": "office", "Mudroom": "mud", "Pantry": "pantry", "Entry": "entry",
                    "Laundry": "laundry"}.get(r.name)
        k = kind_key or key
        # (the house keeps its size and footprint: the room takes or gives space to the rooms
        # in its own band, so everything else stays where it was)
        b.sizes = {**b.sizes, k: round(b.sizes.get(k, 1.0) * o.value, 2)}
        return ""
    if o.kind == "move":
        li, r = find(h, o.target)
        if r is None:
            return "no such room"
        k = {"bedroom": "primary" if r.name.startswith("Primary") else "", "kitchen": "kitchen",
             "living": "living", "family": "family", "dining": "dining", "office": "office"}.get(r.kind, "")
        if not k:
            return "only the kitchen, living, family, dining, office and primary can be placed front or back"
        b.places = sorted({p for p in b.places if not p.startswith(k + ":")} | {f"{k}:{o.side}"})
        return ""
    if o.kind == "remove":
        li, r = find(h, o.target)
        if r is None:
            return "no such room"
        if r.kind == "bedroom" and not r.name.startswith("Primary"):
            if b.beds <= 1:
                return "it's the only bedroom"
            b.beds -= 1
            return ""
        if r.kind == "bath" and not r.name.startswith("Primary"):
            b.baths = max(1.0, b.baths - 1)
            return ""
        if r.kind == "powder":
            b.baths = float(int(b.baths))
            return ""
        m = {"office": "office", "pantry": "pantry", "mud": "mudroom", "family": "family room",
             "garage": "garage"}.get(r.kind) or ("bonus room" if r.name.startswith("Bonus") else "")
        if m:
            b.must_haves = [x for x in b.must_haves if x != m]
            if m == "garage":
                b.garage, b.cars = "none", 0
                b.features = sorted(set(b.features) | {"no garage"})
            return ""
        return "that room comes with the layout (try making a neighbour bigger)"
    if o.kind == "add":
        what = o.target
        if what == "bedroom":
            b.beds = min(7, b.beds + 1)
            b.sqft += 180
        elif what == "bath":
            b.baths = min(8.0, b.baths + 1)
            b.sqft += 60
        elif what == "powder":
            b.baths = float(int(b.baths)) + 0.5
        elif what == "basement":
            b.basement = True
        elif what == "garage":
            b.garage = "auto" if b.garage == "none" else b.garage
            b.features = [f for f in b.features if f != "no garage"]
            b.must_haves = sorted(set(b.must_haves) | {"garage"})
        else:
            b.must_haves = sorted(set(b.must_haves) | {what})
        return ""
    return "unknown edit"


def _redo_details(h: House, li: int) -> None:
    """After a direct edit: doors, unplaceable openings and fixtures redone for that floor."""
    from .design import details
    lv = h.all_levels[li]
    details.use_footprint(lv.footprint)
    lv.doors = details.make_doors(lv.rooms)
    details.drop_unplaced([lv])
    W, D = lv.footprint.bounds[2], lv.footprint.bounds[3]
    upper = lv is not h.levels[0]
    lv.fixtures = details.make_fixtures(lv, W, D, upper=upper)
    details.use_footprint(None)


def swap(h: House, a: str, b: str) -> str:
    """Two rooms on the same floor trade places (each takes the other's name and use)."""
    la, ra = find(h, a)
    lb, rb = find(h, b)
    if ra is None or rb is None:
        return "no such room"
    if la != lb:
        return "they're on different floors"
    if "stair" in (ra.kind, rb.kind) or "garage" in (ra.kind, rb.kind):
        return "stairs and garages stay where they are"
    for (r, o) in ((ra, rb), (rb, ra)):
        lo = min(o.w, o.h)
        if r.kind in ("bedroom", "living", "kitchen", "dining", "family", "office") and lo < 8.5:
            return f"{r.label} wouldn't fit in {o.label}'s space"
    for f in ("name", "kind", "title"):
        va, vb = getattr(ra, f), getattr(rb, f)
        setattr(ra, f, vb)
        setattr(rb, f, va)
    _redo_details(h, la)
    return ""


def walls(h: House, li: int, min_len: float = 2.5) -> list[tuple[str, float, float, float]]:
    """Interior walls that can be dragged: (axis, line, lo, hi). axis 'x' = a wall running
    east-west (it moves in y), 'y' = running north-south (it moves in x)."""
    from .design.details import shared_edge
    lv = h.all_levels[li]
    rooms = [r for r in lv.rooms if r.kind not in ("void", "stair")]
    out = []
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            e = shared_edge(a, b)
            if e and e[3] - e[2] >= min_len:
                out.append(e)
    return out


MINIMUM = {"bedroom": 10.0, "living": 11.0, "kitchen": 9.0, "dining": 9.0, "family": 10.0, "office": 8.0,
           "bath": 5.0, "powder": 3.5, "laundry": 5.0, "closet": 2.5, "hall": 3.0, "mud": 5.0, "garage": 11.0,
           "stair": 99.0, "entry": 5.0}


def shift_wall(rooms: list[Room], axis: str, line: float, lo: float, hi: float, new: float,
               minimum: dict = MINIMUM, keep: set = frozenset()) -> str:
    """Move the wall at `line` (spanning lo..hi) to `new` in a list of rooms; '' when done."""
    delta = new - line
    moved = []
    for r in rooms:
        if r.kind == "void":
            continue
        s0, s1 = (r.y, r.y + r.h) if axis == "y" else (r.x, r.x + r.w)
        if min(s1, hi) - max(s0, lo) <= 0.05:
            continue
        if axis == "y":
            if abs(r.x + r.w - line) < 1e-6:
                moved.append((r, "w", r.w + delta))
            elif abs(r.x - line) < 1e-6:
                moved.append((r, "x", r.w - delta))
        else:
            if abs(r.y + r.h - line) < 1e-6:
                moved.append((r, "h", r.h + delta))
            elif abs(r.y - line) < 1e-6:
                moved.append((r, "y", r.h - delta))
    if not moved:
        return "no wall there"
    for r, how, size in moved:
        if r.label in keep:
            return f"{r.label} is kept as is"
        if r.kind == "stair":
            return "the stair can't change size"
        if size < minimum.get(r.kind, 3.0):
            return f"{r.label} would be too small"
    for r, how, size in moved:
        if how == "w":
            r.w = size
        elif how == "x":
            r.x, r.w = r.x + delta, size
        elif how == "h":
            r.h = size
        else:
            r.y, r.h = r.y + delta, size
    return ""


def widen_primary(rooms: list[Room], margin: float = 1.15) -> bool:
    """Make the primary bedroom clearly the best bedroom: slide one of its walls into a
    neighbouring bedroom or closet (never the stair, never past a room's minimum) until it's
    `margin` times the next biggest bedroom. True when it changed anything."""
    from .design.details import shared_edge
    prim = next((r for r in rooms if r.name.startswith("Primary Bedroom")), None)
    if prim is None:
        return False
    others = [r for r in rooms if r.kind == "bedroom" and r is not prim and not r.unit]
    if not others:
        return False
    changed = False
    for _ in range(3):
        top = max(r.area for r in others)
        if prim.area >= margin * top:
            break
        need = margin * top - prim.area + 1.0
        best = None
        for n in rooms:
            if n is prim or n.kind not in ("bedroom", "closet", "laundry", "office") or n.unit:
                continue
            e = shared_edge(prim, n)
            if not e:
                continue
            axis, line, lo, hi = e
            # only a wall the primary owns along its whole side moves cleanly
            side = prim.h if axis == "y" else prim.w
            if hi - lo < side - 0.05:
                continue
            room = (n.w if axis == "y" else n.h) - MINIMUM.get(n.kind, 3.0)
            step = min(math.ceil(need / side * 2) / 2, math.floor(room * 2) / 2)  # half-foot steps, rounded up
            if step < 0.5:
                continue
            into = 1 if (axis == "y" and n.x > prim.x) or (axis == "x" and n.y > prim.y) else -1
            if best is None or step > best[0]:
                best = (step, axis, line, lo, hi, into)
        if best is None:
            break
        step, axis, line, lo, hi, into = best
        if shift_wall(rooms, axis, line, lo, hi, line + into * step):
            break
        changed = True
    return changed


def move_wall(h: House, li: int, axis: str, line: float, lo: float, hi: float, new: float,
              keep: set = frozenset()) -> str:
    """Slide the interior wall at `line` (spanning lo..hi) to `new`. Rooms whose edge sits on
    it stretch or shrink; no room may drop under its minimum size, and outside walls stay."""
    lv = h.all_levels[li]
    delta = new - line
    if abs(delta) < 0.25:
        return "too small a move"
    minimum = {"bedroom": 9.0, "living": 11.0, "kitchen": 9.0, "dining": 9.0, "family": 10.0, "office": 8.0,
               "bath": 5.0, "powder": 3.5, "laundry": 5.0, "closet": 2.5, "hall": 3.0, "mud": 5.0, "garage": 11.0,
               "stair": 99.0, "entry": 5.0}
    x0, y0, x1, y1 = lv.footprint.bounds
    if axis == "y" and not (x0 + 0.1 < new < x1 - 0.1) or axis == "x" and not (y0 + 0.1 < new < y1 - 0.1):
        return "walls can't move past the outside walls"
    moved = []
    for r in lv.rooms:
        if r.kind == "void":
            continue
        s0, s1 = (r.y, r.y + r.h) if axis == "y" else (r.x, r.x + r.w)
        if min(s1, hi) - max(s0, lo) <= 0.05:
            continue
        if axis == "y":
            if abs(r.x + r.w - line) < 1e-6:
                moved.append((r, "w", r.w + delta))
            elif abs(r.x - line) < 1e-6:
                moved.append((r, "x", r.w - delta))
        else:
            if abs(r.y + r.h - line) < 1e-6:
                moved.append((r, "h", r.h + delta))
            elif abs(r.y - line) < 1e-6:
                moved.append((r, "y", r.h - delta))
    if not moved:
        return "no wall there"
    for r, how, size in moved:
        if r.label in keep:
            return f"{r.label} is kept as is"
        if size < minimum.get(r.kind, 3.0):
            return f"{r.label} would be too small"
        if r.kind == "stair":
            return "the stair can't change size"
    for r, how, size in moved:
        if how == "w":
            r.w = size
        elif how == "x":
            r.x, r.w = r.x + delta, size
        elif how == "h":
            r.h = size
        else:
            r.y, r.h = r.y + delta, size
    _redo_details(h, li)
    return ""


# -- drawing on the plan -------------------------------------------------------------------

def _room_at(h: House, li: int, x: float, y: float) -> Optional[Room]:
    for r in h.all_levels[li].rooms:
        if r.kind != "void" and r.x <= x <= r.x + r.w and r.y <= y <= r.y + r.h:
            return r
    return None


def strokes(h: House, li: int, paths: list[list[tuple[float, float]]]) -> tuple[list[Op], list[str]]:
    """A drawing on one floor (paths in plan feet) -> (operations, selected titles).

    - a loop (ends close together) selects the rooms it encircles
    - two crossing strokes over a room (an X) remove it
    - a stroke along a wall (within 4', nearly parallel) moves that wall to the stroke
    - a stroke from one room into another swaps them
    """
    ops: list[Op] = []
    selected: list[str] = []
    used = set()
    paths = [p for p in paths if len(p) >= 2]
    # X: two short strokes crossing inside the same room
    for i, a in enumerate(paths):
        for j in range(i + 1, len(paths)):
            b = paths[j]
            if i in used or j in used:
                continue
            from shapely.geometry import LineString
            la, lb = LineString(a), LineString(b)
            if la.length < 30 and lb.length < 30 and la.crosses(lb):
                p = la.intersection(lb)
                pt = p if p.geom_type == "Point" else p.centroid
                r = _room_at(h, li, pt.x, pt.y)
                ends = [a[0], a[-1], b[0], b[-1]]
                # (an X is two short strokes inside one room; a stroke ending there is a swap)
                if r is not None and all(_room_at(h, li, *q) is r for q in ends):
                    ops.append(Op("remove", r.label))
                    used |= {i, j}
    wl = walls(h, li)
    for i, p in enumerate(paths):
        if i in used:
            continue
        (sx, sy), (ex, ey) = p[0], p[-1]
        length = sum(math.dist(p[k], p[k + 1]) for k in range(len(p) - 1))
        span = math.dist(p[0], p[-1])
        if length > 6 and span < 0.25 * length:
            # a loop: the rooms whose centres it encloses (or the room it sits in)
            from shapely.geometry import Point, Polygon
            poly = Polygon(p).buffer(0)
            inside = [r.label for r in h.all_levels[li].rooms if r.kind != "void"
                      and poly.contains(Point(r.x + r.w / 2, r.y + r.h / 2))]
            if not inside:
                c = poly.centroid
                r = _room_at(h, li, c.x, c.y)
                inside = [r.label] if r else []
            selected += [t for t in inside if t not in selected]
            continue
        ra, rb = _room_at(h, li, sx, sy), _room_at(h, li, ex, ey)
        if ra is not None and rb is not None and ra is not rb and ra.kind != "hall" and rb.kind != "hall":
            ops.append(Op("swap", ra.label, rb.label))  # from one room into another: trade places
            continue
        dx, dy = ex - sx, ey - sy
        horiz = abs(dx) >= abs(dy)
        best = None
        for axis, line, lo, hi in wl:
            if axis == "x" and horiz:
                mid_y = sum(q[1] for q in p) / len(p)
                cover = min(max(sx, ex), hi) - max(min(sx, ex), lo)
                if cover > 0.5 * min(abs(dx), hi - lo) and abs(mid_y - line) <= 4.0 and abs(dy) < 0.3 * abs(dx):
                    d = abs(mid_y - line)
                    if best is None or d < best[0]:
                        best = (d, Op("wall", value=round(mid_y * 2) / 2, wall=(li, axis, line, lo, hi)))
            if axis == "y" and not horiz:
                mid_x = sum(q[0] for q in p) / len(p)
                cover = min(max(sy, ey), hi) - max(min(sy, ey), lo)
                if cover > 0.5 * min(abs(dy), hi - lo) and abs(mid_x - line) <= 4.0 and abs(dx) < 0.3 * abs(dy):
                    d = abs(mid_x - line)
                    if best is None or d < best[0]:
                        best = (d, Op("wall", value=round(mid_x * 2) / 2, wall=(li, axis, line, lo, hi)))
        if best is not None and best[0] > 0.3:
            ops.append(best[1])
    return ops, selected
