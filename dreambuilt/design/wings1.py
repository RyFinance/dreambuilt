"""One-storey houses built from wings instead of one box.

ell        a living block at the front, a bedroom wing across the back that runs past it: an L
           around a front garden. The wing's hall is a gallery along the garden side.
courtyard  a living block and the garage block either side of a court,
           joined by the bedroom wing across the back: a U around the court. The gallery hall
           runs along the court and links both front blocks.

Each block is a plain rectangle laid out with the same slicing tree as the other plans, so
every room keeps a door, a window wall and sensible proportions; `blocks` are returned so
each one gets its own roof.
"""
from __future__ import annotations

from typing import Optional

from ..brief import DesignBrief
from ..model import Room
from .layout import HALL, Leaf, Spec, _no_twin_baths, col, place, row
from .program import Program

snap = lambda v: round(v * 2) / 2
ROOM_D = 13.0  # depth of the bedroom wing's rooms behind the gallery


def _private_nodes(prog: Program, guest_side: bool = False):
    """Secondary bedrooms and baths, the primary suite last (the far, private end)."""
    pr = prog.primary
    suite = [col(Leaf(pr[2]), Leaf(pr[1])) if len(pr) > 2 else Leaf(pr[1]), Leaf(pr[0])]
    small = [Leaf(s) for s in prog.service if s.kind in ("laundry",)]
    if prog.ensuite_each:
        # each bedroom with its own ensuite beside it, the laundry before the primary suite
        ens = {x.name.split()[-1]: x for x in prog.baths}
        units = [row(Leaf(bd), Leaf(ens[bd.name.split()[-1]])) if bd.name.split()[-1] in ens else Leaf(bd)
                 for bd in prog.bedrooms]
        return units + (small or [Leaf(Spec("Linen", "closet", 18, 3))]) + suite
    nodes = _no_twin_baths([Leaf(s) for s in prog.bedrooms] + [Leaf(s) for s in prog.baths] + small + suite)
    return nodes


def _width_for(nodes, depth: float) -> float:
    from .layout import area
    return sum(area(n) for n in nodes) * 1.12 / depth


