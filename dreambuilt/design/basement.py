"""Basement with rental suites (the Surrey "mortgage helper").

Plan (garage on the east, nothing under it):
    suite 1 (west)                 owner stair + mechanical       suite 2 (east, behind the garage)
    bedrooms / bath / kitchen &    under the main stair,          bedroom / bath / kitchen & living,
    living stacked front to back,  sealed off from both suites    stacked front to back
    a 3'6" hall along the party wall; each suite has its own door at the back, down an
    exterior stairwell. Every habitable room sits on an outside wall for its egress window.
"""
from __future__ import annotations

from ..model import Fixture, Level, Opening, Room
from . import details

CORRIDOR = 3.5
CEILING = 9.0


def _estate_owner(W: float, D: float, xc: float, front: float, features: list[str]) -> list[Room]:
    """An owner's basement under the estate plan (nothing under the garage). The stair comes
    down under the main stair and lands on the rec room behind it; what the brief asked for
    (theatre, gym, wet bar, wine room) lines the back; a guest bedroom and bath in front."""
    sx0 = xc - 4.0
    rooms = [Room("Stair", "stair", sx0, 0, 4.0, front)]
    # front, west of the stair: guest bedroom on the street wall, bath and mechanical beside it
    fw = sx0
    front_parts = [("Bedroom", "bedroom", 0.0)]
    if fw >= 12 + 8:
        front_parts.append(("Bath", "bath", 8.0))
    if fw >= 12 + 8 + 5:
        front_parts.append(("Mechanical", "closet", 5.0))
    rooms += _strip(front_parts, 0, sx0, 0, front, "x")
    # behind: the theatre full depth on the west (if asked), the rec room across the middle
    # where the stair lands, and the rest of the asks along the back wall, each off the rec room
    back = D - front
    lw = min(16.0, sx0) if "theatre" in features and min(16.0, sx0) >= 12 else 0.0
    if lw:
        rooms.append(Room("Theatre", "family", 0, front, lw, back))
    r1 = round(max(12.0, back * 0.5) * 2) / 2
    if back - r1 < 9:
        r1 = back
    rec_w = W - lw
    if rec_w > 2.2 * r1:
        # too long for one room: a flex room on the far side from where the stair lands
        fw_ = round((rec_w - 2.0 * r1) * 2) / 2
        if xc <= lw + rec_w - fw_:
            rooms.append(Room("Rec Room", "family", lw, front, rec_w - fw_, r1))
            rooms.append(Room("Flex Room", "family", W - fw_, front, fw_, r1))
        else:
            rooms.append(Room("Flex Room", "family", lw, front, fw_, r1))
            rooms.append(Room("Rec Room", "family", lw + fw_, front, rec_w - fw_, r1))
    else:
        rooms.append(Room("Rec Room", "family", lw, front, rec_w, r1))
    if r1 < back:
        row2 = []
        if not any(p[1] == "bath" for p in front_parts):
            row2.append(("Bath", "bath", 8.0))  # first, so it is never the one dropped
        if "theatre" in features and not lw:
            row2.append(("Theatre", "family", 15.0))
        if "gym" in features:
            row2.append(("Gym", "family", 12.0))
        if "wet bar" in features:
            row2.append(("Wet Bar", "kitchen", 9.0))
        if "wine room" in features:
            row2.append(("Wine Room", "closet", 6.0))
        if not any(p[0] in ("Gym", "Theatre") for p in row2):
            row2.append(("Games Room", "family", 13.0))
        row2.append(("Storage", "closet", 0.0))
        dropped = []
        while sum(p[2] for p in row2) > (W - lw) - 4 and len(row2) > 2:
            dropped.append(row2.pop(-2))
        rooms += _strip(row2, lw, W, front + r1, D, "x")
        # an asked-for room that didn't fit along the back takes the guest bedroom's place
        asked = [p for p in dropped if p[0] in ("Theatre", "Gym", "Wet Bar", "Wine Room")]
        if asked:
            bed = next((r for r in rooms if r.name == "Bedroom"), None)
            if bed is not None:
                bed.name, bed.kind = asked[0][0], asked[0][1]
    return _fulfil(rooms, features)


