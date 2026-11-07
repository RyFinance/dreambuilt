"""Tiny and narrow infill lots (a townhouse on 18' x 20'): zero side setbacks, small front and
rear yards, a U stair against one side wall, the open living / kitchen / dining below, and a
bedroom with its bath on each floor above. Used when the lot is too small for the other plans,
so a fixed lot is never quietly enlarged."""
from __future__ import annotations

from typing import Optional

from ..brief import DesignBrief
from ..model import Room

import math

SW = 7.0      # the U stair: two 3'-6" flights
SL = 10.5     # the default run, for 10' floor to floor


def stair_length(floor_to_floor: float) -> float:
    """A U stair's length: half the code run (7 3/4" rises, 10" treads) plus its landing."""
    risers = math.ceil(floor_to_floor * 12 / 7.75)
    return round(((risers - 1) * 10 / 12 / 2 + 3.5 + 0.6) * 2) / 2


def setbacks(b: DesignBrief) -> tuple[float, float, float]:
    """(front, rear, side) for an infill lot: zero sides on a townhouse or a lot under 30' wide,
    a little front and rear."""
    side = 0.0 if ("townhouse" in b.features or b.lot_width < 30) else 4.0
    front = max(2.0, min(10.0, round(b.lot_depth * 0.1 * 2) / 2))
    rear = max(2.0, min(10.0, round(b.lot_depth * 0.1 * 2) / 2))
    return front, rear, side


def applies(b: DesignBrief) -> bool:
    f, r, s = setbacks(b)
    return b.lot_width - 2 * s < 26 or b.lot_depth - f - r < 26


def wants_garage(b: DesignBrief) -> bool:
    return b.garage != "none" and "no garage" not in b.features and (b.has("garage") or b.cars > 0)


def banded_depth(b: DesignBrief, W: float) -> float:
    """The depth a townhouse on a long lot needs: its size over its floors, at least deep
    enough for front rooms, the stair band and back rooms (a car in front when there's a
    garage)."""
    least = 42.0 if wants_garage(b) else 34.0
    return max(least, b.sqft / max(b.stories, 1) / W)


def footprint(b: DesignBrief) -> Optional[tuple[float, float]]:
    f, r, s = setbacks(b)
    W, D = b.lot_width - 2 * s, b.lot_depth - f - r
    if W < SW + 9.0 or D < SL + 5.0:
        return None
    if D >= 30.0 and W >= 16.0:
        # a long lot: only as deep as the house needs, not the whole lot
        D = min(D, banded_depth(b, W))
    return round(W * 2) / 2, round(D * 2) / 2


def plan_banded(b: DesignBrief, W: float, D: float, mirror: bool, ftf: float) -> list[list[Room]]:
    """A townhouse on a long narrow lot, every floor in three bands: rooms across the front,
    the stair band (stair on the side wall, a hall beside it, a bath or laundry beyond), rooms
    across the back. Three storeys stack like real townhouses: garage, entry and a den or
    guest room on the ground; living, kitchen and dining on the second; bedrooms on top."""
    sl = stair_length(ftf)
    garage = wants_garage(b) and W >= 15.0
    fd = 20.0 if garage else round((D - sl) / 2 * 2) / 2
    ry = fd + sl
    rd = D - ry
    hx = W - SW - 3.5          # the hall beside the stair
    sw_ = hx                   # small rooms west of the hall
    n = b.stories
    floors: list[list[Room]] = []

    def band(name_kind_list, y0, d):
        out, x = [], 0.0
        tot = sum(w for _, _, w in name_kind_list)
        for i, (name, kind, w) in enumerate(name_kind_list):
            ww = (W - x) if i == len(name_kind_list) - 1 else round(W * w / tot * 2) / 2
            out.append(Room(name, kind, x, y0, ww, d))
            x += ww
        return out

    def middle(small: list[tuple[str, str]], stair_name="Stair"):
        out = [Room("Hall", "hall", hx, fd, 3.5, sl), Room(stair_name, "stair", W - SW, fd, SW, sl)]
        if small and small[0][1] == "powder" and sw_ >= 9.0:
            # the powder room off the hall, closets filling the rest
            out += [Room("Powder", "powder", sw_ - 5.0, fd, 5.0, 6.0),
                    Room("Pantry", "closet", 0, fd, sw_ - 5.0, sl),
                    Room("Coat", "closet", sw_ - 5.0, fd + 6.0, 5.0, sl - 6.0)]
            return out
        if small and sw_ >= 4.0:
            h = round(sl / len(small) * 2) / 2
            y = fd
            for i, (name, kind) in enumerate(small):
                hh = (fd + sl - y) if i == len(small) - 1 else h
                out.append(Room(name, kind, 0, y, sw_, hh))
                y += hh
        elif sw_ > 0.4:
            out.append(Room("Closet", "closet", 0, fd, sw_, sl))
        return out

    beds_left = b.beds
    full = int(b.baths)
    powder = b.baths - full >= 0.5
    # ground floor
    g = []
    if garage:
        g += [Room("1-Car Garage", "garage", 0, 0, W - 6.0, fd), Room("Entry", "entry", W - 6.0, 0, 6.0, fd)]
    else:
        g += [Room("Den", "office", 0, 0, W - 6.0, fd), Room("Entry", "entry", W - 6.0, 0, 6.0, fd)]
    rear_ground = None
    if n >= 3:
        # the ground floor's back room: a guest bedroom when there are bedrooms to place, else
        # a family room or den on the yard
        if beds_left >= 3:
            rear_ground = ("Bedroom 3", "bedroom")
        else:
            rear_ground = ("Family Room", "family") if garage else ("Family Room", "family")
        small = [("Laundry", "laundry")]
        if rear_ground[1] == "bedroom" and full >= 3:
            small = [("Laundry", "laundry"), ("Bath 3", "bath")]
        g += middle(small)
        g += band([(rear_ground[0], rear_ground[1], 1)], ry, rd)
        floors.append(g)
        # second floor: the living floor
        f2 = band([("Living", "living", 1)], 0, fd)
        f2 += middle([("Powder", "powder"), ("Pantry", "closet")] if powder else [("Pantry", "closet")])
        f2 += band([("Kitchen & Dining", "kitchen", 1)], ry, rd)
        floors.append(f2)
    else:
        # two storeys: living behind the entry on the ground, bedrooms above
        if not garage:
            g = band([("Living", "living", 1)], 0, fd)
            g[0].w = W - 6.0
            g.append(Room("Entry", "entry", W - 6.0, 0, 6.0, fd))
        g += middle([("Powder", "powder"), ("Pantry", "closet")] if powder else [("Laundry", "laundry")])
        g += band([("Kitchen, Dining & Living" if garage else "Kitchen & Dining", "kitchen", 1)], ry, rd)
        floors.append(g)
    # bedroom floors: the primary across the front with its ensuite beside the stair, another
    # bedroom across the back sharing the hall bath
    placed = 1 if rear_ground and rear_ground[1] == "bedroom" else 0
    for i in range(len(floors), n):
        top = i == n - 1
        name = "Primary Bedroom" if not any(r.name == "Primary Bedroom" for fl in floors for r in fl) \
            else f"Bedroom {i + 1}"
        # the primary across the front, its walk-in and ensuite in a column on the stair side;
        # the shared bath (and the laundry) beside the stair, off the hall
        cw = 6.5 if W >= 18 else 5.5
        fr = [Room(name, "bedroom", 0, 0, W - cw, fd)]
        wd = round(min(7.0, fd * 0.4) * 2) / 2
        fr += [Room("Walk-in Closet", "closet", W - cw, 0, cw, wd),
               Room("Primary Ensuite" if name == "Primary Bedroom" else "Ensuite", "bath", W - cw, wd, cw, fd - wd)]
        small = ([("Laundry", "laundry")] if n < 3 else [("Linen", "closet")]) + [("Bath", "bath")]
        f = fr + middle(small)
        want_rear = b.beds - placed - 1 > 0
        # the back room keeps a closet on the stair side, so the primary stays the biggest
        f += [Room("Bedroom 2" if want_rear else "Office", "bedroom" if want_rear else "office", 0, ry, W - cw, rd),
              Room("Closet", "closet", W - cw, ry, cw, rd)]
        placed += 1 + (1 if want_rear else 0)
        floors.append(f)
    if mirror:
        for rooms in floors:
            for r in rooms:
                r.x = W - r.x - r.w
    return floors


