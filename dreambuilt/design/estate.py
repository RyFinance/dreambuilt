"""Estate template: the two-storey family home you see across Surrey and the Lower Mainland.

Main floor, front to back (garage side can mirror):
    front   den or guest suite | foyer with feature stair (bumps out under a tall portico) | 3-car garage (projects)
    middle  living & dining    | gallery hall, the spine from the door to the kitchen       | powder, laundry, mudroom
    rear    great room (fireplace, covered deck) | kitchen (+ nook bump-out) | spice kitchen, pantry
Upper floor:
    front   bedroom 2          | open to below over the foyer, stair arriving | bedroom 3 + ensuite + closet over the garage
    middle  ensuite 2, bath    | hall                                          | laundry, storage
    rear    bedroom 4          | hall                                          | primary suite (ensuite, walk-in), balcony over the nook

Every bedroom reaches the hall; every ensuite and walk-in hangs off its own bedroom;
the garage drops you into the mudroom, which leads to the kitchen and spice kitchen.
"""
from __future__ import annotations

import math

from ..brief import DesignBrief
from ..model import Balcony, Porch, RoofMass, Room, Steps

BW = 12.0  # foyer / gallery width
STAIR = 4.0
FRONT = 16.0  # depth of the front band (also the stair run)
MIDDLE = 13.0
GARAGE_D = 24.0
BUMP = 4.0  # foyer bump-out
NOOK_D = 9.0


LIVING_PROJ = 6.0  # the one-storey living wing steps forward of the entry


NARROW_BW, NARROW_GW, NARROW_A = 10.0, 21.0, 11.0


def applies(b: DesignBrief, style: dict) -> bool:
    if b.garage in ("side", "none") or "no garage" in b.features:
        return False  # this template is built around the garage out front
    if not style.get("layout", {}).get("estate") and b.garage != "front":
        return False  # colonials, foursquares and ranches keep their own plans
    # 50' lots fit the narrow version: 10' entry bay, 21' double garage, 11'+ west rooms
    big = b.stories == 2 and b.sqft >= 2800 and b.lot_width - 8.0 >= NARROW_GW + NARROW_BW + NARROW_A
    # five bedrooms need the full upper floor, which only pays off on a big house
    if not (big and b.beds <= 5):
        return False
    # the estate has a minimum size; don't use it when it would overshoot the brief
    W, D, gw, _cars, bw = footprint(b)
    if half_upper(b):
        est = W * D + (bw + gw) * D - gw * FRONT
    else:
        est = 2 * W * D - gw * FRONT
    return est <= b.sqft * 1.1


def half_upper(b: DesignBrief) -> bool:
    """Four bedrooms or fewer (and room for a west wing): the upper floor covers only the
    garage and entry bays."""
    # on a narrow lot the west wing is too slim for a main-floor bedroom: four go upstairs
    if b.beds == 4 and b.has("office"):
        return False  # four bedrooms upstairs so the office gets the main-floor room
    return b.beds <= 3 or (b.beds == 4 and bays(b)[3] >= 16)


def bays(b: DesignBrief) -> tuple[float, float, int, float]:
    """Entry-bay width, garage width, cars, minimum west-wing width for this lot."""
    room = b.lot_width - 8.0
    full = b.beds >= 5  # a full upper floor doubles the minimum size

    def fits(bw, gw, amin):
        w = bw + gw + amin
        smallest = (2 * w * (FRONT + MIDDLE + 15) - gw * FRONT) if full else w * 44 + (bw + gw) * 44 - gw * FRONT
        return smallest <= b.sqft * 1.1
    want3 = b.cars >= 3 or (b.cars == 0 and b.sqft >= 4200)
    if room >= 33.0 + BW + 18 and want3 and b.cars != 2 and fits(BW, 33.0, 18.0):
        return BW, 33.0, 3, 18.0
    if room >= 23.0 + BW + 16 and fits(BW, 23.0, 16.0):
        return BW, 23.0, 2, 16.0
    return NARROW_BW, NARROW_GW, 2, NARROW_A