def plan(ex: dict, suites: list[int], features: list[str] = ()) -> list[Room]:
    """Basement rooms in the estate plan's (unmirrored) coordinates."""
    W, D, xc = ex["W"], ex["D"], ex["xc"]
    front = 16.0  # the garage sits over y < 16 on the east
    rooms: list[Room] = []
    if len(suites) == 2:
        xs = max(17.0, min(round(W * 0.45 * 2) / 2, xc - 4.0))
    else:
        xs = max(17.0, xc - 4.0)
    # owner zone: the stair under the main stair, mechanical beside it
    rooms.append(Room("Stair", "stair", xc - 4.0, 0, 4.0, front))
    if xc - 4.0 - xs >= 3.0:
        rooms.append(Room("Mechanical", "closet", xs, 0, xc - 4.0 - xs, front))
    if not suites:
        return _estate_owner(W, D, xc, front, features)
    if suites:
        rooms += _suite(1, suites[0], 0, xs, 0, D, corridor_side="E")
    if len(suites) == 2:
        rooms += _suite(2, suites[1], xs, W, front, D, corridor_side="W")
    else:
        # the owner's side behind the garage: the rec room where the stair lands, the asks
        # (theatre, gym, bar, wine) along the back wall off it
        back = D - front
        r1 = round(max(12.0, back * 0.5) * 2) / 2 if back >= 21 else back
        rooms.append(Room("Rec Room", "family", xs, front, W - xs, r1))
        if r1 < back:
            row2 = [("Bath", "bath", 8.0)]
            for feat, name, kind, _ in ASKED:
                if feat in features:
                    row2.append((name, kind, {"Theatre": 14.0, "Gym": 11.0, "Wet Bar": 8.0}.get(name, 6.0)))
            row2.append(("Storage", "closet", 0.0))
            while sum(p[2] for p in row2) > (W - xs) - 3 and len(row2) > 2:
                row2.pop(-2)
            rooms += _strip(row2, xs, W, front + r1, D, "x")
    return _fulfil(rooms, features)


