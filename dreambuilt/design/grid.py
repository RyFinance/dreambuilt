"""Grid plan for two-storey houses: three columns, the stair core in the middle.

The organising idea of a well-made family house (the hand-drawn "Halcyon"): one grid on both
floors, the stair stacked in the middle column, a short hall at its head, every room on a
corner or an outside wall.

    main floor   front:  office / living  |  foyer  |  dining
                 core:                       hall + stair
                 rear:   great room       |  nook   |  kitchen  | service (mud, laundry, powder)

    upper floor  front:  bedroom + closet |  bedroom or bath over the foyer |  closet + bedroom
                 hall:   a short landing at the head of the stair
                 rear:   primary suite    |  room behind the stair |  bedroom + ensuite over the kitchen

Rooms are explicit rectangles on the grid (feet; y = 0 at the street). The engine's doors,
windows, checks and drawings take over from here.
"""
from __future__ import annotations

from typing import Optional

from ..model import Room
from .layout import HALL, STAIR_UL, STAIR_UW
from .program import Program

snap = lambda v: round(v * 2) / 2
CORE = STAIR_UW + 4.0  # the stair plus the hall beside it


def fits(W: float, D: float, prog: Program) -> bool:
    return W >= 37.0 and D >= 30.0 and len(prog.bedrooms) <= 5