def footprint(b: DesignBrief) -> tuple[float, float, float, int, float]:
    """Main width and depth, garage width, cars, entry-bay width."""
    bw, gw, cars, amin = bays(b)
    snap = lambda v: round(v * 2) / 2
    room = b.lot_width - 8.0
    void = (bw - STAIR) * FRONT
    if half_upper(b):
        D = max(FRONT + MIDDLE + 14, min(52.0, math.sqrt(b.sqft / 2.4)))
        U = (bw + gw) * D - void
        M = b.sqft - U
        W = (M + gw * FRONT - 13 * NOOK_D + (bw + gw) * LIVING_PROJ) / (D + LIVING_PROJ)
        W = max(W, bw + gw + amin)
        return snap(min(W, room)), snap(D), gw, cars, bw
    block = (b.sqft + gw * FRONT + void - 13 * NOOK_D) / 2
    W = min(math.sqrt(block * 1.25), room)
    W = max(W, bw + gw + amin)
    D = max(block / W, FRONT + MIDDLE + 15)
    W = max(block / D, bw + gw + amin)  # at the minimum depth, narrow down instead
    return snap(W), snap(D), gw, cars, bw


def _row(y0: float, y1: float, x0: float, x1: float, parts: list[tuple[str, str, float]]):
    """Rooms side by side across [x0, x1] sharing [y0, y1]; widths in proportion to weights."""
    tot = sum(w for _, _, w in parts)
    out, x = [], x0
    for i, (name, kind, w) in enumerate(parts):
        nx = x1 if i == len(parts) - 1 else round((x + (x1 - x0) * w / tot) * 2) / 2
        out.append(Room(name, kind, x, y0, nx - x, y1 - y0))
        x = nx
    return out


def _col(x0, x1, y0, y1, parts):
    tot = sum(w for _, _, w in parts)
    out, y = [], y0
    for i, (name, kind, w) in enumerate(parts):
        ny = y1 if i == len(parts) - 1 else round((y + (y1 - y0) * w / tot) * 2) / 2
        out.append(Room(name, kind, x0, y, x1 - x0, ny - y))
        y = ny
    return out


def bed_suite(bed: str, ens: str, x0: float, x1: float, y0: float, y1: float,
              hall_side: str, ens_w: float = 7.0, ens_kind: str = "bath") -> list[Room]:
    """Bedroom on the outside wall; its ensuite and a short hall stub on the hall side.

    The stub gives the bedroom its own door to the hall while the ensuite opens only
    from the bedroom, so the bedroom keeps an exterior wall for its egress window.
    """
    stub = 4.0
    ens_w = max(ens_w, round(((x1 - x0) - 1.9 * (y1 - y0)) * 2) / 2)  # keep the bedroom under 2:1
    ex = x1 - ens_w if hall_side == "E" else x0
    out = [Room(ens, ens_kind, ex, y0, ens_w, y1 - y0 - stub),
           Room("Hall", "hall", ex, y1 - stub, ens_w, stub)]
    bx0, bx1 = (x0, x1 - ens_w) if hall_side == "E" else (x0 + ens_w, x1)
    out.append(Room(bed, "bedroom", bx0, y0, bx1 - bx0, y1 - y0))
    return out


def bath_budget(b: DesignBrief, wants: list[str]) -> set[str]:
    """Which of the wanted full baths (in priority order) the brief pays for."""
    return set(wants[:max(2, int(b.baths))])


def living_proj(a: float) -> float:
    """How far the living wing steps forward: less on a slim wing, so it stays a good shape."""
    p = max(0.0, min(LIVING_PROJ, round((1.6 * a - FRONT) * 2) / 2))
    return p if p >= 3.0 else 0.0  # a token step reads as a mistake on the elevation


LANDING = 5.0  # the upper landing at the top of the stair, open over the foyer