def plan(b: DesignBrief, W: float, D: float, mirror: bool = False, ftf: float = 10.0) -> list[list[Room]]:
    """One list of rooms per storey."""
    if D >= 30.0 and W >= 16.0:
        return plan_banded(b, W, D, mirror, ftf)
    SL = stair_length(ftf)
    sx = W - SW               # the stair strip on the east
    fy = max(3.5, D - SL)     # entry / landing in front of the stair
    lw = sx                   # the rooms' width west of the stair
    floors = []
    ground = [Room("Entry", "entry", sx, 0, SW, fy), Room("Stair", "stair", sx, fy, SW, SL)]
    liv_d = round(max(7.0, D * 0.48) * 2) / 2
    if lw * D < 240 or liv_d < 11:
        # too small to divide: one open living, kitchen and dining room
        ground.append(Room("Living, Kitchen & Dining", "kitchen", 0, 0, lw, D))
    elif b.baths - int(b.baths) >= 0.5 or b.baths >= b.stories and lw >= 14:
        # a powder room tucked behind the living room, off the entry
        ground += [Room("Living", "living", 0, 0, lw, liv_d),
                   Room("Kitchen & Dining", "kitchen", 0, liv_d, lw - 5.0, D - liv_d),
                   Room("Powder", "powder", lw - 5.0, liv_d, 5.0, min(6.0, D - liv_d))]
        if D - liv_d > 6.0:
            ground.append(Room("Pantry", "closet", lw - 5.0, liv_d + 6.0, 5.0, D - liv_d - 6.0))
    else:
        ground += [Room("Living", "living", 0, 0, lw, liv_d),
                   Room("Kitchen & Dining", "kitchen", 0, liv_d, lw, D - liv_d)]
    floors.append(ground)
    for i in range(1, b.stories):
        up = [Room("Landing", "hall", sx, 0, SW, fy), Room("Stair", "stair", sx, fy, SW, SL)]
        bath_d = 6.0 if D - 6.0 >= 10 else 5.0
        if i == 1:
            up += [Room("Primary Bedroom", "bedroom", 0, 0, lw, D - bath_d),
                   Room("Primary Ensuite", "bath", 0, D - bath_d, lw, bath_d)]
        else:
            n = i + 1
            kind = ("bedroom", f"Bedroom {i}") if b.beds > i - 1 else ("office", "Office")
            up += [Room(kind[1], kind[0], 0, 0, lw, D - bath_d), Room("Bath" if i == 2 else f"Bath {n}", "bath", 0, D - bath_d, lw, bath_d)]
        floors.append(up)
    if mirror:
        for rooms in floors:
            for r in rooms:
                r.x = W - r.x - r.w
    return floors