def plan(prog: Program, b: DesignBrief, W0: float, D0: float, mirror: bool, kind: str = "ell",
         stair: bool = False, lot_w: float = 60.0) -> Optional[tuple[list[Room], float, float, list]]:
    """(rooms, W, D, blocks) or None when the lot or the program doesn't suit the shape."""
    if stair:
        return None  # (a basement stair needs the strip plans)
    pub = {s.kind: s for s in prog.public}
    garage_w = 0.0
    want_garage = b.garage != "none" and "no garage" not in b.features and (b.has("garage") or b.cars)
    if kind == "courtyard" and want_garage:
        garage_w = {1: 13.0, 2: 23.0, 3: 33.0}.get(max(1, min(3, b.cars or 2)), 23.0)

    if kind == "courtyard" and not garage_w:
        return None  # the court is framed by the living wing and the garage wing
    priv = _private_nodes(prog)
    if kind == "ell-side":
        return _side_wing(prog, priv, b, mirror, lot_w)
    wing_w = snap(max(_width_for(priv, ROOM_D), 34.0))
    pub_area = sum(s.target for s in prog.public) * 1.15 + \
        sum(s.target for s in prog.service if s.kind != "laundry") * 1.1
    if kind == "ell":
        Wa = snap(max(22.0, min((pub_area * 1.1) ** 0.5, wing_w - 12.0)))
        Wt = wing_w
        if Wt > lot_w:
            return None
        Da = snap(max(16.0, pub_area / Wa))
        if Da > 32 or Wt - Wa < 10:
            return None
    else:
        court = 14.0
        Wa = snap(max(20.0, min(26.0, pub_area / 20.0)))
        Wg = garage_w or 16.0  # no garage: a guest / office block
        Wt = snap(max(wing_w, Wa + court + Wg))
        if Wt > lot_w:
            return None
        Da = snap(max(18.0, pub_area / Wa, 24.0 if garage_w else 0.0))
        if Da > 32:
            return None
    Db = HALL + ROOM_D
    D = Da + Db
    rooms: list[Room] = []

    # the living block: living to the street, dining and kitchen behind it toward the wing
    service = [Leaf(s) for s in prog.service if s.kind in ("mud", "pantry", "powder")]
    back = row(Leaf(pub["dining"]), Leaf(pub["kitchen"]), *([col(*service)] if service else []))
    front = [Leaf(pub["living"])]
    if "office" in pub and kind == "ell":
        front.insert(0, Leaf(pub["office"]))
    if "family" in pub:
        front.append(Leaf(pub["family"]))
    block_a = col(row(*front) if len(front) > 1 else front[0], back)
    place(block_a, 0, 0, Wa, Da, rooms)
    blocks = [(0.0, 0.0, Wa, Da, "Living wing")]

    if kind == "courtyard":
        gx = Wt - (garage_w or 16.0)
        if garage_w:
            n = max(1, min(3, b.cars or 2))
            rooms.append(Room(f"{n}-Car Garage", "garage", gx, 0, Wt - gx, Da))
            blocks.append((gx, 0.0, Wt - gx, Da, "Garage wing"))

    # the bedroom wing: a gallery hall along the garden / court side, rooms behind it
    rooms.append(Room("Hall", "hall", 0, Da, Wt, HALL))
    wing_rooms: list[Room] = []
    place(row(*priv), 0, Da + HALL, Wt, D, wing_rooms)
    rooms += wing_rooms
    blocks.append((0.0, Da, Wt, Db, "Bedroom wing"))

    if mirror:
        for r in rooms:
            r.x = Wt - r.x - r.w
        blocks = [(Wt - x - w, y, w, h, n) for x, y, w, h, n in blocks]
    return rooms, Wt, D, blocks


def _side_wing(prog: Program, priv, b: DesignBrief, mirror: bool, lot_w: float):
    """An L the other way: the living rooms across the front, the bedroom wing running back
    along one side, its gallery hall facing the back garden."""
    pub = {s.kind: s for s in prog.public}
    pub_area = sum(s.target for s in prog.public) * 1.15 + \
        sum(s.target for s in prog.service if s.kind != "laundry") * 1.1
    ww = ROOM_D + HALL
    dw = snap(max(24.0, _width_for(priv, ROOM_D)))
    Wt = snap(max(ww + 16.0, (pub_area * 1.5) ** 0.5))
    if Wt > lot_w:
        return None
    Da = snap(max(15.0, pub_area / Wt))
    if Da > 26 or dw > 70:
        return None
    rooms: list[Room] = []
    service = [Leaf(s) for s in prog.service if s.kind in ("mud", "pantry", "powder")]
    front = [Leaf(pub["living"])] + ([Leaf(pub["family"])] if "family" in pub else [])
    kitchen = col(Leaf(pub["kitchen"]), *service) if service else Leaf(pub["kitchen"])
    lay = row(*([Leaf(pub["office"])] if "office" in pub else []), Leaf(pub["dining"]), *front, kitchen)
    place(lay, 0, 0, Wt, Da, rooms)
    # the wing: rooms down its outer side, the gallery along its inner (garden) side
    place(col(*priv), 0, Da, ROOM_D, Da + dw, rooms)
    rooms.append(Room("Hall", "hall", ROOM_D, Da, HALL, dw))
    D = Da + dw
    blocks = [(0.0, 0.0, Wt, Da, "Living wing"), (0.0, Da, ww, dw, "Bedroom wing")]
    if mirror:
        for r in rooms:
            r.x = Wt - r.x - r.w
        blocks = [(Wt - x - w, y, w, h, n) for x, y, w, h, n in blocks]
    return rooms, Wt, D, blocks