def plan(b: DesignBrief, variant: bool) -> tuple[list[list[Room]], dict]:
    """Room rectangles for both floors (garage on the east), plus the bits the details need.

    variant: an open great room, kitchen and nook (no walls between them) instead of
    separate rooms with cased openings."""
    W, D, gw, cars, bw = footprint(b)
    BW_ = bw
    a = W - bw - gw
    xb, xc = a, a + bw
    half = half_upper(b)
    powder = b.baths - int(b.baths) >= 0.5
    # a deep house puts its extra depth in the middle band, so the great room and kitchen
    # across the back stay a good shape
    mid_d = max(MIDDLE, round((D - FRONT - 20.0) * 2) / 2)
    y1 = FRONT + mid_d
    proj = living_proj(a)
    five_up = b.beds == 5 and (b.has("office") or a < 16)
    main_bed = ((b.beds == 4 and half) or b.beds == 5) and not five_up
    office_main = b.has("office") and not main_bed
    # full baths in priority order; the brief's count decides how many become real baths
    if half:
        wants = ["Primary Ensuite", "Bath", "Main Ensuite", "Ensuite 2", "Ensuite 3"]
    else:
        wants = ["Primary Ensuite", "Bath", "Ensuite 2", "Main Ensuite", "Ensuite 3", "Office Bath"]
    if not main_bed:
        wants.remove("Main Ensuite")
    if b.beds < 3:
        wants.remove("Ensuite 3")
    baths = bath_budget(b, wants)
    main: list[Room] = []
    # front: the living wing steps forward; the entry sits back in the nest; the garage leads
    main.append(Room("Living", "living", 0, -proj, a, FRONT + proj))
    main.append(Room("Foyer", "entry", xb, 0, BW_ - STAIR, FRONT))
    main.append(Room("Stair", "stair", xc - STAIR, 0, STAIR, FRONT))
    main.append(Room(f"{cars}-Car Garage", "garage", xc, FRONT - GARAGE_D, gw, GARAGE_D))
    # middle: a main-floor suite (or office, or dining), the gallery, then the service rooms
    if main_bed:
        n = 4 if half else 5
        kind = "bath" if "Main Ensuite" in baths else "closet"
        ens = f"Ensuite {n}" if kind == "bath" else f"Walk-in {n}"
        if a >= 16:
            main += bed_suite(f"Bedroom {n}", ens, 0, a, FRONT, y1, "E", ens_kind=kind)
        else:
            main += _col(0, a, FRONT, y1, [(f"Bedroom {n}", "bedroom", 1.6), ("Bath", "bath", 1)])
    elif office_main and "Office Bath" in baths:
        # office with a full bath beside it (off a short hall, so it doubles as a guest room)
        if a >= 18:
            suite = bed_suite("Office", "Bath", 0, a, FRONT, y1, "E")
            for r in suite:
                if r.name == "Office":
                    r.kind = "office"
        else:
            suite = _col(0, a, FRONT, y1, [("Office", "office", 1.5), ("Bath", "bath", 1)])
        main += suite
    elif office_main:
        main.append(Room("Office", "office", 0, FRONT, a, mid_d))
    else:
        main.append(Room("Dining", "dining", 0, FRONT, a, mid_d))
    main.append(Room("Gallery", "hall", xb, FRONT, BW_, mid_d))
    sy1 = FRONT + MIDDLE if mid_d - MIDDLE >= 9 else y1
    main += _row(FRONT, sy1, xc, W, [("Powder" if powder else "Bath", "powder" if powder else "bath", 6),
                                     ("Laundry", "laundry", 8), ("Mudroom", "mud", 9)])
    if sy1 < y1:
        # a deep middle band: a flex room behind the service rooms, off the kitchen
        main.append(Room("Flex Room", "family", xc, sy1, W - xc, y1 - sy1))
    if mid_d - MIDDLE >= 9:
        # and the west room splits: dining / office in front, a den behind it off the gallery
        west = next(r for r in main if r.x == 0 and abs(r.y - FRONT) < 1e-6 and abs(r.h - mid_d) < 1e-6
                    and r.kind in ("dining", "office"))
        west.h = MIDDLE
        dd = min(mid_d - MIDDLE, round(a * 2.0 * 2) / 2)
        main.append(Room("Den", "family", 0, FRONT + MIDDLE, a, dd))
        if mid_d - MIDDLE - dd > 0.4:
            main.append(Room("Storage", "closet", 0, FRONT + MIDDLE + dd, a, mid_d - MIDDLE - dd))
    sz = getattr(b, "sizes", {}) or {}
    rear = _row(y1, D, 0, W, [("Great Room", "family", (1.75 if variant else 1.55) * sz.get("family", 1.0)),
                              ("Kitchen", "kitchen", 1.3 * sz.get("kitchen", 1.0)), ("Spice Kitchen", "spice", 0.8)])
    spice = rear[2]
    rear[2:3] = _col(spice.x, spice.x + spice.w, spice.y, spice.y + spice.h,
                     [("Pantry", "closet", 0.45), ("Spice Kitchen", "spice", 1)])
    main += rear
    kit = rear[1]
    nook_w = min(kit.w, 14.0)
    nook = Room("Dining" if main_bed else "Nook", "dining", kit.x + (kit.w - nook_w) / 2, D, nook_w, NOOK_D)
    main.append(nook)
    # upper floor: the stair arrives on a landing that looks over the foyer
    up: list[Room] = []
    up.append(Room("Open to Below", "void", xb, 0, BW_ - STAIR, FRONT))
    up.append(Room("Stair", "stair", xc - STAIR, 0, STAIR, FRONT))
    snap = lambda v: round(v * 2) / 2
    if half:
        s = snap(max(8.0, min(11.0, gw * 0.33)))
        f2 = FRONT + 4.0
        mid = snap((D - f2) * 0.45)
        up += _col(xb, xb + 7, FRONT, D, [("Bath", "bath", 1.1), ("Laundry", "laundry", 1),
                                          ("Linen", "closet", 0.5)])
        up.append(Room("Hall", "hall", xb + 7, FRONT, BW_ - 7, D - FRONT))
        up.append(Room("Bedroom 2", "bedroom", xc, 0, gw - s, f2))
        if b.beds >= 3:
            e3 = "Ensuite 3" in baths
            up += bed_suite("Bedroom 3", "Ensuite 3" if e3 else "Walk-in 3", xc, W, f2, f2 + mid, "W",
                            ens_kind="bath" if e3 else "closet")
        else:
            up.append(Room("Office", "office", xc, f2, W - xc, mid))
        up.append(Room("Primary Bedroom", "bedroom", xc, f2 + mid, gw - s, D - f2 - mid))
        if "Ensuite 2" in baths:
            up += _col(W - s, W, 0, f2, [("Ensuite 2", "bath", 1.1), ("Closet 2", "closet", 1)])
        else:
            up.append(Room("Walk-in 2", "closet", W - s, 0, s, f2))
        up += _col(W - s, W, f2 + mid, D, [("Primary Ensuite", "bath", 1.3), ("Walk-in Closet", "closet", 1)])
    else:
        # the hall runs straight on from the top of the stair; the landing spans the entry bay
        xh = xc - 4.0
        f2 = FRONT + LANDING
        up.append(Room("Landing", "hall", xb, FRONT, BW_, LANDING))
        up.append(Room("Hall", "hall", xh, f2, 4.0, D - f2))
        # west front: bedroom 2, its ensuite behind it, a stub to the landing
        b2 = snap(max(11.0, f2 - 8.0))
        e2 = "Ensuite 2" in baths
        up.append(Room("Bedroom 2", "bedroom", 0, 0, a, b2))
        up.append(Room("Ensuite 2" if e2 else "Walk-in 2", "bath" if e2 else "closet", 0, b2, a - 4, f2 - b2))
        up.append(Room("Hall", "hall", a - 4, b2, 4.0, f2 - b2))
        # east front: bedroom 3 over the garage, its ensuite and walk-in behind it
        if gw > 24:
            # a wide garage bay: bedroom 3 reaches the landing itself, its suite beside it
            s3 = snap(min(12.0, gw - f2 * 0.95))
            up.append(Room("Bedroom 3", "bedroom", xc, 0, gw - s3, f2))
            if "Ensuite 3" in baths:
                up += _col(W - s3, W, 0, f2, [("Ensuite 3", "bath", 1.1), ("Walk-in 3", "closet", 1)])
            else:
                up.append(Room("Walk-in 3", "closet", W - s3, 0, s3, f2))
        else:
            b3 = snap(f2 - 6.0)
            up.append(Room("Bedroom 3", "bedroom", xc, 0, gw, b3))
            up.append(Room("Hall", "hall", xc, b3, 4.0, f2 - b3))
            if "Ensuite 3" in baths:
                # walk-in first, ensuite at the far end: never against the shared bath behind
                up += _row(b3, f2, xc + 4, W, [("Walk-in 3", "closet", 1), ("Ensuite 3", "bath", 1)])
            else:
                up.append(Room("Walk-in 3", "closet", xc + 4, b3, W - xc - 4, f2 - b3))
        # west rear: bedroom 4 at the back; bedroom 5 (or laundry) between
        back = D - f2
        if five_up and xh > 22:
            # wide back bedrooms: each keeps the outside wall, its walk-in and a door stub on the hall side
            ym = snap(f2 + (D - f2) / 2)
            up += bed_suite("Bedroom 5", "Walk-in 5", 0, xh, f2, ym, "E", ens_w=7.0, ens_kind="closet")
            up += bed_suite("Bedroom 4", "Walk-in 4", 0, xh, ym, D, "E", ens_w=7.0, ens_kind="closet")
        elif five_up:
            up += _col(0, xh, f2, D, [("Bedroom 5", "bedroom", 1), ("Bedroom 4", "bedroom", 1)])
        else:
            mid = snap(min(9.0, back - 11.0))
            up += _row(f2, f2 + mid, 0, xh, [("Linen", "closet", 0.6), ("Laundry", "laundry", 1)])
            up.append(Room("Bedroom 4", "bedroom", 0, f2 + mid, xh, D - f2 - mid))
        # east rear: the shared bath on the hall, then the primary suite across the back
        s = snap(max(8.5, min(11.0, gw * 0.4)))
        row = snap(max(min(9.0, back - 13.0), back - 16.0))  # the primary stays under 16' deep
        up.append(Room("Bath", "bath", xc, f2, 9.0, row))
        up.append(Room("Walk-in Closet", "closet", xc + 9.0, f2, W - xc - 9.0, row))
        up.append(Room("Primary Bedroom", "bedroom", xc, f2 + row, gw - s, D - f2 - row))
        up.append(Room("Primary Ensuite", "bath", W - s, f2 + row, s, D - f2 - row))
    _primary_takes_biggest(up, "Bedroom 2" if half else "Bedroom 3")
    if b.primary_floor == "main":
        _primary_on_main(main, up, b, a)
    by = {r.name: r for r in main}
    extras = {"W": W, "D": D, "gw": gw, "cars": cars, "nook": nook, "great": by["Great Room"],
              "garage": next(r for r in main if r.kind == "garage"), "foyer": by["Foyer"],
              "living": by.get("Living") or by["Primary Bedroom"],
              "hearth": by.get("Living") or by["Great Room"], "half": half, "a": a, "bw": bw, "xc": xc, "open": variant}
    return [main, up], extras


