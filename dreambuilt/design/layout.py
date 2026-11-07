"""Parametric slicing-tree layouts.

A layout is a tree of cuts. A Group lays its children side by side along one
axis; a Leaf is a room. Extents are shared in proportion to target areas,
with minimum sizes respected and fixed-size pieces (halls, stairs) honoured,
then snapped to a 6" grid so rooms always tile the footprint exactly.

Templates (one-story and multi-story) build trees from a room program.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

from ..model import Room
from .program import Program, Spec

GRID = 0.5
HALL = 3.5
STAIR_W = 4.0
STAIR_L = 14.0
# the U stair the smaller plans use: up from the foyer, turn at the back landing, and arrive
# at the front again, right on the upstairs hall
STAIR_UW = 7.0  # two 3'-6" flights
STAIR_UL = 11.5  # 10' ceilings (11' floor to floor) at code rises and treads


@dataclass
class Leaf:
    spec: Spec
    fixed: Optional[float] = None  # fixed extent along the parent's axis


@dataclass
class Group:
    axis: str  # "x": children side by side east-west; "y": stacked south-north
    children: list["Node"] = field(default_factory=list)
    fixed: Optional[float] = None


Node = Union[Leaf, Group]


def area(n: Node) -> float:
    return n.spec.target if isinstance(n, Leaf) else sum(area(c) for c in n.children)


def min_along(n: Node, axis: str) -> float:
    if n.fixed is not None:
        return n.fixed
    if isinstance(n, Leaf):
        return n.spec.min_dim
    if n.axis == axis:
        return sum(min_along(c, axis) for c in n.children)
    return max(min_along(c, axis) for c in n.children)


def _shares(nodes: list[Node], length: float, axis: str) -> list[float]:
    """Split `length` among nodes: fixed first, then by area with minimums."""
    fixed = {i: n.fixed for i, n in enumerate(nodes) if n.fixed is not None}
    free = [i for i in range(len(nodes)) if i not in fixed]
    rest = length - sum(fixed.values())
    out = dict(fixed)
    pinned: dict[int, float] = {}
    while True:
        open_ = [i for i in free if i not in pinned]
        budget = rest - sum(pinned.values())
        tot = sum(area(nodes[i]) for i in open_) or 1.0
        trial = {i: budget * area(nodes[i]) / tot for i in open_}
        short = {i: min_along(nodes[i], axis) for i in open_ if trial[i] < min_along(nodes[i], axis)}
        if not short or len(short) == len(open_):
            out.update(trial)
            out.update(pinned)
            break
        pinned.update(short)
    return [out[i] for i in range(len(nodes))]


def _snap_cuts(start: float, sizes: list[float]) -> list[tuple[float, float]]:
    end = start + sum(sizes)
    cuts = [start]
    acc = start
    for s in sizes[:-1]:
        acc += s
        snapped = round(acc / GRID) * GRID
        snapped = max(snapped, cuts[-1] + GRID)
        cuts.append(snapped)
    cuts.append(end)
    if cuts[-1] - cuts[-2] < GRID:  # last piece squeezed by snapping
        cuts[-2] = cuts[-1] - GRID
    return list(zip(cuts, cuts[1:]))


def place(n: Node, x0: float, y0: float, x1: float, y1: float, out: list[Room]) -> None:
    if isinstance(n, Leaf):
        out.append(Room(n.spec.name, n.spec.kind, x0, y0, x1 - x0, y1 - y0))
        return
    if n.axis == "x":
        spans = _snap_cuts(x0, _shares(n.children, x1 - x0, "x"))
        for c, (a, b) in zip(n.children, spans):
            place(c, a, y0, b, y1, out)
    else:
        spans = _snap_cuts(y0, _shares(n.children, y1 - y0, "y"))
        for c, (a, b) in zip(n.children, spans):
            place(c, x0, a, x1, b, out)


def row(*nodes, fixed=None) -> Group:
    return Group("x", [n for n in nodes if n is not None], fixed)


def col(*nodes, fixed=None) -> Group:
    return Group("y", [n for n in nodes if n is not None], fixed)


def leaf(s: Optional[Spec], fixed=None) -> Optional[Leaf]:
    return Leaf(s, fixed) if s is not None else None


def _maybe(nodes):
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return None
    return nodes[0] if len(nodes) == 1 else None


def _band(nodes: list[Node], axis="x", fixed=None) -> Optional[Node]:
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return None
    if len(nodes) == 1 and fixed is None:
        return nodes[0]
    g = Group(axis, nodes, fixed)
    return g


def _by_kind(specs: list[Spec], kind: str) -> Optional[Spec]:
    return next((s for s in specs if s.kind == kind or s.name.lower().startswith(kind)), None)


SMALL = {"bath", "laundry", "closet", "powder"}


def _no_twin_baths(nodes: list[Node]) -> list[Node]:
    """Never two bathrooms side by side: bedrooms, laundry or a linen closet go between them.
    The primary suite ([its bath (+ walk-in), the primary bedroom]) stays together at the end."""
    is_bath = lambda n: isinstance(n, Leaf) and n.spec.kind in ("bath", "powder")
    tail = []
    if len(nodes) >= 2 and isinstance(nodes[-1], Leaf) and nodes[-1].spec.name.startswith("Primary"):
        tail = nodes[-2:]
    body = nodes[:len(nodes) - len(tail)]
    baths = [n for n in body if is_bath(n)]
    others = [n for n in body if not is_bath(n)]
    out = []
    for i, bt in enumerate(baths):
        out.append(bt)
        if i < len(baths) - 1:
            out.append(others.pop(0) if others else Leaf(Spec("Linen", "closet", 18, 3)))
    if tail and out and is_bath(out[-1]):
        roomy = [o for o in others if not (isinstance(o, Leaf) and o.spec.kind == "closet")]
        if roomy:
            others.remove(roomy[-1])
            out.append(roomy[-1])  # a real room between this bath and the primary's
        else:
            # a cupboard between two baths still reads as a row: the primary bedroom goes
            # between them, its bath beyond
            tail = tail[::-1]
    return others + out + tail


def _end_suite_floor(program, front, rear_beds, baths, laundry, W, D, ys, front_depth, mirror) -> list[Room]:
    """An upper floor with the primary suite across its whole far end, front to back (the
    hall stops at its door): the bedroom on the street and the corner, the walk-in and ensuite
    behind it. The rest of the floor is the usual bands, narrower by the suite."""
    pr = program.primary
    pw = round(max(14.0, min(18.0, W * 0.3)) * 2) / 2
    rest_w = W - pw
    rear = _no_twin_baths([Leaf(s) for s in rear_beds] + baths + laundry)
    if not rear:
        rear = [Leaf(Spec("Linen", "closet", 30, 3))]
    width = rest_w - STAIR_UW
    if len(front) > 1 and 11.0 * len(front) > rest_w:
        front, rear = front[:-1], [Leaf(front[-1])] + rear
    rooms = upper_floor(front, rear, rest_w, D, ys, front_depth, mirror, 2)
    bed_d = round(max(front_depth + HALL, min(D * 0.6, D - 9.0)) * 2) / 2
    suite = col(Leaf(pr[0], fixed=bed_d), row(Leaf(pr[1]), Leaf(pr[2])) if len(pr) > 2 else Leaf(pr[1]))
    srooms: list[Room] = []
    place(suite, 0, 0, pw, D, srooms)
    if mirror:
        for r in srooms:
            r.x += rest_w  # the stair is on the west when mirrored: the suite takes the east end
    else:
        for r in rooms:
            r.x += pw
    return rooms + srooms


def _stack_wet(rear: list[Node], place_upper, lower: list[Room]) -> list[Room]:
    """Lay the upper floor with its back-row rooms in the order that puts the most bathrooms
    over wet rooms below (kitchen, laundry, mudroom, baths), so drains drop straight down.
    Baths never end up side by side and the primary suite stays together."""
    import itertools
    from shapely.geometry import box
    wet = [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in lower
           if r.kind in ("kitchen", "laundry", "mud", "bath", "powder")]

    def is_bath(n):  # a bath, or the primary's stack (its bath with the walk-in)
        if isinstance(n, Leaf):
            return n.spec.kind in ("bath", "powder")
        return any(is_bath(c) for c in getattr(n, "children", []))
    # the primary suite (its stack and bedroom) moves as one unit
    units, i = [], 0
    while i < len(rear):
        n = rear[i]
        nxt = rear[i + 1] if i + 1 < len(rear) else None
        if nxt is not None and isinstance(nxt, Leaf) and nxt.spec.name.startswith("Primary Bedroom"):
            units.append((n, nxt))
            i += 2
        elif isinstance(n, Leaf) and n.spec.name.startswith("Primary Bedroom") and i + 1 < len(rear):
            units.append((n, rear[i + 1]))
            i += 2
        else:
            units.append((n,))
            i += 1

    def ok(rooms):
        from .details import shared_edge
        pb = next((r for r in rooms if r.name == "Primary Bath"), None)
        pr = next((r for r in rooms if r.name == "Primary Bedroom"), None)
        if pb and pr and not ((e := shared_edge(pb, pr)) and e[3] - e[2] >= 2.6):
            return False  # the ensuite must open off its bedroom
        return all(min(r.w, r.h) >= (9.0 if r.kind == "bedroom" else 4.5 if r.kind == "bath" else 2.0)
                   for r in rooms if r.kind in ("bedroom", "bath"))

    def score(rooms):
        good = 0
        for r in rooms:
            if r.kind in ("bath", "powder"):
                b = box(r.x, r.y, r.x + r.w, r.y + r.h)
                good += any(b.intersection(w).area > 6 or b.distance(w) < 3.0 for w in wet)
        return good

    best_rooms = place_upper(rear)
    best = score(best_rooms)
    total = sum(r.kind in ("bath", "powder") for r in best_rooms)
    if best >= total or len(units) > 7:
        return best_rooms
    for perm in itertools.islice(itertools.permutations(units), 400):
        order = [n for u in perm for n in u]
        if any(is_bath(a) and is_bath(b) for a, b in zip(order, order[1:])):
            continue
        if any(isinstance(a, Leaf) and a.spec.kind == "closet" and is_bath(b) and is_bath(c)
               for b, a, c in zip(order, order[1:], order[2:])):
            continue  # a cupboard between two baths still reads as a row
        rooms = place_upper(order)
        sc = score(rooms)
        if sc > best and ok(rooms):
            best, best_rooms = sc, rooms
            if best >= total:
                break
    return best_rooms


def _bath_by_stair(nodes: list[Node]) -> list[Node]:
    """The primary suite with its bath at the stair end of the back row: over the kitchen and
    the mudroom / laundry below, so its drain drops straight down a stack."""
    if len(nodes) >= 2 and isinstance(nodes[-1], Leaf) and nodes[-1].spec.name.startswith("Primary Bedroom"):
        stack = nodes[-2]
        before = nodes[-3] if len(nodes) >= 3 else None
        is_bath = lambda n: isinstance(n, Leaf) and n.spec.kind in ("bath", "powder")
        if not is_bath(before):
            return nodes[:-2] + [nodes[-1], stack]
    return nodes


def pack_small(nodes: list[Node], depth: float) -> list[Node]:
    """Stack neighbouring small rooms two-high when the band is deep enough.

    Only pairs where the back room can still get a legal door: a closet or laundry
    behind a bath would be stranded, so baths never stack behind each other.
    """
    if depth < 11 or True:  # stacking strands the back room; kept for later Jack-and-Jill work
        return nodes
    out: list[Node] = []
    i = 0
    while i < len(nodes):
        a = nodes[i]
        b = nodes[i + 1] if i + 1 < len(nodes) else None
        if (isinstance(a, Leaf) and isinstance(b, Leaf) and a.spec.kind in SMALL
                and b.spec.kind in SMALL and a.fixed is None and b.fixed is None):
            out.append(col(a, b))
            i += 2
        else:
            out.append(a)
            i += 1
    return out


def _split_beds(beds: list[Spec], width: float, rear_min: float = 0.0,
                depth: float = 0.0) -> tuple[list[Spec], list[Spec]]:
    """Front band takes bedrooms while they fit; the rest go to the rear band.

    A bedroom is never narrower than half its depth (no 10' x 20' corridors).
    """
    min_w = max(11.0, depth / 1.9)
    n_front = min(len(beds), max(1, int(width // min_w)))
    # don't leave the front band nearly empty while the rear band is overfull
    while n_front < len(beds) and rear_min + 10 * (len(beds) - n_front) > width:
        n_front += 1
    return beds[:n_front], beds[n_front:]


def _primary_nodes(program: Program, include_closet: bool = True) -> list[Node]:
    """[bath (+ closet stacked), primary bedroom], west to east."""
    pr = program.primary
    bed, bath = pr[0], pr[1]
    wic = pr[2] if len(pr) > 2 and include_closet else None
    stack = col(Leaf(bath), Leaf(wic)) if wic else Leaf(bath)
    return [stack, Leaf(bed)]


def one_story_narrow(program: Program, W: float, D: float, mirror: bool, stair: bool = False) -> list[Room]:
    """A one-storey on a narrow lot, front to back: living across the front, dining and
    kitchen behind it, then a hall down the middle with bedrooms, baths and the laundry off
    both sides, and the primary suite across the back where the hall ends."""
    pub = {s.kind: s for s in program.public}
    front = [Leaf(pub["living"])]
    if "office" in pub:
        front.insert(0, Leaf(pub["office"]))
    if "family" in pub:
        front.append(Leaf(pub["family"]))
    laundry = [Leaf(s) for s in program.service if s.kind in ("laundry", "pantry")]
    small = [s for s in program.service if s.kind == "powder"]
    if D < 52:
        # not deep enough for four bands: dining and kitchen share the front band beside the
        # living room (the laundry goes off the hall)
        front.append(col(Leaf(pub["dining"]), Leaf(pub["kitchen"])))
        kitchen_row = None
        small += [s for s in program.service if s.kind in ("laundry",)]
    else:
        kitchen_row = row(Leaf(pub["dining"]), Leaf(pub["kitchen"]), *laundry)
    beds = list(program.bedrooms)
    baths = list(program.baths)
    if stair:
        small.insert(0, Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW))
    # two columns either side of the hall, bedrooms and small rooms alternating so no two
    # bathrooms ever stack
    # bedrooms down one side (their outside wall stays free for windows), baths and the
    # laundry down the other, where a garage can meet the laundry
    west = beds[:2]
    east = beds[2:] + baths + small

    def column(items):
        nodes = _no_twin_baths([Leaf(x) for x in items]) if items else []
        if not nodes:
            return None
        return col(*nodes) if len(nodes) > 1 else nodes[0]

    side = round((W - HALL) / 2 * 2) / 2
    cw, ce = column(west), column(east)
    mid_parts = []
    if cw is not None:
        cw.fixed = side
        mid_parts.append(cw)
    mid_parts.append(Leaf(Spec("Hall", "hall", HALL * 20, HALL), fixed=HALL))
    if ce is not None:
        mid_parts.append(ce)
    mid = row(*mid_parts)
    pr = program.primary
    suite = row(Leaf(pr[0]), col(Leaf(pr[2]), Leaf(pr[1])) if len(pr) > 2 else Leaf(pr[1]))
    top = col(row(*front) if len(front) > 1 else front[0], kitchen_row, mid, suite)
    if mirror:
        _mirror(top)
    rooms: list[Room] = []
    place(top, 0, 0, W, D, rooms)
    return rooms


def one_story_compact(program: Program, W: float, D: float, mirror: bool, stair: bool = False) -> list[Room]:
    """A small one-storey on a narrow lot: living, dining and kitchen down one side, a hall
    down the middle, the bedrooms and bath down the other (the primary at the back)."""
    pub = {s.kind: s for s in program.public}
    west = col(Leaf(pub["living"]), Leaf(pub["dining"]), Leaf(pub["kitchen"]))
    east_specs = list(program.bedrooms) + list(program.baths) + \
        [s for s in program.service if s.kind in ("powder", "laundry", "mud")] + \
        [program.primary[1], program.primary[0]]
    if stair:
        east_specs.insert(0, Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW))
    nodes = _no_twin_baths([Leaf(x) for x in east_specs])
    ew = max(11.0, round((W - HALL) * 0.42 * 2) / 2)
    top = row(west, Leaf(Spec("Hall", "hall", HALL * D, HALL), fixed=HALL), col(*nodes, fixed=ew))
    if mirror:
        _mirror(top)
    rooms: list[Room] = []
    place(top, 0, 0, W, D, rooms)
    return rooms


def one_story(program: Program, W: float, D: float, mirror: bool, dining_front: bool,
              stair: bool = False) -> list[Room]:
    pub = {s.kind: s for s in program.public}
    hall = Spec("Hall", "hall", 0, HALL)
    # private zone: front band of bedrooms, hall, rear band of baths + primary suite
    private_area = sum(s.target for s in program.primary + program.bedrooms + program.baths)
    public_area = sum(s.target for s in program.public + program.service) + \
        (STAIR_UW * STAIR_UL if stair else 0)
    wp_guess = W * public_area / (public_area + private_area + HALL * W * 0.5)
    wv = W - wp_guess
    depth = (D - HALL) / 2
    baths = [Leaf(s) for s in program.baths]
    powder = next((s for s in program.service if s.kind == "powder"), None)
    if powder:
        baths.insert(0, Leaf(powder))
    if program.ensuite_each and program.bedrooms:
        # each bedroom with its own ensuite beside it, all facing one way (no bath meets a bath)
        ens = {x.name.split()[-1]: x for x in program.baths}
        units = [row(Leaf(bd), Leaf(ens[bd.name.split()[-1]])) if bd.name.split()[-1] in ens else Leaf(bd)
                 for bd in program.bedrooms]
        nf = max(1, min(len(units), int(wv // 16.5)))
        extra = [Leaf(powder)] if powder else []
        rear_list = units[nf:] + extra + ([Leaf(Spec("Linen", "closet", 18, 3))] if units[nf:] else []) + \
            _primary_nodes(program)
        front = _band(units[:nf])
        rear = _band(rear_list)
    else:
        rear_fixed = _no_twin_baths(pack_small(baths, depth) + _primary_nodes(program))
        rear_min = sum(min_along(n, "x") for n in rear_fixed)
        front_beds, rear_beds = _split_beds(program.bedrooms, wv, rear_min)
        front = _band([Leaf(s) for s in front_beds])
        rear = _band([Leaf(s) for s in rear_beds] + rear_fixed)
    hall.target = HALL * wv
    pub_depth = round((D / 2 + HALL / 2) * 2) / 2
    if front is None:  # one-bedroom: no front band, the hall runs along the front
        private = col(Leaf(hall, fixed=HALL), rear)
    else:
        # the hall sits inside the depth of the front living rooms, so it always opens onto them
        front.fixed = pub_depth - HALL
        private = col(front, Leaf(hall, fixed=HALL), rear)
    # public zone: living (+ dining) in front, kitchen + service in back
    service = [Leaf(s) for s in sorted(program.service, key=lambda s: s.kind == "mud")
               if s.kind != "powder"]
    service_stack = col(*service) if len(service) > 1 else (service[0] if service else None)
    if stair:
        # the stair down gets its own bay in the back row, opening onto the front rooms
        down = Leaf(Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW), fixed=STAIR_UW)
        service_stack = row(service_stack, down) if service_stack is not None else down
    fam = pub.get("family")
    office = leaf(pub.get("office"))
    if wp_guess > 1.9 * (D / 2) and not fam and wp_guess * D > 800:
        fam = Spec("Family Room", "family", 220, 12)
        dining_front = True
    if dining_front:
        front_pub = row(office, Leaf(pub["living"]), Leaf(pub["dining"]))  # office away from the hall
        rear_pub = row(leaf(fam), Leaf(pub["kitchen"]), service_stack)  # kitchen beside the service rooms
    else:
        front_pub = row(office, Leaf(pub["living"]), leaf(fam))
        if len(front_pub.children) == 1:
            front_pub = front_pub.children[0]
        rear_pub = row(Leaf(pub["dining"]), Leaf(pub["kitchen"]), service_stack)
    public = col(front_pub, rear_pub)
    front_pub.fixed = pub_depth
    top = row(public, private)
    if mirror:
        _mirror(top)
    rooms: list[Room] = []
    place(top, 0, 0, W, D, rooms)
    return rooms


def _service_back(svc: dict, depth: float) -> Node:
    """Laundry and mudroom behind the stair: stacked when deep, one shared room when shallow."""
    have = [k for k in ("laundry", "mud") if k in svc]
    if depth < 5:
        return Leaf(Spec("Coat", "closet", 20, 2))  # too shallow: the laundry went upstairs
    if len(have) == 2 and depth >= 12:
        return col(Leaf(svc["mud"]), Leaf(svc["laundry"]))  # the mudroom first, where a garage meets it
    if len(have) == 2:
        return Leaf(Spec("Mud & Laundry", "laundry", svc["laundry"].target + svc["mud"].target, 6))
    if have:
        return Leaf(svc[have[0]])
    return Leaf(Spec("Storage", "closet", 40, 3))


def stair_y(D: float, front_depth: float) -> float:
    """South end of the U stair: where its top flight arrives, just behind the upper hall."""
    ys = round((front_depth + HALL) / GRID) * GRID
    return max(6.0, min(ys, D - STAIR_UL - 2.5))


def lower_floor(program: Program, W: float, D: float, ys: float, mirror: bool,
                suite_hall: float = 0.0, dining_front: bool = False,
                suite_rear: float = 0.0, kitchen_rear: bool = False, living_rear: bool = False) -> list[Room]:
    if suite_rear:
        # the primary suite across the back of the main floor (no room beside the house for a
        # wing): bedroom on the stair side off a hall, ensuite and walk-in next to it, the
        # laundry beside the walk-in
        import dataclasses
        laundry = []  # (the laundry stays by the mudroom in the stair strip, off circulation)
        rest = program
        front = lower_floor(rest, W, D - suite_rear, ys, mirror, suite_hall=4.0, dining_front=dining_front,
                            kitchen_rear=kitchen_rear, living_rear=living_rear)
        pr = program.primary
        bed_w = max(13.0, min(17.0, round(W * 0.4 * 2) / 2))
        cells = [Leaf(laundry[0], fixed=8.0)] if laundry else []
        side_w = 10.0
        spare = W - bed_w - side_w - (8.0 if laundry else 0.0)
        if spare >= 10.0:
            # the rest of the back: a family room off the kitchen, on the garden
            fam = next((s for s in program.public if s.kind == "family"), None)
            if fam is None:
                cells.insert(0, Leaf(Spec("Family Room", "family", 220, 12)))
        cells.append(col(Leaf(pr[2]), Leaf(pr[1])) if len(pr) > 2 else Leaf(pr[1]))
        cells[-1].fixed = side_w
        cells.append(Leaf(pr[0], fixed=bed_w))
        suite = row(*cells)
        if mirror:
            _mirror(suite)
        rooms = list(front)
        place(suite, 0, D - suite_rear, W, D, rooms)
        return rooms
    pub = {s.kind: s for s in program.public}
    svc = {s.kind: s for s in program.service}
    stair = Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW)
    small = [Leaf(x) for x in program.service if x.kind == "powder"]
    if not small:
        small = [Leaf(Spec("Coat", "closet", 20, 3))]
    pub_extra: list[Leaf] = []
    strip_w = STRIP_W(W)
    if strip_w > STAIR_UW:  # a wide strip has a column beside the stair for the pantry too
        small += [Leaf(x) for x in program.service if x.name == "Pantry"]
    narrow_powder = strip_w <= STAIR_UW and any(x.kind == "powder" for x in program.service)
    back_node = _service_back(svc, D - ys - STAIR_UL - (4.5 if narrow_powder else 0.0))
    if strip_w <= STAIR_UW:
        # a narrow plan: the stair alone in the strip, the powder room behind it
        middle = Leaf(stair, fixed=STAIR_UL)
        if D - ys - STAIR_UL >= 9:
            back_node = col(*small, back_node)
        else:
            pass  # too shallow behind the stair for the powder room
    else:
        middle = row(col(*small) if len(small) > 1 else small[0], Leaf(stair, fixed=STAIR_UW),
                     fixed=STAIR_UL)
    if suite_hall:
        # a hall at the back of the strip leads to the main-floor primary wing beside it
        back_node = col(back_node, Leaf(Spec("Hall", "hall", strip_w * suite_hall, 3), fixed=suite_hall))
    strip = col(Leaf(pub["entry"], fixed=ys), middle, back_node, fixed=strip_w)
    # living goes last (east), right against the entry strip; office and family sit beyond it
    front = ([Leaf(pub["office"])] if "office" in pub else []) + [Leaf(pub["living"])]
    fam = pub.get("family")
    west_w = W - strip_w
    # the pantry tucks in front of the kitchen, off it, keeping the kitchen's back wall
    kitchen_node = col(*pub_extra, Leaf(pub["kitchen"])) if pub_extra else Leaf(pub["kitchen"])
    if D >= 36 and (fam or west_w < D * 0.8):
        # a deep plan: three rows, so no room turns into a corridor. Formal rooms in front, the
        # dining (or living) in the middle, the kitchen with the family room across the back
        fr = [Leaf(pub["office"])] if "office" in pub else []
        fr.append(Leaf(pub["dining" if dining_front else "living"]))
        mid = None
        if dining_front:
            mid = Leaf(pub["living"])
        elif fam:
            mid = Leaf(pub["dining"])
        elif west_w < 24:
            mid = Leaf(pub["dining"])  # too narrow for two side by side: one room per row
        else:
            fr.append(Leaf(pub["dining"]))  # living and dining side by side in front
        if fam:
            back = row(Leaf(fam), kitchen_node)
            if west_w < 27:
                # too narrow for the two side by side: the family room in front of the kitchen
                # (open to it), the kitchen across the back on the garden
                back = col(Leaf(fam), kitchen_node)
        elif west_w * D > 900 and west_w >= 24:
            # a deep house: a family room beside the kitchen (they open into each other)
            back = row(Leaf(Spec("Family Room", "family", 220, 12)), kitchen_node)
        else:
            back = kitchen_node
        if D >= 44 and not kitchen_rear and not dining_front and west_w >= 22 and "office" not in pub \
                and west_w < 30:
            # a very deep, narrow plan: living and dining side by side on the street (both get
            # front windows), the family room across the middle, the kitchen across the back
            # by the mudroom and laundry (never a living room against the laundry)
            fam_spec = fam or Spec("Family Room", "family", 220, 12)
            d1 = round(D * 0.36 * 2) / 2
            d3 = round(D * 0.31 * 2) / 2
            west = col(_fixed(row(Leaf(pub["living"]), Leaf(pub["dining"])), d1),
                       Leaf(fam_spec), _fixed(kitchen_node, d3))
            top = row(west, strip)
            if mirror:
                _mirror(top)
            rooms: list[Room] = []
            place(top, 0, 0, W, D, rooms)
            return rooms
        if D >= 44 and not kitchen_rear and not dining_front and west_w >= 22:
            # a very deep plan: living in front, dining and kitchen across the middle (the
            # kitchen by the mudroom), the family room across the back on the garden
            fr = [x for x in fr if x.spec.kind != "dining"]
            # (the kitchen on the outside wall for its window, dining between it and the hall)
            mid = row(kitchen_node, Leaf(pub["dining"]))
            back = Leaf(fam or Spec("Family Room", "family", 220, 12))
        front_row = row(*fr) if len(fr) > 1 else fr[0]
        west = col(front_row, mid, back) if mid else col(front_row, back)
        if living_rear and not kitchen_rear:
            # kitchen and dining to the street, the living room on the garden
            west = col(back, mid, front_row) if mid else col(back, front_row)
        top = row(west, strip)
        if mirror:
            _mirror(top)
        rooms: list[Room] = []
        place(top, 0, 0, W, D, rooms)
        return rooms
    if fam:
        front.insert(0, Leaf(fam))
    if len(front) == 1 and west_w > 1.9 * (D / 2) and west_w * D > 800:
        # wide house: dining joins the front row, a family room sits behind with the kitchen
        front.insert(0, Leaf(pub["dining"]))
        back_row = row(Leaf(Spec("Family Room", "family", 220, 12)), kitchen_node)
    else:
        back_row = row(Leaf(pub["dining"]), kitchen_node)
    # two rows: living (+ office) in front, dining and kitchen behind; kitchen next to the strip
    west = col(row(*front) if len(front) > 1 else front[0], back_row)
    if living_rear and not kitchen_rear:
        # the other way round: kitchen and dining to the street, the living room on the garden
        west = col(back_row, row(*front) if len(front) > 1 else front[0])
    top = row(west, strip)
    if mirror:
        _mirror(top)
    rooms: list[Room] = []
    place(top, 0, 0, W, D, rooms)
    return rooms


def lower_floor_centered(program: Program, W: float, D: float, ys: float) -> list[Room]:
    """Centre-hall plan: entry and stair in the middle, living one side, dining the other."""
    pub = {s.kind: s for s in program.public}
    svc = {s.kind: s for s in program.service}
    stair = Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW)
    small = [Leaf(x) for x in program.service if x.kind == "powder"] or \
        [Leaf(Spec("Coat", "closet", 20, 3))]
    middle = row(col(*small) if len(small) > 1 else small[0], Leaf(stair, fixed=STAIR_UW),
                 fixed=STAIR_UL)
    back_node = _service_back(svc, D - ys - STAIR_UL)
    if getattr(program, "_laundry_closet", False):
        back_node = Leaf(Spec("Laundry", "closet", 30, 2))
    sw = STRIP_W(W)
    strip = col(Leaf(pub["entry"], fixed=ys), middle, back_node, fixed=sw)
    west_back = Leaf(pub["office"]) if "office" in pub else \
        Leaf(pub.get("family") or Spec("Family Room", "family", 200, 11))
    side = round((W - sw) / 2 * 2) / 2
    west = col(Leaf(pub["living"]), west_back, fixed=side)
    east = col(Leaf(pub["dining"]), Leaf(pub["kitchen"]), fixed=W - sw - side)
    rooms: list[Room] = []
    place(row(west, strip, east), 0, 0, W, D, rooms)
    return rooms


def upper_floor_centered(front_specs: list[Spec], rear_nodes: list[Node], W: float, D: float,
                         ys: float, front_depth: float, n: int) -> list[Room]:
    """Upper floor with the stair strip in the middle and a wing either side."""
    side = round((W - STAIR_UW) / 2 * 2) / 2
    per_wing = max(1, int(side // 10.5))
    fronts = list(front_specs)
    rear = list(rear_nodes)
    # primary suite (last two nodes) stays together in the east rear
    east_rear, west_rear = rear[-2:], rear[:-2]
    as_node = lambda x: x if isinstance(x, (Leaf, Group)) else Leaf(x)  # (a bedroom + ensuite unit)
    if any(isinstance(x, Group) for x in fronts):
        per_wing = max(1, int(side // 15.0))  # a bedroom (10') and its ensuite (5')
    n_west = min(per_wing, (len(fronts) + 1) // 2)
    west_front = [as_node(s) for s in fronts[:n_west]]
    east_front = [as_node(s) for s in fronts[n_west:n_west + per_wing]]
    leftover = [as_node(s) for s in fronts[n_west + per_wing:]]
    has_bed = lambda n: (isinstance(n, Leaf) and n.spec.kind == "bedroom") or \
        (isinstance(n, Group) and any(isinstance(c, Leaf) and c.spec.kind == "bedroom" for c in n.children))
    if not leftover and len(west_front) > 1 and not any(has_bed(n) for n in west_rear) and \
            not any(isinstance(n, Group) for n in west_front):
        # move a bedroom behind the hall so the west rear isn't one huge bath
        leftover = [west_front.pop()]
    west_rear = leftover + west_rear
    if not west_rear:
        west_rear = [Leaf(Spec("Bonus Room" if n == 3 else "Sitting Room", "family", 150, 10))]
    if not east_front:
        east_front = [Leaf(Spec("Office" if n == 3 else "Bedroom Nook", "office", 120, 9))]

    def wing(front, back, label, width):
        f = _band(front)
        f.fixed = front_depth
        hall = Spec(f"Hall {label}", "hall", HALL * side, HALL)
        return col(f, Leaf(hall, fixed=HALL), _band(pack_small(back, D - front_depth - HALL)),
                   fixed=width)

    strip = _upper_strip(ys, front_depth, D, "Linen")
    rooms: list[Room] = []
    place(row(wing(west_front, west_rear, "W", side), strip,
              wing(east_front, east_rear, "E", W - STAIR_UW - side)), 0, 0, W, D, rooms)
    for r in rooms:
        if r.name.startswith("Hall "):
            r.name = "Hall"
    return rooms


def upper_floor(front_specs: list[Spec], rear_nodes: list[Node], W: float, D: float,
                ys: float, front_depth: float, mirror: bool, n: int) -> list[Room]:
    hall = Spec("Hall", "hall", HALL * (W - STAIR_UW), HALL)
    width = W - STAIR_UW
    if len(front_specs) == 1 and width > 24 and isinstance(front_specs[0], Spec):
        front_specs = front_specs + [Spec("Sitting Room" if n == 2 else "Bonus Room", "family",
                                          front_specs[0].target, 10)]
    # (a front item may already be a node: a bedroom with its own ensuite)
    front = _band([s if isinstance(s, (Leaf, Group)) else Leaf(s) for s in front_specs]) or \
        Leaf(Spec("Sitting Room", "family", 150, 10))
    front.fixed = front_depth
    rear = _band(pack_small(rear_nodes, D - front_depth - HALL)) or \
        Leaf(Spec("Bonus Room", "family", 200, 10))
    # the front rooms run the full width, over the foyer too; behind them the hall meets the
    # landing the U stair arrives on, and the rear rooms sit beside the stair
    front.fixed = None
    land = max(HALL, ys - front_depth)
    rear_strip = col(Leaf(Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW), fixed=STAIR_UL),
                     Leaf(Spec("Linen" if n == 2 else "Storage", "closet", 30, 3)), fixed=STAIR_UW)
    top = col(_fixed(front, ys - land),
              row(Leaf(hall), Leaf(Spec("Landing", "hall", STAIR_UW * land, HALL), fixed=STAIR_UW),
                  fixed=land),
              row(rear, rear_strip))
    if mirror:
        _mirror(top)
    rooms: list[Room] = []
    place(top, 0, 0, W, D, rooms)
    return rooms


def _fixed(node: Node, size: float) -> Node:
    node.fixed = size
    return node


def STRIP_W(W: float) -> float:
    """The entry strip: the U stair, plus a column for the powder room and coats beside it
    when the house is wide enough."""
    return 12.0 if W >= 36 else STAIR_UW


def _upper_strip(ys: float, front_depth: float, D: float, rear: str) -> Node:
    """Closet over the foyer, the landing the stair arrives on (in line with the hall), the
    stair, and storage behind it."""
    land = max(HALL, ys - front_depth)
    return col(Leaf(Spec("Closet", "closet", STAIR_UW * front_depth, 3), fixed=ys - land),
               Leaf(Spec("Landing", "hall", STAIR_UW * land, HALL), fixed=land),
               Leaf(Spec("Stair", "stair", STAIR_UW * STAIR_UL, STAIR_UW), fixed=STAIR_UL),
               Leaf(Spec(rear, "closet", 30, 3)), fixed=STAIR_UW)


def _mirror(n: Node) -> None:
    """Reverse every east-west row, flipping the plan left to right."""
    if isinstance(n, Group):
        if n.axis == "x":
            n.children.reverse()
        for c in n.children:
            _mirror(c)


def multi_story(program: Program, stories: int, W: float, D: float, mirror: bool,
                front_depth: float, centered: bool = False, D_main: Optional[float] = None,
                D_top: Optional[float] = None, primary_main: bool = False,
                dining_front: bool = False, primary_elsewhere: bool = False,
                primary_rear: float = 0.0, kitchen_rear: bool = False,
                living_rear: bool = False) -> list[list[Room]]:
    """Floors front-aligned: the main floor runs D_main deep (a one-storey section out the
    back), the floor above D, and a third floor D_top."""
    D_main = D_main or D
    D_top = D_top or D
    ys = stair_y(D, front_depth)
    if D_main - ys - STAIR_UL < 5 and any(s.kind == "laundry" for s in program.service):
        # a small plan has no room behind the stair: laundry upstairs, the mudroom becomes a
        # coat closet by the door
        import dataclasses
        if centered:
            # a centre hall: a stacked laundry closet stays at the back of the hall downstairs
            # (the wings upstairs are too narrow to give it room)
            program = dataclasses.replace(program, service=[s for s in program.service
                                                            if s.kind not in ("laundry", "mud")])
            program._laundry_closet = True
        else:
            program = dataclasses.replace(program, upstairs_laundry="closet",
                                          service=[s for s in program.service if s.kind not in ("laundry", "mud")])
    if stories == 2 and not primary_rear and not centered and not program.upstairs_laundry and \
            any(s.kind == "laundry" for s in program.service):
        # the band behind the upstairs hall would be mostly empty: the laundry moves up beside
        # the bedrooms (the mudroom stays by the garage door)
        width_up = W - STAIR_UW if centered else W
        f_beds, r_beds = _split_beds(list(program.bedrooms), width_up)
        rear_area = (W - STAIR_UW) * (D - front_depth - HALL)
        rear_need = sum(s.target for s in r_beds + program.baths) + \
            (0 if primary_main or primary_elsewhere else sum(s.target for s in program.primary))
        if rear_need < 0.5 * rear_area:
            import dataclasses
            program = dataclasses.replace(program, upstairs_laundry=True,
                                          service=[s for s in program.service if s.kind != "laundry"])
    if centered:
        floors = [lower_floor_centered(program, W, D_main, ys)]
        uf = lambda f, r, n: upper_floor_centered(f, r, W, D if n == 2 else D_top, ys, front_depth, n)
    else:
        floors = [lower_floor(program, W, D_main, ys, mirror,
                              suite_hall=5.0 if primary_main and not primary_rear else 0.0,
                              dining_front=dining_front, suite_rear=primary_rear,
                              kitchen_rear=kitchen_rear, living_rear=living_rear)]
        uf = lambda f, r, n: upper_floor(f, r, W, D if n == 2 else D_top, ys, front_depth, mirror, n)
    beds = list(program.bedrooms)
    baths = [Leaf(s) for s in program.baths]
    if program.upstairs_laundry == "closet":
        laundry = [Leaf(Spec("Laundry", "closet", 20, 3))]  # a stacked pair behind doors
    else:
        laundry = [Leaf(Spec("Laundry", "laundry", 50, 5.5))] if program.upstairs_laundry else []
    width = W - STAIR_UW if centered else W  # the front rooms run over the foyer too
    if stories == 2 and program.ensuite_each and beds:
        # every bedroom with its bath beside it, all facing the same way, so a bath always
        # meets the next bedroom (never another bath)
        ens = {s.name.split()[-1]: s for s in program.baths}
        units = [row(Leaf(bd), Leaf(ens[bd.name.split()[-1]])) if bd.name.split()[-1] in ens else Leaf(bd)
                 for bd in beds]
        nf = max(1, min(len(units), int(width // 16.5)))
        front, rear_units = units[:nf], units[nf:]
        spare = [Leaf(s) for s in program.baths if s.name.split()[-1] not in {b.name.split()[-1] for b in beds}]
        prim = [] if primary_main or primary_elsewhere else _primary_nodes(program)
        rear = rear_units + spare + laundry + ([Leaf(Spec("Linen", "closet", 18, 3))] if rear_units and prim else []) + prim
        floors.append(uf(front, rear, 2))
    elif stories == 2:
        front, rear_beds = _split_beds(beds, width)
        # baths are kept apart by real rooms, not a linen cupboard (a bath, a closet and a bath
        # still read as a row of bathrooms): bring a bedroom back from the front when needed
        # (when there aren't enough rooms behind the hall to keep them apart, a shared bath
        # moves to the front, between two bedrooms, where it gets a window)
        n_baths = len(baths) + (1 if not (primary_main or primary_elsewhere) else 0)
        baths = list(baths)
        front = list(front)
        rear_w = W - STAIR_UW
        prim_w = 0 if (primary_main or primary_elsewhere) else 18.0
        for _ in range(4):
            if len(rear_beds) + len(laundry) >= n_baths - 1:
                break
            used = 11.0 * len(rear_beds) + 6.0 * n_baths + prim_w
            if len(front) >= 3 and used + 11.0 <= rear_w:
                rear_beds.insert(0, front.pop())  # a bedroom between the baths at the back
            elif baths and len(front) >= 2 and 11.0 * len(front) + 6.0 <= width and \
                    not any(isinstance(f, Spec) and f.kind == "bath" for f in front):
                front.insert(len(front) // 2, baths.pop().spec)  # a bath between bedrooms in front
                n_baths -= 1
            else:
                break
        rear = _no_twin_baths([Leaf(s) for s in rear_beds] + baths + laundry +
                              ([] if primary_main or primary_elsewhere else _primary_nodes(program)))
        rear = _bath_by_stair(rear)
        end_suite = not centered and not (primary_main or primary_elsewhere) and W >= 40 and len(program.primary) >= 2
        if end_suite:
            floors.append(_end_suite_floor(program, front, rear_beds, baths, laundry, W, D, ys, front_depth, mirror))
        else:
            floors.append(_stack_wet(rear, lambda order: uf(front, order, 2), floors[0]))
    else:
        # second floor: secondary bedrooms and shared baths; third: primary suite + extras
        front, rear_beds = _split_beds(beds, width)
        rear = _no_twin_baths([Leaf(s) for s in rear_beds] + baths + laundry)
        if not rear_beds:
            # a band of only bathrooms stretches them; a study keeps them bathroom-sized
            rear.insert(len(rear) // 2, Leaf(Spec("Study", "office", 150, 10)))
        if not rear:
            rear = [Leaf(Spec("Bath", "bath", 50, 5))]
        floors.append(uf(front, rear, 2))
        top_front = program.extras[:1] or [Spec("Office", "office", 120, 9)]
        top_rear = [Leaf(s) for s in program.extras[1:]] + _primary_nodes(program)
        floors.append(uf(top_front, top_rear, 3))
    return floors


__all__ = ["Group", "Leaf", "multi_story", "one_story", "place", "GRID", "HALL", "STAIR_L",
           "STAIR_W", "stair_y", "_maybe"]