def plan(prog: Program, W: float, D: float, mirror: bool = False,
         upstairs_laundry: bool = False) -> Optional[list[list[Room]]]:
    if not fits(W, D, prog):
        return None
    wa = snap((W - CORE) * 0.54)  # the primary's column a little wider
    wc = W - CORE - wa
    xb, xc = wa, wa + CORE             # the core column starts at xb, column C at xc
    fd = snap(max(12.0, min(16.0, D * 0.38)))  # main-floor front band
    fu = fd - HALL                     # upper front band (the landing sits in front of the stair)
    sy0, sy1 = fd, fd + STAIR_UL       # the stair
    if D - sy1 < 8.0 or wa < 13.0 or wc < 13.0:
        return None
    pub = {s.kind: s for s in prog.public}
    svc = {s.kind: s for s in prog.service}

    # -- main floor ---------------------------------------------------------------------
    # the kitchen sits in column A under the primary's bath, dining in front of it; the great
    # room across column C; the service rooms behind the stair under the upstairs baths (or down
    # column A's outer wall, where a garage can meet the mudroom, on a wide house)
    main: list[Room] = []
    front_c = "Office" if "office" in pub else "Living"
    great = "Family Room" if ("family" in pub and front_c == "Living") else "Great Room"
    main.append(Room("Dining", "dining", 0, 0, wa, fd))
    main.append(Room("Entry", "entry", xb, 0, CORE, fd))
    main.append(Room(front_c, "office" if front_c == "Office" else "living", xc, 0, wc, fd))
    main.append(Room("Hall", "hall", xb, sy0, 4.0, STAIR_UL))
    main.append(Room("Stair", "stair", xb + 4.0, sy0, STAIR_UW, STAIR_UL))
    main.append(Room(great, "living" if great == "Great Room" else "family", xc, fd, wc, D - fd))
    # the service rooms run down column A's outer wall (where a garage can meet the mudroom);
    # the nook behind the stair joins the kitchen to the great room, the hall opens onto it
    sw = 8.0 if wa >= 22 else (7.0 if wa >= 19 else 0.0)
    if not sw:
        return None
    main.append(Room("Kitchen", "kitchen", sw, fd, wa - sw, D - fd))
    items = [(n, k) for n, k, want in (("Mudroom", "mud", True),
                                       ("Laundry", "laundry", "laundry" in svc and not upstairs_laundry),
                                       ("Pantry", "closet", "pantry" in svc),
                                       ("Powder", "powder", "powder" in svc)) if want]
    while items and (D - fd) / len(items) < 5.5:
        items.pop(2 if len(items) > 3 else -1)
    h = snap((D - fd) / len(items))
    y = fd
    for i, (name, kind) in enumerate(items):
        hh = (D - y) if i == len(items) - 1 else h
        main.append(Room(name, kind, 0, y, sw, hh))
        y += hh
    main.append(Room("Nook", "dining", xb, sy1, CORE, D - sy1))

    # -- upper floor --------------------------------------------------------------------
    up: list[Room] = []
    beds = list(prog.bedrooms)
    baths = list(prog.baths)
    pr = prog.primary
    ha, hb = xb - 4.0, xc + 4.0       # a short hall: just past each column's edge
    up.append(Room("Hall", "hall", ha, fu, hb - ha, HALL))
    up.append(Room("Hall", "hall", xb, sy0, 4.0, STAIR_UL))
    up.append(Room("Stair", "stair", xb + 4.0, sy0, STAIR_UW, STAIR_UL))
    # the primary suite in the back corner of column A: bedroom off the hall, bath and walk-in
    # along the back wall
    rear_d = D - fd
    bed_d = snap(max(12.0, min(16.0, rear_d - 8.0)))
    up.append(Room(pr[0].name, "bedroom", 0, fd, wa, bed_d))
    if len(pr) > 2:
        bw = snap(wa * 0.55)
        up.append(Room(pr[1].name, "bath", 0, fd + bed_d, bw, rear_d - bed_d))
        up.append(Room(pr[2].name, "closet", bw, fd + bed_d, wa - bw, rear_d - bed_d))
    else:
        up.append(Room(pr[1].name, "bath", 0, fd + bed_d, wa, rear_d - bed_d))
    # (the hall band beside the primary's door belongs to the hall; the strip of column A in
    # front of it, outside the hall, joins the front bedroom)
    slots = []  # bedroom slots in order of quality: corners first
    if len(beds) >= 4 and wa - 4.0 >= 22.0:
        # a wide column A holds two front bedrooms (closets in the strip beside the landing)
        m = snap((wa - 4.0) / 2)
        slots.append(("front_a", (0, 0, m, fd), None))
        slots.append(("front_a2", (m, 0, wa - 4.0, fd), (wa - 4.0, 0, wa, fu)))
    else:
        slots.append(("front_a", (0, 0, wa - 4.0, fd), (wa - 4.0, 0, wa, fu)))       # bedroom + closet
    slots.append(("front_c", (hb, 0, W, fd), (xc, 0, hb, fu)))
    slots.append(("rear_c", (xc, fd, W, D), None))
    slots.append(("front_b", (xb, 0, xc, fu), None))
    slots.append(("rear_b", (xb, sy1, xc, D), None))
    used = set()
    for sp in beds:
        free = [s for s in slots if s[0] not in used]
        if not free:
            return None
        name, room, closet = free[0]
        used.add(name)
        x0, y0, x1, y1 = room
        up.append(Room(sp.name, "bedroom", x0, y0, x1 - x0, y1 - y0))
        if closet:
            cx0, cy0, cx1, cy1 = closet
            up.append(Room("Closet", "closet", cx0, cy0, cx1 - cx0, cy1 - cy0))
        if name == "rear_c":
            r = up[-1]
            spare = [s for s in slots if s[0] not in used and s[0] in ("front_b", "rear_b")]
            need_bath = len(baths) > len(spare) - max(0, len(beds) - len(used))
            if need_bath and rear_d - 12.0 >= 6.0:
                # its own bath behind it
                r.h = snap(max(12.0, rear_d - 8.0))
                up.append(Room(f"Ensuite {sp.name.split()[-1]}", "bath", xc, fd + r.h, wc, rear_d - r.h))
                baths.pop()
            elif rear_d > 17:
                # a deep corner room keeps a walk-in along the back
                r.h = snap(min(16.0, rear_d - 6.0))
                up.append(Room("Closet", "closet", xc, fd + r.h, wc, rear_d - r.h))
    if "front_a2" in [s[0] for s in slots] and "front_a2" not in used:
        return None
    # whatever slots are left: shared baths, the laundry, linen
    left = sorted([s for s in slots if s[0] not in used], key=lambda s: ["rear_b", "front_b", "front_a", "front_c", "rear_c"].index(s[0]))
    for name, room, closet in left:
        x0, y0, x1, y1 = room
        if closet:  # an unused front corner: a bath with its linen beside it
            x0, x1 = (x0, x1) if name == "front_a" else (x0, x1)
        if name in ("front_a", "front_c"):
            kind = "bath" if baths else ("laundry" if upstairs_laundry else "office")
            label = (baths.pop().name if baths else ("Laundry" if upstairs_laundry else "Study"))
            up.append(Room(label, kind, x0, y0, x1 - x0, y1 - y0))
            if closet:
                cx0, cy0, cx1, cy1 = closet
                up.append(Room("Linen", "closet", cx0, cy0, cx1 - cx0, cy1 - cy0))
        elif name == "rear_c":
            up.append(Room("Study" if not baths else baths.pop().name, "office" if not baths else "bath",
                           xc, fd, wc, rear_d))
        elif name == "front_b" and not baths:
            up.append(Room("Open to Foyer", "void", xb, 0, CORE, fu))  # a two-storey foyer
        elif name == "front_b":
            if baths:
                bwid = min(CORE, 9.0)
                up.append(Room(baths.pop().name, "bath", xb, 0, bwid, fu))
                if CORE - bwid >= 2.5:
                    up.append(Room("Laundry" if upstairs_laundry else "Linen",
                                   "laundry" if upstairs_laundry else "closet", xb + bwid, 0, CORE - bwid, fu))
            else:
                up.append(Room("Laundry" if upstairs_laundry else "Linen", "laundry" if upstairs_laundry else "closet",
                               xb, 0, CORE, fu))
        elif name == "rear_b" and not baths and not upstairs_laundry and len(pr) > 2:
            # the primary's walk-in behind the stair; its bath takes the whole back wall
            for r in up:
                if r.name == pr[2].name:
                    up.remove(r)
                    break
            for r in up:
                if r.name == pr[1].name:
                    r.w = wa
            up.append(Room(pr[2].name, "closet", xb, sy1, CORE, D - sy1))
        elif name == "rear_b":
            label = baths.pop().name if baths else ("Laundry" if upstairs_laundry else "Linen")
            kind = "bath" if label.startswith("Bath") else ("laundry" if label == "Laundry" else "closet")
            up.append(Room(label, kind, xb, sy1, CORE, D - sy1))
    if baths:
        return None  # more baths than the grid has places for
    # rooms that ended up the same kind side by side on the hall get merged visually by the
    # engine's checks; nothing else to do here
    if mirror:
        for rooms in (main, up):
            for r in rooms:
                r.x = W - r.x - r.w
    return [main, up]