def _primary_on_main(main: list[Room], up: list[Room], b: DesignBrief, a: float) -> None:
    """The client wants the primary downstairs: the front living wing becomes the primary
    bedroom (it opens off the foyer), the room behind it its ensuite and walk-in. Upstairs,
    the old primary suite becomes the bedroom that moved down, or a bonus room."""
    liv = next(r for r in main if r.name == "Living")
    mid = next((r for r in main if r.x < 1e-6 and abs(r.y - FRONT) < 1e-6 and r.kind in
                ("dining", "office", "bedroom")), None)
    if mid is None:
        return
    moved = mid.name if mid.kind == "bedroom" else None
    # whatever sat behind the living wing (dining, office, a guest suite) gives way to the suite
    lost_office = any(r.kind == "office" for r in main if r.x < a - 1e-6 and FRONT - 1e-6 <= r.y < FRONT + mid.h - 1e-6)
    for r in [r for r in main if r.x < a - 1e-6 and FRONT - 1e-6 <= r.y < FRONT + mid.h - 1e-6 and r is not liv]:
        main.remove(r)
    liv.name, liv.kind = "Primary Bedroom", "bedroom"
    half = round(a * 0.55 * 2) / 2
    main.append(Room("Primary Ensuite", "bath", 0, FRONT, half, mid.h))
    main.append(Room("Walk-in Closet", "closet", half, FRONT, a - half, mid.h))
    for r in up:
        if r.name == "Primary Bedroom":
            if moved:
                r.name, r.kind = moved, "bedroom"
            elif lost_office or b.has("office"):
                r.name, r.kind = "Office", "office"  # the office moves up into the old primary
            else:
                r.name, r.kind = "Bonus Room", "family"
        elif r.name == "Primary Ensuite":
            r.name = f"Ensuite {moved.split()[-1]}" if moved else "Bath 3"
        elif r.name == "Walk-in Closet":
            r.name = f"Walk-in {moved.split()[-1]}" if moved else "Storage"