def _suite(n: int, beds: int, x0: float, x1: float, y0: float, y1: float, corridor_side: str) -> list[Room]:
    unit = f"Suite {n}"
    depth = y1 - y0
    living = max(11.0, min(16.0, round(depth * 0.32 * 2) / 2))
    bath = 6.5
    beds = max(1, min(beds, int((depth - living - bath) // 10)))
    bed_h = (depth - living - bath) / beds
    if corridor_side == "E":
        cx, rx0, rx1 = x1 - CORRIDOR, x0, x1 - CORRIDOR
    else:
        cx, rx0, rx1 = x0, x0 + CORRIDOR, x1
    out = [Room(f"{unit} Hall", "hall", cx, y0, CORRIDOR, depth, unit)]
    y = y0
    for j in range(beds):
        h = round(bed_h * 2) / 2 if j < beds - 1 else (y1 - living - bath) - y
        out.append(Room(f"{unit} Bedroom {j + 1}" if beds > 1 else f"{unit} Bedroom", "bedroom", rx0, y, rx1 - rx0, h, unit))
        y += h
    # bath beside the hall, the suite's own laundry on the outside wall next to it
    bw = min(8.5, rx1 - rx0)
    if corridor_side == "E":
        lx0, lx1, bx0, bx1 = rx0, rx1 - bw, rx1 - bw, rx1
    else:
        bx0, bx1, lx0, lx1 = rx0, rx0 + bw, rx0 + bw, rx1
    out.append(Room(f"{unit} Bath", "bath", bx0, y, bx1 - bx0, bath, unit))
    if lx1 - lx0 >= 4.0:
        out.append(Room(f"{unit} Laundry", "laundry", lx0, y, lx1 - lx0, bath, unit))
    elif lx1 > lx0:
        out[-1].x, out[-1].w = rx0, rx1 - rx0
    y += bath
    out.append(Room(f"{unit} Kitchen & Living", "kitchen", rx0, y, rx1 - rx0, y1 - y, unit))
    return out


def openings(level: Level, W: float, D: float) -> list[Opening]:
    """High basement windows (egress-sized in bedrooms) and a back door for each suite."""
    ops: list[Opening] = []
    details.use_footprint(level.footprint)
    try:
        for r in level.rooms:
            ext = details.sides_on_exterior(r, W, D)
            if not ext:
                continue
            face = next((f for f in ("W", "E", "S", "N") if f in ext), None)
            a, b = ext[face]
            line = {"S": r.y, "N": r.y + r.h, "W": r.x, "E": r.x + r.w}[face]
            mid = (a + b) / 2
            if r.kind == "bedroom":
                ops.append(Opening("window", face, mid - 2.0, 4.0, 4.5, 3.5, None, "casement", line=line))
            elif r.kind == "kitchen":
                for off in (-3.75, 0.75):  # a pair: basements need every bit of daylight
                    if b - a >= 9:
                        ops.append(Opening("window", face, mid + off, 3.0, 4.0, 3.5, None, "casement", line=line))
                if b - a < 9:
                    ops.append(Opening("window", face, mid - 1.5, 3.0, 4.0, 3.5, None, "casement", line=line))
                if r.unit and "N" in ext:
                    na, nb = ext["N"]
                    ops.append(Opening("door", "N", nb - 4.0, 2.83, 6.83, 0.0, operation="swing",
                                       line=r.y + r.h))
            elif r.kind == "family":
                ops.append(Opening("window", face, mid - 1.5, 3.0, 3.5, 4.0, None, "casement", line=line))
            elif r.kind == "bath":
                ops.append(Opening("window", face, mid - 1.0, 2.0, 2.0, 5.5, None, "awning", line=line))
    finally:
        details.use_footprint(None)
    return ops


def stairwells(level: Level) -> list[Fixture]:
    """Exterior stairs down to each suite door, drawn on the basement plan."""
    out = []
    for op in level.openings:
        if op.kind == "door" and op.face == "N":
            out.append(Fixture("stair", op.start - 0.3, op.line + 0.6, 3.5, 9.0, "N"))
    return out


def build_level(rooms: list[Room], main_floor_z: float, W: float, D: float) -> Level:
    lv = Level("Basement", main_floor_z - CEILING - 1.0, CEILING, rooms=rooms)
    lv.rooms = details.split_long(lv.rooms)
    lv.doors = details.make_doors(lv.rooms)
    lv.openings = openings(lv, W, D)
    details.use_footprint(lv.footprint)
    lv.fixtures = details.make_fixtures(lv, W, D, upper=False) + stairwells(lv)
    details.use_footprint(None)
    return lv


def under(W: float, D: float, stair: Room, suites: list[int], features: list[str],
          guest: bool = True, seed: int = 0, area: float = 0.0) -> list[Room]:
    """area > 0: a small basement of about that size, centred on the stair (the rest of the
    house sits on fill)."""
    if area and not suites and area < W * D * 0.9:
        bw = min(W, max(stair.w + 14.0, round(area / D * 2) / 2))
        x0 = max(0.0, min(W - bw, stair.x + stair.w / 2 - bw / 2))
        st = Room(stair.name, stair.kind, stair.x - x0, stair.y, stair.w, stair.h)
        rooms = _under(bw, D, st, suites, features, guest, seed)
        for r in rooms:
            r.x += x0
        return rooms
    return _under(W, D, stair, suites, features, guest, seed)


def _under(W: float, D: float, stair: Room, suites: list[int], features: list[str],
           guest: bool = True, seed: int = 0) -> list[Room]:
    """A basement under any rectangular house. The U stair lands at its south end on the
    owner's rec room; rental suites take full-depth strips at the sides with their own halls
    and back doors; the owner keeps the middle."""
    sx0, sx1 = stair.x, stair.x + stair.w
    left, right = sx0, W - sx1
    rooms: list[Room] = []
    ox0, ox1 = 0.0, W
    n = 0
    order = sorted(("L", "R"), key=lambda s: -(left if s == "L" else right))
    if seed % 2 and min(left, right) >= 14:
        order.reverse()  # some briefs put the suite on the narrower side
    for side in order:
        if n >= len(suites):
            break
        width = left if side == "L" else right
        if width < 14:
            continue
        sw = min(width, max(14.0, round(W * 0.42 * 2) / 2))
        if side == "L":
            rooms += _suite(n + 1, suites[n], 0, sw, 0, D, corridor_side="E")
            ox0 = sw
        else:
            rooms += _suite(n + 1, suites[n], W - sw, W, 0, D, corridor_side="W")
            ox1 = W - sw
        n += 1
    rooms += _owner(ox0, ox1, D, stair, features, guest and not suites, seed)
    return _fulfil(rooms, features)


ASKED = [("theatre", "Theatre", "family", 160), ("gym", "Gym", "family", 110),
         ("wet bar", "Wet Bar", "kitchen", 60), ("wine room", "Wine Room", "closet", 20)]


def _fulfil(rooms: list[Room], features: list[str]) -> list[Room]:
    """Anything the brief asked for that the layout couldn't place takes over the best spare
    room: a flex or games room, then storage, then the guest bedroom."""
    have = {r.name for r in rooms}
    order = ("Flex Room", "Games Room", "Storage", "Linen", "Bedroom")
    for feat, name, kind, need in ASKED:
        if feat not in features or name in have:
            continue
        for spare in order:
            cands = [r for r in rooms if r.name == spare and not r.unit and r.area >= need
                     and min(r.w, r.h) >= (3 if kind == "closet" else 9)]
            if cands:
                r = max(cands, key=lambda r: r.area)
                r.name, r.kind = name, kind
                have.add(name)
                break
        else:
            if name == "Wet Bar":
                # no room to spare: the bar goes along a wall of the rec room
                rec = next((r for r in rooms if r.name == "Rec Room"), None)
                if rec is not None:
                    rec.name = "Rec Room & Wet Bar"
    return rooms


def _owner(x0: float, x1: float, D: float, stair: Room, features: list[str], guest: bool,
           seed: int = 0) -> list[Room]:
    """Front band: the rec room (theatre, guest bedroom) where the stair lands; back band:
    the stair, with bath, gym, bar and storage either side, each opening off the rec room."""
    sx0, sx1, sy = stair.x, stair.x + stair.w, stair.y
    out = [Room("Stair", "stair", sx0, sy, stair.w, stair.h)]
    if sy + stair.h < D - 2.5:
        out.append(Room("Mechanical", "closet", sx0, sy + stair.h, stair.w, D - sy - stair.h))
    else:
        out[0].h = D - sy
    # front band, west to east: guest bedroom | rec room (over the stair foot) | theatre
    # seeds: 0 bedroom west in front | 1 bedroom east in front | 2 bedroom at the back |
    #        3 theatre west, bedroom east
    flip = seed in (1, 3)
    bed_back = seed == 2 and guest
    front = []
    if guest and not bed_back and (x1 - sx1 if flip else sx0 - x0) >= 12:
        front.append(("Bedroom", "bedroom", 12.0))
    front.append(("Rec Room", "family", 0.0))
    if "theatre" in features and (sx0 - x0 if flip else x1 - sx1) >= 13:
        front.append(("Theatre", "family", 14.0))
    others = sum(p[2] for p in front)
    if (x1 - x0 - others) > 2.2 * sy:
        # too long for one room: a games / flex room shares the front
        front.append(("Flex Room", "family", round((x1 - x0 - others) * 0.4 * 2) / 2))
    if flip:
        front.reverse()
    out += _strip(front, x0, x1, 0, sy, "x")
    # back band either side of the stair
    # outermost first: storage under the guest bedroom, the bath beside the stair
    west = [("Storage", "closet", 0.0)] + ([("Gym", "family", 12.0)] if "gym" in features else []) + \
        [("Bath", "bath", 8.0)]
    east = ([("Wet Bar", "kitchen", 9.0)] if "wet bar" in features else []) + \
        ([("Wine Room", "closet", 6.0)] if "wine room" in features else []) + [("Storage", "closet", 0.0)]
    wide_west = False
    if bed_back:
        # the guest bedroom across the back on the wider side, opening off the rec room
        wide_west = sx0 - x0 >= x1 - sx1
        if wide_west:
            west = [("Bedroom", "bedroom", 0.0), ("Bath", "bath", 8.0)]
        else:
            east = [("Bath", "bath", 8.0), ("Bedroom", "bedroom", 0.0)]
    if D - sy > 21 and max(sx0 - x0, x1 - sx1) >= 16:
        # a deep basement: a hall runs back beside the stair on its wider side, the asked-for
        # rooms open off it one behind the other (bath nearest the rec room, the dark theatre
        # at the back)
        west_side = sx0 - x0 >= x1 - sx1
        stack = [("Bath", "bath", 8.5)]
        if bed_back:
            stack.append(("Bedroom", "bedroom", 12.0))
        if "gym" in features:
            stack.append(("Gym", "family", 12.0))
        if "wet bar" in features:
            stack.append(("Wet Bar", "kitchen", 8.0))
        if "wine room" in features:
            stack.append(("Wine Room", "closet", 7.0))
        if "theatre" in features and not any(p[0] == "Theatre" for p in front):
            stack.append(("Theatre", "family", 15.0))
        while sum(p[2] for p in stack) > D - sy - 4 and len(stack) > 1:
            stack.pop(1)
        stack.append(("Storage", "closet", 0.0))
        if west_side:
            hx, rx0, rx1 = sx0 - 3.5, x0, sx0 - 3.5
        else:
            hx, rx0, rx1 = sx1, sx1 + 3.5, x1
        out.append(Room("Hall", "hall", hx, sy, 3.5, D - sy))
        y = sy
        for i, (name, kind, d) in enumerate(stack):
            dd = (D - y) if i == len(stack) - 1 else d
            if dd > 0.4:
                out.append(Room(name, kind, rx0, y, rx1 - rx0, dd))
            y += dd
        ox0, ox1 = (sx1, x1) if west_side else (x0, sx0)
        if ox1 - ox0 > 0.5:
            out += _strip([("Storage", "closet", 0.0)], ox0, ox1, sy, D, "x")
        return out
    if sx0 - x0 < 8 + 3 and not (bed_back and wide_west):
        west, east = [("Storage", "closet", 0.0)], [("Bath", "bath", 8.0)] + east
    if flip:
        west, east = list(reversed(east)), list(reversed(west))
    if sx0 - x0 > 0.5:
        out += _strip(west, x0, sx0, sy, D, "x")
    if x1 - sx1 > 0.5:
        out += _strip(east, sx1, x1, sy, D, "x")
    return out


def _strip(parts, x0, x1, y0, y1, axis):
    """Rooms side by side across [x0, x1] (fixed widths; zeros share what's left)."""
    span = x1 - x0
    fixed = sum(p[2] for p in parts)
    while fixed > span - 3 and len(parts) > 1:  # drop extras that don't fit
        parts = [p for p in parts if p[2] == 0.0] + [p for p in parts if p[2]][:-1] \
            if any(p[2] for p in parts) else parts[:-1]
        fixed = sum(p[2] for p in parts)
    flex = [p for p in parts if p[2] == 0.0] or [parts[-1]]
    spare = max(0.0, span - fixed) / len(flex)
    out, x = [], x0
    for i, (name, kind, w) in enumerate(parts):
        ww = x1 - x if i == len(parts) - 1 else round((w or spare) * 2) / 2
        if ww > 0.4:
            out.append(Room(name, kind, x, y0, ww, y1 - y0))
        x += ww
    return out
