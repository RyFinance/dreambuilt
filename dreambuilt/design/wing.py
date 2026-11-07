"""Side wings of a two-storey house: real rooms over a built-in garage (bedrooms off the
upstairs hall, a bath behind), and a one-storey primary suite behind the garage when the
client wants the primary on the main floor."""
from __future__ import annotations

from typing import Optional

from ..model import Room
from .program import Spec

snap = lambda v: round(v * 2) / 2


def beds_over(gw: float) -> int:
    """How many bedrooms the floor over a garage this wide holds along its front."""
    return max(1, min(3, int(gw // 11.5)))


def _side_hall(rooms: list[Room], x_line: float) -> Optional[Room]:
    """The upstairs hall or landing that meets the wing's wall."""
    best = None
    for r in rooms:
        if r.kind not in ("hall",) or r.h > 6.5:
            continue
        if abs(r.x - x_line) < 1e-6 or abs(r.x + r.w - x_line) < 1e-6:
            if best is None or r.y < best.y:
                best = r
    return best


def over_depth(rooms: list[Room]) -> float:
    """How far back the rooms over the garage reach."""
    return max(r.y + r.h for r in rooms)


def over_garage(rooms: list[Room], gar: Room, beds: list[Spec], baths: list[Spec],
                W: float, primary: Optional[list[Spec]] = None) -> Optional[list[Room]]:
    """Rooms over the garage: the upstairs hall carries on across it, bedrooms in front (the
    street side, with the house's front windows), a bath and linen behind. None when the hall
    upstairs doesn't reach the garage side (the caller keeps a bonus room)."""
    east = gar.x >= W - 1e-6
    hall = _side_hall(rooms, W if east else 0.0)
    if hall is None or not (beds or primary):
        return None
    x0, gw = gar.x, gar.w
    hy, hh = hall.y, hall.h
    # rooms run back over the garage only as far as the bath band needs; a deep garage keeps a
    # one-storey roof behind them
    depth = min(gar.y + gar.h, hy + hh + 10.0)
    if hy < 10.0 or depth - hy - hh < 0:
        return None
    out = [Room("Hall", "hall", x0, hy, gw, hh)]
    if primary:
        # the primary suite over the garage: the bedroom on the street off the hall, the
        # walk-in and ensuite beside it on the outside wall
        side_w = snap(max(8.0, min(10.0, gw * 0.4)))
        bw = gw - side_w
        bx = x0 if east else x0 + side_w
        sx = x0 + bw if east else x0
        wd = snap(max(5.0, min(6.5, hy * 0.4)))
        out.append(Room(primary[0].name, "bedroom", bx, 0, bw, hy))
        if len(primary) > 2:
            out.append(Room(primary[2].name, "closet", sx, hy - wd, side_w, wd))
            out.append(Room(primary[1].name, "bath", sx, 0, side_w, hy - wd))
        else:
            out.append(Room(primary[1].name, "bath", sx, 0, side_w, hy))
        return out
    n = len(beds)
    if n == 1 and gw >= 20.0:
        # one guest suite: the bedroom on the street, its own bath and closet beside it
        bw = snap(min(16.0, gw * 0.55))
        rest = gw - bw
        bx = x0 if not east else x0 + rest
        sx = x0 + bw if not east else x0
        out.append(Room(beds[0].name, "bedroom", bx, 0, bw, hy))
        if baths:
            out.append(Room(baths[0].name + " Ensuite", "bath", sx, 0, rest, snap(hy * 0.6)))
            out.append(Room("Walk-in Closet", "closet", sx, snap(hy * 0.6), rest, hy - snap(hy * 0.6)))
        else:
            out.append(Room("Walk-in Closet", "closet", sx, 0, rest, hy))
        return out
    if n == 2 and baths and gw >= 26.0:
        # two bedrooms sharing a jack-and-jill bath between them, all on the street side; the
        # garage behind keeps a one-storey roof
        jw = snap(max(5.5, min(8.0, gw - 2 * 12.0)))
        bw = snap((gw - jw) / 2)
        out.append(Room(beds[0].name, "bedroom", x0, 0, bw, hy))
        out.append(Room(baths[0].name, "bath", x0 + bw, 0, jw, hy))
        out.append(Room(beds[1].name, "bedroom", x0 + bw + jw, 0, gw - bw - jw, hy))
        return out
    full = gar.y + gar.h - hy - hh  # how deep the garage runs behind the hall
    if n >= 2 and 10.5 <= full <= 17.0 and gw >= 20.0:
        # a deep garage: one bedroom goes behind the hall with the bath beside it, both out to
        # the garage's back wall (walls over walls, no storage filling the back)
        y = hy + hh
        out = [Room("Hall", "hall", x0, hy, gw, hh)]
        fw = snap(gw / (n - 1))
        for i, sp in enumerate(beds[:-1]):
            x = x0 + i * fw
            out.append(Room(sp.name, "bedroom", x, 0, (x0 + gw - x) if i == n - 2 else fw, hy))
        bath_w = snap(min(9.0, max(6.0, gw * 0.3))) if baths else 0.0
        bed_w = gw - bath_w
        if bed_w >= 10.5 and max(bed_w, full) / min(bed_w, full) <= 1.8:
            # the bath against the house, near the laundry and mudroom below (a short drain),
            # the bedroom on the outside corner (windows two ways)
            bed_x = x0 + bath_w if east else x0
            out.append(Room(beds[-1].name, "bedroom", bed_x, y, bed_w, full))
            if baths:
                bx = x0 if east else x0 + gw - bath_w
                bd = min(full, 9.5)
                out.append(Room(baths[0].name, "bath", bx, y, bath_w, bd))
                if full - bd > 0.4:
                    out.append(Room("Linen", "closet", bx, y + bd, bath_w, full - bd))
            return out
    bw = snap(gw / n)
    xs = [x0 + i * bw for i in range(n)]
    for i, (sp, x) in enumerate(zip(beds, xs)):
        w = (x0 + gw - x) if i == n - 1 else bw
        out.append(Room(sp.name, "bedroom", x, 0, w, hy))
    rd = depth - hy - hh
    if rd >= 5.0:
        y = hy + hh
        # bath in the middle of the rear band, linen and a laundry nook either side; never
        # two baths side by side
        cells = []
        for sp in baths[:1]:
            cells.append(Room(sp.name, "bath", 0, y, min(9.0, max(5.5, gw * 0.3)), rd))
        rest = gw - sum(c.w for c in cells)
        left = snap(rest / 2)
        x = x0
        names = ("Linen", "Storage")
        parts = [Room(names[0], "closet", 0, y, left, rd)] + cells + \
            [Room(names[1], "closet", 0, y, rest - left, rd)]
        if not east:
            parts.reverse()
        for p in parts:
            if p.w < 0.5:
                continue
            p.x = x
            x += p.w
            out.append(p)
    elif rd > 0.4:
        out.append(Room("Storage", "closet", x0, hy + hh, gw, rd))
    return out


def primary_behind(gar: Optional[Room], side_x: float, east: bool, y0: float, y1: float,
                   width: float, prog_primary: list[Spec]) -> list[Room]:
    """A one-storey primary suite at the back of the house on the garage side (behind the
    garage when there is one): the bedroom on the garden, the ensuite and walk-in beside it
    on the far side, the bedroom entered from the hall at the back of the stair strip."""
    d = y1 - y0
    bed = prog_primary[0]
    bath = prog_primary[1]
    wic = prog_primary[2] if len(prog_primary) > 2 else None
    # the bedroom against the house (its door on the hall), the walk-in and ensuite beyond it
    side_w = snap(max(8.0, min(11.0, width * 0.36)))
    bed_w = width - side_w
    x_house = side_x if east else side_x - width
    rooms = []
    if east:
        bx, sx = x_house, x_house + bed_w
    else:
        sx, bx = x_house, x_house + side_w
    rooms.append(Room(bed.name, "bedroom", bx, y0, bed_w, d))
    if wic is not None and d >= 12:
        wd = snap(max(5.0, min(7.0, d * 0.38)))
        rooms.append(Room(wic.name, "closet", sx, y0, side_w, wd))
        rooms.append(Room(bath.name, "bath", sx, y0 + wd, side_w, d - wd))
    else:
        rooms.append(Room(bath.name, "bath", sx, y0, side_w, d))
    return rooms