def _primary_takes_biggest(up: list[Room], other: str) -> None:
    """The primary suite goes in the bigger of its zone and `other`'s zone: the two
    bedrooms trade names, and the ensuite / walk-in go with the primary."""
    by = {r.name: r for r in up}
    p, o = by.get("Primary Bedroom"), by.get(other)
    if p is None or o is None or o.area <= p.area:
        return
    n = other.split()[-1]
    p_ens, p_wic = by.get("Primary Ensuite"), by.get("Walk-in Closet")
    o_ens = by.get(f"Ensuite {n}")
    o_wic = by.get(f"Walk-in {n}") or by.get(f"Closet {n}")
    p.name, o.name = other, "Primary Bedroom"
    if o_ens is not None:
        o_ens.name = "Primary Ensuite"
        if p_ens is not None:
            p_ens.name = f"Ensuite {n}"
        if o_wic is not None:
            o_wic.name = "Walk-in Closet"
        if p_wic is not None:
            p_wic.name = f"Walk-in {n}"
        return
    # the other suite had only a walk-in: half of it becomes the primary's ensuite, and the
    # old primary ensuite becomes the other bedroom's walk-in
    if o_wic is not None and p_ens is not None:
        # split the walk-in: the ensuite takes the end away from any other bath (no twin baths)
        from .details import shared_edge
        baths = [r for r in up if r.kind == "bath" and r is not p_ens]
        horiz = o_wic.w >= o_wic.h
        span = o_wic.w if horiz else o_wic.h
        half = round(span * 0.55 * 2) / 2
        cands = []
        for low in (True, False):
            if horiz:
                ex = o_wic.x if low else o_wic.x + o_wic.w - half
                e = Room("Primary Ensuite", "bath", ex, o_wic.y, half, o_wic.h)
            else:
                ey = o_wic.y if low else o_wic.y + o_wic.h - half
                e = Room("Primary Ensuite", "bath", o_wic.x, ey, o_wic.w, half)
            touch = sum((shared_edge(e, r)[3] - shared_edge(e, r)[2]) for r in baths if shared_edge(e, r))
            cands.append((touch, low, e))
        _, low, ens = min(cands, key=lambda c: c[0])
        if horiz:
            if low:
                o_wic.x += half
            o_wic.w -= half
        else:
            if low:
                o_wic.y += half
            o_wic.h -= half
        o_wic.name = "Walk-in Closet"
        up.append(ens)
        p_ens.name, p_ens.kind = f"Walk-in {n}", "closet"
        if p_wic is not None:
            p_wic.name = f"Closet {n}"


