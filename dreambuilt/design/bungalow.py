"""Split-bedroom bungalow: the primary suite on one side, the open living space in the
middle, the other bedrooms on the far side off their own hall.

    west (primary)          centre (public)                    east (bedrooms)
    office / bedroom 4      living | foyer (+ powder) | dining  bedroom 2 (over the hall end)
    ensuite + walk-in       --------------------------------    hall | bath, laundry
    primary bedroom         great room | kitchen (+ pantry)     bedroom 3

The primary is sized to be the biggest bedroom; every room has an outside wall.
"""
from __future__ import annotations

from typing import Optional

from ..brief import DesignBrief
from ..model import Room

HALL = 3.5
snap = lambda v: round(v * 2) / 2


def plan(b: DesignBrief, W: float, D: float, stair: bool = False,
         dining_front: bool = True) -> Optional[list[Room]]:
    n2 = b.beds - 1
    ew = 15.5
    pw = snap(max(13.5, min(18.0, W * 0.3)))
    cw = W - pw - ew
    if cw < 22 or D < 26 or n2 < 1:
        return None
    cx0, cx1 = pw, W - ew
    rooms: list[Room] = []
    # east: bedroom 2 across the front, bedroom 3 across the back, hall + bath between
    b2 = snap(min(13.0, max(11.0, D * 0.36)))
    b3 = b2
    mid = D - b2 - b3
    extra_east = n2 >= 3 and mid >= 8.0 + 10.5
    if mid < 8.0:
        return None
    rooms.append(Room("Bedroom 2", "bedroom", cx1, 0, ew, b2))
    if n2 >= 2:
        rooms.append(Room("Bedroom 3", "bedroom", cx1, D - b3, ew, b3))
        hall_end = D - b3
    else:
        hall_end = D
    rooms.append(Room("Hall", "hall", cx1, b2, HALL, hall_end - b2))
    rx = cx1 + HALL
    y = b2
    rooms.append(Room("Bath", "bath", rx, y, W - rx, 8.0))
    y += 8.0
    if extra_east:
        rooms.append(Room("Bedroom 4", "bedroom", rx, y, W - rx, hall_end - y))
        y = hall_end
    elif hall_end - y >= 5.0:
        rooms.append(Room("Laundry", "laundry", rx, y, W - rx, hall_end - y))
        y = hall_end
    elif hall_end - y > 0.4:
        rooms[-1].h += hall_end - y
    laundry_placed = any(r.kind == "laundry" for r in rooms)
    # west: the primary suite, an office or bedroom 4 in front when wanted
    front_room = None
    if n2 >= 3 and not extra_east:
        front_room = ("Bedroom 4", "bedroom")
    elif b.has("office"):
        front_room = ("Office", "office")
    biggest_other = max(r.area for r in rooms if r.kind == "bedroom")
    pd = snap(max(13.0, min(17.0, (biggest_other + 12) / pw)))
    ens = 9.0
    wf = D - pd - ens
    if front_room and wf >= 10.0:
        rooms.append(Room(front_room[0], front_room[1], 0, 0, pw, wf))
        y0 = wf
    else:
        if front_room:
            return None  # no room for the office / fourth bedroom: the other plans get it
        pd = D - ens
        y0 = 0.0
    split = snap(pw * 0.55)
    rooms.append(Room("Primary Ensuite", "bath", 0, y0, split, ens))
    rooms.append(Room("Walk-in Closet", "closet", split, y0, pw - split, ens))
    rooms.append(Room("Primary Bedroom", "bedroom", 0, y0 + ens, pw, D - y0 - ens))
    # centre: living and the foyer in front, the open dining / great room and kitchen behind
    fd = snap(max(12.0, min(16.0, D * 0.45), b2 + 4.0))  # the east hall opens onto the front rooms
    fw = 8.0
    sw = 7.0 if stair else 0.0  # the stair down opens off the foyer, beside it
    fx = cx1 - fw if dining_front else cx0
    sx = fx - sw if dining_front else fx + fw
    lx = cx0 if dining_front else cx0 + fw + sw
    if cw - fw - sw < 12:
        return None
    rooms.append(Room("Living", "living", lx, 0, cw - fw - sw, fd))
    if stair:
        rooms.append(Room("Stair", "stair", sx, 0, sw, fd))
    powder = b.baths - int(b.baths) >= 0.5
    if powder:
        rooms.append(Room("Foyer", "entry", fx, 0, fw, fd - 5.5))
        rooms.append(Room("Powder", "powder", fx, fd - 5.5, fw, 5.5))
    else:
        rooms.append(Room("Foyer", "entry", fx, 0, fw, fd))
    gw = snap(cw * 0.5)
    service = []
    if not laundry_placed:
        service.append(("Laundry", "laundry"))
    if b.has("mudroom"):
        service.append(("Mudroom", "mud"))
    if b.has("pantry"):
        service.append(("Pantry", "closet"))
    rooms.append(Room("Family & Dining" if cw < 30 else "Great Room", "family",
                      cx0, fd, gw, D - fd))
    if service:
        # the kitchen keeps the outside wall at the back; service rooms line up in front of it
        kx = cx0 + gw
        sd = 7.0
        rooms.append(Room("Kitchen", "kitchen", kx, fd + sd, cx1 - kx, D - fd - sd))
        widths = [7.0 if k == "stair" else None for _, k in service]
        free = (cx1 - kx) - sum(w for w in widths if w)
        n_free = sum(1 for w in widths if w is None)
        x = kx
        for i, ((name, kind), w) in enumerate(zip(service, widths)):
            ww = cx1 - x if i == len(service) - 1 else (w or snap(free / max(n_free, 1)))
            rooms.append(Room(name, kind, x, fd, ww, sd))
            x += ww
    else:
        rooms.append(Room("Kitchen", "kitchen", cx0 + gw, fd, cx1 - cx0 - gw, D - fd))
    return rooms


def mirror(rooms: list[Room], W: float) -> None:
    for r in rooms:
        r.x = W - r.x - r.w
