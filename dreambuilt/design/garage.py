"""An attached side garage for houses that aren't the front-garage estate: it goes against
the side wall where the mudroom, laundry or a hall is, so you walk in through the right room,
and steps back from the front so the house leads."""
from __future__ import annotations

from typing import Optional

from ..model import Room

DEPTH = 24.0
PRIORITY = {"mud": 0, "laundry": 1, "hall": 2, "entry": 3}


def width(cars: int) -> float:
    return {1: 13.0, 2: 23.0, 3: 33.0}.get(max(1, min(3, cars or 2)), 23.0)


RECESS = 2.0  # the garage door sits back from the house front, so the house leads


def built_in(rooms: list[Room], W: float, depth: float, cars: int, room_left: float,
             room_right: float, max_depth: float = 0.0) -> Optional[Room]:
    """A garage built into the house: the full depth of the house (so the floor above can run
    over it and one roof covers both), set back a little from the front, on the side where it
    opens into the mudroom, laundry, a hall or the entry."""
    gw = width(cars)
    best = None
    for side, x_line, spare in (("E", W, room_right), ("W", 0.0, room_left)):
        if spare < gw:
            continue
        for r in rooms:
            touches = abs((r.x + r.w if side == "E" else r.x) - x_line) < 1e-6
            if not touches or r.kind not in PRIORITY or r.h < 3.0 or r.y + r.h <= RECESS + 3:
                continue
            # deeper than standard (to max_depth) when that lets it open into a better room
            reach = max(depth, min(r.y + 5.0, r.y + r.h)) if max_depth else depth
            if max_depth and reach > max_depth + 1e-6:
                if r.y + 3.5 > max(depth, max_depth):
                    continue
                reach = max(depth, max_depth)
            key = (PRIORITY[r.kind], -r.h)
            if best is None or key < best[0]:
                best = (key, side, reach)
    if best is None:
        return None
    side, depth = best[1], best[2]
    name = f"{max(1, min(3, cars or 2))}-Car Garage"
    return Room(name, "garage", W if side == "E" else -gw, RECESS, gw, round(depth * 2) / 2 - RECESS)


def attach(rooms: list[Room], W: float, D: float, cars: int, room_left: float,
           room_right: float) -> Optional[Room]:
    """Place the garage against the best side (by the room it would open into); None when
    no side has a room a garage may open into, or there's no room on the lot."""
    gw = width(cars)
    best = None
    for side, x_line, spare in (("E", W, room_right), ("W", 0.0, room_left)):
        if spare < gw:
            continue
        for r in rooms:
            touches = abs((r.x + r.w if side == "E" else r.x) - x_line) < 1e-6
            if not touches or r.kind not in PRIORITY or r.h < 3.0:
                continue
            key = (PRIORITY[r.kind], -r.h)
            if best is None or key < best[0]:
                best = (key, side, r)
    if best is None:
        return None
    _, side, r = best
    # cover the room it opens into; sit back from the front when the house is deep enough
    cy = r.y + r.h / 2
    gy = max(min(cy - DEPTH / 2, D - DEPTH), min(4.0, D - DEPTH))
    if gy + 3.0 > r.y + r.h or gy + DEPTH - 3.0 < r.y:
        gy = r.y + r.h - DEPTH if r.y + r.h - DEPTH >= -8 else r.y
    gx = W if side == "E" else -gw
    name = f"{max(1, min(3, cars or 2))}-Car Garage"
    return Room(name, "garage", gx, round(gy * 2) / 2, gw, DEPTH)