def mirror(floors: list[list[Room]], W: float) -> None:
    for rooms in floors:
        for r in rooms:
            r.x = W - r.x - r.w


def front_gable(name: str, x0: float, x1: float, y0: float, depth: float, plate: float, pitch: float,
                steep: float, over: float, cx: float, max_w: float) -> RoofMass:
    """A street-facing gable that dies cleanly into the hip behind it: narrow enough and far
    enough in from the side that its ridge never stands above the main roof."""
    rise = lambda w: w / 2 * steep / 12 + 0.75  # ridge above the plate, plus a margin
    need = lambda w: rise(w) * 12 / pitch  # run of the hip needed to cover it
    half_span = min(x1 - x0, depth) / 2 + over
    w = max_w
    while w > 8.0 and need(w) > half_span:
        w -= 1.0
    if cx > (x0 + x1) / 2:
        cx = min(cx, x1 + over - need(w))
    else:
        cx = max(cx, x0 - over + need(w))
    length = min(depth / 2, need(w) - over + 1.0)
    return RoofMass(name, cx - w / 2, y0, w, length, kind="gable", ridge="y", pitch=steep,
                    overhang=over, plate_z=plate, gable_ends=("S",))


def roof_kind(style: dict, features: list[str]) -> str:
    """hip | gable | flat: what the client asked for, else what the style does."""
    for f, k in (("flat roof", "flat"), ("shed roof", "flat"), ("gable roof", "gable"), ("hip roof", "hip")):
        if f in features:
            return k
    return {"flat": "flat", "shed": "flat", "gable": "gable"}.get(style.get("roof", {}).get("kind"), "hip")


def roofs_and_porches(ex: dict, style: dict, floors, levels, features: list[str] = ()):
    """Roof masses, the entry porch in the nest, the covered rear deck and the balcony.

    Three roof families: low hips with one feature gable (the Lower Mainland house), side
    gables with street-facing gables (craftsman / farmhouse), or flat roofs with deep
    overhangs (modern)."""
    W, D = ex["W"], ex["D"]
    r = style.get("roof", {})
    kind = roof_kind(style, list(features))
    pitch, over = r.get("pitch", 5), r.get("overhang", 2.0)
    if kind == "flat":
        pitch, over = 0.25, max(over, 2.5)
    elif kind == "gable" and pitch < 6:
        pitch = 8
    wood = "wood" in features or style.get("siding", {}).get("accent") == "wood"
    l1, l2 = levels[0].plate_z, levels[1].plate_z
    upper = levels[1].footprint.bounds
    ux0, uy0, ux1, uy1 = upper
    liv = ex["living"]
    g = ex["garage"]
    if kind == "flat":
        roofs = [RoofMass("Upper", ux0, uy0, ux1 - ux0, uy1 - uy0, kind="shed", pitch=pitch,
                          overhang=over, plate_z=l2, low_side="N")]
    else:
        # a gabled house turns its big gable to the street; a hipped one runs its ridge long
        roofs = [RoofMass("Upper", ux0, uy0, ux1 - ux0, uy1 - uy0, kind=kind,
                          ridge="y" if (kind == "gable" or ux1 - ux0 < uy1 - uy0) else "x",
                          pitch=pitch, overhang=over, plate_z=l2)]
    if ex["half"]:
        o = over * 0.8
        wx = liv.x if liv.x < 1e-6 else liv.x + o
        ww = liv.w - o  # trimmed on the entry side so its eave lands on the wall
        if kind == "flat":
            roofs.append(RoofMass("Wing", wx, liv.y, ww, D - liv.y, kind="shed", pitch=pitch,
                                  overhang=o, plate_z=l1, low_side="N"))
        elif kind == "gable":
            # the wing turns a tall gable to the street
            roofs.append(RoofMass("Wing", wx, liv.y, ww, D - liv.y, kind="gable", ridge="y",
                                  pitch=10, overhang=o, plate_z=l1, gable_ends=("S",),
                                  cladding="wood" if wood else ""))
        else:
            # a plain hip like the main roof (a gable this low would crowd it)
            roofs.append(RoofMass("Wing", wx, liv.y, ww, D - liv.y, kind="hip", ridge="y",
                                  pitch=pitch, overhang=o, plate_z=l1))
    if kind == "hip":
        # the one feature gable on the upper floor over the garage bay
        fg = front_gable("Upper gable", ux0, ux1, uy0, uy1 - uy0, l2, pitch, ex.get("gable_pitch", 10) if kind == "hip" else 12,
                         over * 0.8, g.x + g.w / 2, max_w=min(g.w - 3.0, 16.0))
        fg.cladding = "wood" if wood else ""
        roofs.append(fg)
    fo = ex["foyer"]
    pw = fo.w + STAIR
    depth = max(-g.y, 6.0)
    fx0, fx1 = min(fo.x, g.x), max(fo.x + pw, g.x + g.w)
    if kind == "flat":
        # a thin flat canopy across entry and garage
        roofs.append(RoofMass("Front", fx0, -depth, fx1 - fx0, depth, kind="shed", pitch=0.25,
                              overhang=1.5, plate_z=l1 - 0.5, low_side="S"))
    else:
        roofs.append(RoofMass("Front", fx0, -depth, fx1 - fx0, depth * 2, kind="hip", ridge="x", pitch=4,
                              overhang=1.2, plate_z=l1 - 0.5))
    if ex.get("grand") and kind != "flat":
        # a grand entry: a tall stone gable over the entry, rising in front of the upper floor
        roofs.append(RoofMass("Entry", fo.x - 0.5, -depth, pw + 1.0, depth + 4.0, kind="gable", ridge="y",
                              pitch=12, overhang=0.9, plate_z=l2 - 1.0, gable_ends=("S",), cladding="stone"))
    porch = Porch(fo.x, fo.y - depth, pw, depth, floor_z=levels[0].floor_z,
                  columns=[(fo.x + 1.0, fo.y - depth + 1.0), (fo.x + pw - 1.0, fo.y - depth + 1.0)],
                  column="square", pier_height=3.0,
                  steps=[Steps(fo.x + fo.w / 2 - 3, 6.0, "S", risers=max(2, math.ceil(levels[0].floor_z / 0.6)))])
    nook = ex["nook"]
    roofs.append(RoofMass("Nook", nook.x, nook.y, nook.w, nook.h, kind="shed", pitch=0.5,
                          overhang=0.75, plate_z=l1 + 0.5, low_side="N"))
    great = ex["great"]
    deck_w = min(great.w - 2.0, 20.0)
    dx = great.x + (great.w - deck_w) / 2
    deck = Porch(dx, D, deck_w, 12.0, floor_z=levels[0].floor_z,
                 columns=[(dx + 1.0, D + 11.0), (dx + deck_w - 1.0, D + 11.0)], column="square",
                 pier_height=0.0, steps=[Steps(dx + deck_w / 2 - 3, 6.0, "N", risers=2)])
    # the deck roof tucks under the main eave so it never peeks over the wing from the street
    roofs.append(RoofMass("Deck", dx, D, deck_w, 12.0, kind="shed", pitch=0.25 if kind == "flat" else 2.5,
                          overhang=1.0, plate_z=l1 - (0.5 if kind == "flat" else 2.5), low_side="N"))
    over_nook = nook.x >= ux0 - 1e-6
    balconies = [Balcony(nook.x, nook.y, nook.w, nook.h - 0.5, level=1)] if over_nook else []
    return roofs, [porch, deck], balconies


def claddings(ex: dict, style: dict, features: list[str]) -> list:
    """Where the finishes change on the street side: stone at the entry (and the living wing
    on a modern house), warm wood on the upper floor over the garage."""
    from ..model import Cladding
    det = set(style.get("details", []))
    modern = roof_kind(style, list(features)) == "flat"
    stone = "stone" in features or det & {"stone-entry", "stone-base"}
    wood = "wood" in features or style.get("siding", {}).get("accent") == "wood"
    fo, g, liv = ex["foyer"], ex["garage"], ex["living"]
    out = []
    if stone:
        a, b = fo.x - 0.1, fo.x + fo.w + STAIR + 0.1
        if modern:
            a, b = min(a, liv.x - 0.1), max(b, liv.x + liv.w + 0.1)
        out.append(Cladding(0, "S", a, b, "stone"))
    if wood:
        out.append(Cladding(1, "S", g.x - 0.1, g.x + g.w + 0.1, "wood"))
        if modern:
            out.append(Cladding(0, "S", g.x - 0.1, g.x + g.w + 0.1, "wood"))
    if "brick" in features:
        out.append(Cladding(0, "S", -1e3, 1e3, "brick"))
    return out
