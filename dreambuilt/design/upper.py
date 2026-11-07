"""The upper floor laid out on top of the main floor.

The other generators plan each floor on its own and hope they line up. This one starts from
the main floor as built: its stair (the same rectangle upstairs), its wet rooms (kitchen,
laundry, powder, baths) and its walls. It tries a few hundred arrangements of the upper floor
and keeps the one an architect would mark least:

    front band   bedrooms on the street, a full-width band in front of the hall
    hall         a short corridor in front of the stair, between the end rooms
    rear band    beside the stair: bedrooms, baths, laundry; baths over the wet rooms below
    end columns  a suite at either end runs front to back (bedroom on the hall, its bath and
                 walk-in behind), so the hall stops short of the end walls

Scored on: baths over a wet room below (P11), never two baths side by side or in a row,
closets under 12% of the floor, a short hall, bedrooms square enough and near their target
size, the primary clearly the biggest, and walls standing on walls below.
"""
from __future__ import annotations

import itertools
from typing import Optional

from ..model import Room
from .layout import HALL, STAIR_UL, STAIR_UW
from .program import Program, Spec

snap = lambda v: round(v * 2) / 2
WET = {"bath", "powder", "kitchen", "laundry", "spice"}
BATH_LONG = 9.5      # longest a bath runs before the rest is a closet (details.CAP)
BED_MIN = 10.5


def plan(prog: Program, lower: list[Room], W: float, D: float,
         upstairs_laundry: bool = False, wing_side: Optional[str] = None,
         primary_elsewhere: bool = False) -> Optional[list[Room]]:
    stair = next((r for r in lower if r.kind == "stair"), None)
    if stair is None or abs(stair.w - STAIR_UW) > 0.01 or abs(stair.h - STAIR_UL) > 0.01:
        return None
    if len(prog.primary) < 2 and not primary_elsewhere:
        return None
    if primary_elsewhere:
        import dataclasses
        prog = dataclasses.replace(prog, primary=[])  # the primary suite is over the garage
    sx, ys = stair.x, stair.y
    f = ys - HALL
    R = D - ys
    if f < 10.0 or R < 10.0 or stair.y + stair.h > D - 2.0:
        return None
    wet = [r for r in lower if r.kind in WET]
    walls = _walls(lower)
    best = None
    def all_variants():
        yield from _variants(prog, W, D, sx, ys, upstairs_laundry)
        if upstairs_laundry:
            # or a laundry closet (a stacked washer and dryer) at one end of the hall
            for rooms in _variants(prog, W, D, sx, ys, False):
                hall = next(r for r in rooms if r.kind == "hall" and abs(r.y - f) < 0.01)
                if hall.w < 6.0 + STAIR_UW + 3.0:
                    continue
                for side in ("L", "R"):
                    if (side == "L" and hall.x + 6.0 > sx) or (side == "R" and hall.x + hall.w - 6.0 < sx + STAIR_UW):
                        continue
                    out = [Room(r.name, r.kind, r.x, r.y, r.w, r.h) for r in rooms]
                    h = next(r for r in out if r.kind == "hall" and abs(r.y - f) < 0.01)
                    lx = h.x if side == "L" else h.x + h.w - 6.0
                    h.w -= 6.0
                    if side == "L":
                        h.x += 6.0
                    out.append(Room("Laundry", "closet", lx, f, 6.0, HALL))
                    yield out
    for rooms in all_variants():
        hall = [r for r in rooms if r.kind == "hall" and abs(r.y - (ys - HALL)) < 0.01]
        if wing_side == "R" and not any(abs(r.x + r.w - W) < 0.01 for r in hall):
            continue  # the hall must run on over the garage
        if wing_side == "L" and not any(r.x < 0.01 for r in hall):
            continue
        s = score(rooms, wet, walls, prog, W, D, wing_side)
        if s is not None and (best is None or s < best[0]):
            best = (s, rooms)
    return best[1] if best else None


# -- arrangements ---------------------------------------------------------------------------

def _variants(prog: Program, W, D, sx, ys, laundry_up):
    f, R = ys - HALL, D - ys
    pr = prog.primary
    beds = list(prog.bedrooms)
    baths = list(prog.baths)
    nb = len(beds)
    for pside in (("L", "R", "rear") if pr else ("none",)):
        for other in (None, "B"):
            if other == "B" and (not baths or not beds):
                continue
            flushL, flushR = sx, W - sx - STAIR_UW  # an end column right up to the stair
            ePs = [13.0, 14.5, 16.0, 17.5, 19.0, 20.5] + [v for v in ((flushL,) if pside == "L" else (flushR,)) if 12.5 <= v <= 19]
            eBs = [12.0, 13.5, 15.0] + [v for v in (flushL, flushR) if 12.0 <= v <= 16.5]
            for eP in (sorted(set(ePs)) if pside in ("L", "R") else (0.0,)):
                for eB in (sorted(set(eBs)) if other else (0.0,)):
                    if pside == "L":
                        a, b = eP, W - eB
                    elif pside == "R":
                        a, b = eB, W - eP
                    elif pside == "none" and not other:
                        a, b = 0.0, W
                    else:  # the B column on whichever side has more room beside the stair
                        a, b = (eB, W) if sx >= W - sx - STAIR_UW else (0.0, W - eB)
                    Ls, Rs = sx - a, b - sx - STAIR_UW
                    if Ls < -1e-6 or Rs < -1e-6 or 0 < Ls < 5.0 or 0 < Rs < 5.0:
                        continue
                    rest_beds = beds[1:] if other == "B" else beds[:]
                    rest_baths = baths[1:] if other == "B" else baths[:]
                    Fw = b - a
                    for nf in range(1, min(len(rest_beds), int(Fw // BED_MIN)) + 1):
                        front_beds = rest_beds[:nf]
                        rear_beds = rest_beds[nf:]
                        ens = prog.ensuite_each
                        for front_bath in ([None] + (list(range(nf + 1)) if rest_baths and not ens else [])):
                            if ens:
                                # every bedroom with its own bath: the front ones beside them
                                fb, rb = rest_baths[:nf], rest_baths[nf:]
                                front = _front_suites(front_beds, fb, a, b, f)
                            else:
                                fb = rest_baths[:1] if front_bath is not None else []
                                rb = rest_baths[1:] if front_bath is not None else rest_baths[:]
                                front = _front(front_beds, fb, a, b, f, front_bath)
                            if front is None:
                                continue
                            ns_opts = [len(rear_beds)] if ens else range(0, min(len(rear_beds), len(rb)) + 1 if R >= 16.0 else 1)
                            if ens and (len(rb) != len(rear_beds) or (rear_beds and R < 16.0)):
                                continue
                            for ns in ns_opts:
                                # ns bedrooms in the rear band take a bath behind them as their own
                                items = ["suite"] * ns + ["bed"] * (len(rear_beds) - ns) + ["bath"] * (len(rb) - ns) + \
                                    (["laundry"] if laundry_up else []) + (["primary"] if pside == "rear" else [])
                                seen = set()
                                for perm in itertools.permutations(items):
                                    for k in range(len(perm) + 1):
                                        key = (perm[:k], perm[k:])
                                        if key in seen:
                                            continue
                                        seen.add(key)
                                        left, right = list(perm[:k]), list(perm[k:])
                                        if (left and Ls < 5) or (right and Rs < 5) or (Ls >= 5 and not left) or \
                                                (Rs >= 5 and not right):
                                            continue
                                        for flip in (False, True):
                                            rooms = _assemble(prog, W, D, sx, ys, a, b, pside, eP, other, eB,
                                                              front, left, right, rear_beds, rb, flip)
                                            if rooms is not None:
                                                yield rooms
                                if R >= 17.0:
                                    yield from _spined(prog, W, D, sx, ys, a, b, pside, eP, other, eB, front,
                                                       items, rear_beds, rb)
    _ = nb


def _spined(prog, W, D, sx, ys, a, b, pside, eP, other, eB, front, items, rear_beds, rb):
    """Deep houses: a spine hall down one side of the stair with rooms stacked along it, a bath
    or the laundry behind the stair on the spine. Where the stair stands away from the outside
    wall, a core of baths can sit between the spine and the stair (they need no window)."""
    for spine in ("L", "R"):
        for gap in (0.0, 5.5, 7.0, 8.5, 10.0):
            col = (sx - HALL - gap - a) if spine == "L" else (b - sx - STAIR_UW - HALL - gap)
            other_w = (b - sx - STAIR_UW) if spine == "L" else (sx - a)
            if col < BED_MIN or 0 < other_w < 5.0:
                continue
            for cell in (None, "bath", "laundry"):
                if cell and cell not in items:
                    continue
                rest = list(items)
                if cell:
                    rest.remove(cell)
                smalls = [i for i, it in enumerate(rest) if it in ("bath", "laundry")]
                cores = [()] if not gap else [c for n in (1, 2) for c in itertools.combinations(smalls, n)]
                for core_idx in cores:
                    core = [rest[i] for i in core_idx]
                    rest2 = [it for i, it in enumerate(rest) if i not in core_idx]
                    seen = set()
                    for perm in itertools.permutations(rest2):
                        for k in range(len(perm) + 1):
                            stack, seg = (list(perm[:k]), list(perm[k:]))
                            key = (tuple(stack), tuple(seg))
                            if key in seen or not stack or (seg and other_w < 5.0) or (other_w >= 5.0 and not seg):
                                continue
                            seen.add(key)
                            left, right = (stack, seg) if spine == "L" else (seg, stack)
                            for flip in (False, True):
                                rooms = _assemble(prog, W, D, sx, ys, a, b, pside, eP, other, eB, front, left,
                                                  right, rear_beds, rb, flip, spine=spine, cell=cell,
                                                  gap=gap, core=core)
                                if rooms is not None:
                                    yield rooms


def _front_suites(front_beds, fbaths, a, b, f):
    """Front bedrooms each with its own bath beside it (bath on the street, a walk-in behind it
    on the hall side), all facing the same way so a bath always meets the next bedroom."""
    n = len(front_beds)
    bw = 6.5
    w = (b - a) / n - bw
    if w < BED_MIN or max(w, f) / min(w, f) > 1.8:
        return None
    if f > BATH_LONG + 0.5 and f - BATH_LONG < 3.0:
        return None
    cells, x = [], a
    for i, (sp, ba) in enumerate(zip(front_beds, fbaths)):
        ww = snap(w) if i < n - 1 else b - x - bw
        cells.append(("bed", sp, x, ww))
        cells.append(("ensuite", ba, x + ww, bw))
        x += ww + bw
    return cells


def _front(front_beds, fb, a, b, f, pos=None):
    """Bedrooms across the front band, a shared bath at slot `pos` when given."""
    n = len(front_beds)
    bath_w = 7.0 if fb else 0.0
    w = (b - a - bath_w) / n
    if w < BED_MIN or w > 18.0 or max(w, f) / min(w, f) > 1.8:
        return None
    seq = [("bed", sp) for sp in front_beds]
    if fb:
        seq.insert(pos, ("bath", fb[0]))
    cells, x = [], a
    for i, (kind, sp) in enumerate(seq):
        ww = bath_w if kind == "bath" else snap(w)
        if i == len(seq) - 1:
            ww = b - x
        cells.append((kind, sp, x, ww))
        x += ww
    if cells[-1][0] == "bath" and abs(cells[-1][3] - bath_w) > 1.0:
        return None
    return cells


def _assemble(prog, W, D, sx, ys, a, b, pside, eP, other, eB, front, left, right, rear_beds, rb, flip,
              spine=None, cell=None, gap=0.0, core=()):
    f, R = ys - HALL, D - ys
    pr = prog.primary
    rooms: list[Room] = []
    # end columns
    def suite(x0, e, bed: Spec, bath: Spec, wic_name: str, bath_name: str, bath_out: bool):
        bd = snap(max(ys, D - 12.0))
        if D - bd < 6.5:
            bd = D - 6.5
        if bd < ys - 1e-6:
            return None
        bw = snap(min(9.0, max(5.5, e - 5.0)))
        ww = e - bw
        out = [Room(bed.name, "bedroom", x0, 0, e, bd)]
        rear = D - bd
        if ww < 4.0:
            out.append(Room(bath_name, "bath", x0, bd, e, rear))
            if wic_name.startswith("Walk-in Closet"):
                return None  # the primary needs its walk-in
        else:
            # the bath on the outside wall (window) or against the house, as asked
            on_left = (x0 == 0) == bath_out
            bx = x0 if on_left else x0 + ww
            cx = x0 + bw if on_left else x0
            out.append(Room(bath_name, "bath", bx, bd, bw, rear))
            out.append(Room(wic_name, "closet", cx, bd, ww, rear))
        return out
    if pr:
        p_bed, p_bath = pr[0], pr[1]
        p_wic = pr[2].name if len(pr) > 2 else "Walk-in Closet"
    if pside in ("L", "R"):
        x0 = 0.0 if pside == "L" else W - eP
        s = suite(x0, eP, p_bed, p_bath, p_wic, p_bath.name, flip)
        if s is None:
            return None
        rooms += s
    if other == "B":
        bsp = prog.bedrooms[0]
        num = bsp.name.split()[-1]
        x0 = 0.0 if a > 0 and (pside != "L") else W - eB
        if pside == "L":
            x0 = W - eB
        elif pside == "R":
            x0 = 0.0
        s = suite(x0, eB, bsp, prog.baths[0], f"Walk-in {num}", f"Ensuite {num}", not flip)
        if s is None:
            return None
        rooms += s
    # front band and hall
    for kind, sp, x, w in front:
        if kind == "bed":
            rooms.append(Room(sp.name, "bedroom", x, 0, w, f))
        elif kind == "ensuite":
            if f <= BATH_LONG + 0.5:
                rooms.append(Room(sp.name, "bath", x, 0, w, f))
            else:
                rooms.append(Room(sp.name, "bath", x, 0, w, BATH_LONG))
                rooms.append(Room(f"Walk-in {sp.name.split()[-1]}", "closet", x, BATH_LONG, w, f - BATH_LONG))
        else:
            if f <= BATH_LONG + 1.0:
                rooms.append(Room(sp.name, "bath", x, 0, w, f))
            else:
                rooms.append(Room("Linen", "closet", x, 0, w, f - BATH_LONG))
                rooms.append(Room(sp.name, "bath", x, f - BATH_LONG, w, BATH_LONG))
    rooms.append(Room("Hall", "hall", a, f, b - a, HALL))
    # the stair and what's behind it
    rooms.append(Room("Stair", "stair", sx, ys, STAIR_UW, STAIR_UL))
    behind = D - ys - STAIR_UL
    names = {"bed": [s for s in rear_beds], "bath": [s for s in rb]}
    if behind > 0.05:
        if spine and cell in ("bath", "laundry"):
            # behind the stair, on the spine hall: a bath or the laundry
            name = names["bath"].pop(0).name if cell == "bath" else "Laundry"
            rooms += _wet_cell(name, cell, sx, ys + STAIR_UL, STAIR_UW, behind)
        else:
            rooms.append(Room("Linen", "closet", sx, ys + STAIR_UL, STAIR_UW, behind))
    # rear band, either side of the stair (a spine hall down one side of it in a deep house,
    # with rooms stacked along it)
    if spine == "L":
        rooms.append(Room("Hall", "hall", sx - HALL - gap, ys, HALL, D - ys))
        spans = ((left, (a, sx - HALL - gap), True), (right, (sx + STAIR_UW, b), False))
        cx0 = sx - gap
    elif spine == "R":
        rooms.append(Room("Hall", "hall", sx + STAIR_UW + gap, ys, HALL, D - ys))
        spans = ((left, (a, sx), False), (right, (sx + STAIR_UW + HALL + gap, b), True))
        cx0 = sx + STAIR_UW
    else:
        spans = ((left, (a, sx), False), (right, (sx + STAIR_UW, b), False))
    if spine and gap:
        out = _core(list(core), cx0, gap, ys, D, names)
        if out is None:
            return None
        rooms += out
    for seg, (x0, x1), stacked in spans:
        if not seg:
            continue
        out = (_column if stacked else _segment)(seg, x0, x1, ys, D, names, pr, flip)
        if out is None:
            return None
        rooms += out
    return rooms


def _core(items, x0, w, ys, D, names):
    """Baths and the laundry one behind another between the spine hall and the stair (no
    windows needed), a linen cupboard filling what's left."""
    R = D - ys
    hs = [BATH_LONG if it == "bath" else 8.0 for it in items]
    if sum(hs) > R:
        k = R / sum(hs)
        hs = [snap(h * k) for h in hs]
        if any(h < 5.0 for h in hs):
            return None
    out, y = [], ys
    for it, h in zip(items, hs):
        name = names["bath"].pop(0).name if it == "bath" else "Laundry"
        if w > 12.5:
            return None
        out.append(Room(name, it, x0, y, w, h))
        y += h
    if D - y > 0.05:
        if D - y < 2.5 and out:
            out[-1].h += D - y
        else:
            out.append(Room("Linen", "closet", x0, y, w, D - y))
    return out


def _column(seg, x0, x1, ys, D, names, pr, flip):
    """Rooms one behind another down a spine hall, each the full width of the column."""
    cw = x1 - x0
    R = D - ys
    if cw < BED_MIN:
        return None
    small = {"bath": 7.5, "laundry": 6.5, "suite": 8.0, "primary": 9.0}
    fixed = [small.get(it, 0.0) for it in seg]
    flex = [i for i, it in enumerate(seg) if it in ("bed", "suite", "primary")]
    rest = R - sum(fixed)
    if not flex:
        return None if abs(rest) > 3.0 else _column_rooms(seg, [f + rest / len(seg) for f in fixed], x0, cw, ys, names, pr, flip)
    hs = list(fixed)
    wts = [1.4 if seg[i] == "primary" else 1.0 for i in flex]
    for i, wt in zip(flex, wts):
        hs[i] += snap(rest * wt / sum(wts))
    hs[-1] = R - sum(hs[:-1])
    return _column_rooms(seg, hs, x0, cw, ys, names, pr, flip)


def _column_rooms(seg, hs, x0, cw, ys, names, pr, flip):
    out = []
    y = ys
    for it, h in zip(seg, hs):
        if it == "bed":
            if h < BED_MIN or max(h, cw) / min(h, cw) > 1.8:
                return None
            out.append(Room(names["bed"].pop(0).name, "bedroom", x0, y, cw, h))
        elif it in ("bath", "laundry"):
            name = names["bath"].pop(0).name if it == "bath" else "Laundry"
            if h < 5.0:
                return None
            bw = min(cw, 9.0 if it == "bath" else 8.0)
            if cw - bw < 3.0:
                bw = cw
            bx = x0 if flip else x0 + cw - bw  # the spine side
            bx = x0 + cw - bw if flip else x0
            out.append(Room(name, it, bx if bw < cw else x0, y, bw, h))
            if bw < cw:
                out.append(Room("Linen", "closet", x0 + bw if bx == x0 else x0, y, cw - bw, h))
        elif it in ("suite", "primary"):
            tier = 8.0 if it == "suite" else 9.0
            bd = h - tier
            if bd < (BED_MIN if it == "suite" else 12.5) or max(bd, cw) / min(bd, cw) > 1.8:
                return None
            if it == "suite":
                sp = names["bed"].pop(0)
                names["bath"].pop(0)
                num = sp.name.split()[-1]
                bed_name, bath_name, wic_name = sp.name, f"Ensuite {num}", f"Walk-in {num}"
            else:
                bed_name, bath_name = pr[0].name, pr[1].name
                wic_name = pr[2].name if len(pr) > 2 else "Walk-in Closet"
            out.append(Room(bed_name, "bedroom", x0, y, cw, bd))
            bw = snap(min(9.0, max(5.5, cw - 5.0)))
            if cw - bw < 4.0:
                if it == "primary":
                    return None
                out.append(Room(bath_name, "bath", x0, y + bd, cw, tier))
            else:
                bx, cx = (x0, x0 + bw) if flip else (x0 + cw - bw, x0)
                out.append(Room(bath_name, "bath", bx, y + bd, bw, tier))
                out.append(Room(wic_name, "closet", cx, y + bd, cw - bw, tier))
        y += h
    return out


def _segment(seg, x0, x1, ys, D, names, pr, flip):
    """Rooms side by side across one stretch of the rear band, full depth."""
    R = D - ys
    width = x1 - x0
    fixed = {"bath": snap(min(9.0, max(5.0, 50.0 / min(R, BATH_LONG)))), "laundry": 6.5}
    want = []
    for it in seg:
        if it in fixed:
            want.append(fixed[it])
        else:
            want.append(None)
    flex = [i for i, w in enumerate(want) if w is None]
    rest = width - sum(w for w in want if w is not None)
    if not flex:
        # only small rooms: they share the stretch, within their limits
        k = width / sum(want)
        want = [snap(w * k) for w in want]
        if any(w > 9.0 or w < 5.0 for w in want):
            return None
    elif rest < BED_MIN * len(flex):
        # squeeze the small rooms toward their minimum to make room for the bedrooms
        short = BED_MIN * len(flex) - rest
        give = [max(0.0, w - 5.0) if w is not None else 0.0 for w in want]
        if sum(give) + 1e-6 < short:
            return None
        k = short / sum(give)
        want = [snap(w - g * k) if w is not None else None for w, g in zip(want, give)]
        rest = width - sum(w for w in want if w is not None)
        weights = [2.2 if seg[i] == "primary" else 1.0 for i in flex]
        for i, wt in zip(flex, weights):
            want[i] = snap(rest * wt / sum(weights))
    else:
        weights = [2.2 if seg[i] == "primary" else 1.0 for i in flex]
        for i, wt in zip(flex, weights):
            want[i] = snap(rest * wt / sum(weights))
    # close the last gap exactly
    want[-1] = width - sum(want[:-1])
    out = []
    x = x0
    for it, w in zip(seg, want):
        if it == "bed":
            if w < BED_MIN or max(w, R) / min(w, R) > 1.8:
                return None
            sp = names["bed"].pop(0)
            out.append(Room(sp.name, "bedroom", x, ys, w, R))
        elif it == "suite":
            # a bedroom on the hall, its own bath (and a walk-in) behind it on the back wall
            bh = snap(min(BATH_LONG, max(6.0, R - 14.0)))
            bd = R - bh
            if w < BED_MIN or bd < 10.0 or max(w, bd) / min(w, bd) > 1.8:
                return None
            sp = names["bed"].pop(0)
            names["bath"].pop(0)
            num = sp.name.split()[-1]
            out.append(Room(sp.name, "bedroom", x, ys, w, bd))
            bw = snap(min(9.0, max(5.5, w - 5.0)))
            if w - bw >= 4.0:
                bx, cx = (x, x + bw) if flip else (x + w - bw, x)
                out.append(Room(f"Ensuite {num}", "bath", bx, ys + bd, bw, bh))
                out.append(Room(f"Walk-in {num}", "closet", cx, ys + bd, w - bw, bh))
            else:
                out.append(Room(f"Ensuite {num}", "bath", x, ys + bd, w, bh))
        elif it == "bath":
            sp = names["bath"].pop(0)
            out += _wet_cell(sp.name, "bath", x, ys, w, R)
        elif it == "laundry":
            out += _wet_cell("Laundry", "laundry", x, ys, w, R)
        elif it == "primary":
            bw = 8.0
            bed_w = w - bw
            if bed_w < 12.5 or max(bed_w, R) / min(bed_w, R) > 1.7:
                return None
            bx, px = (x, x + bw) if flip else (x + bed_w, x)
            out.append(Room(pr[0].name, "bedroom", px, ys, bed_w, R))
            long = min(R, 11.0)
            out.append(Room(pr[1].name, "bath", bx, ys, bw, long))
            if R - long >= 3.5:
                out.append(Room(pr[2].name if len(pr) > 2 else "Walk-in Closet", "closet", bx, ys + long, bw, R - long))
            elif len(pr) > 2:
                return None
            else:
                out[-1].h = R
        x += w
    return out


def _wet_cell(name, kind, x, y, w, R):
    if R <= BATH_LONG + 1.0:
        return [Room(name, kind, x, y, w, R)]
    return [Room(name, kind, x, y, w, BATH_LONG), Room("Linen", "closet", x, y + BATH_LONG, w, R - BATH_LONG)]


# -- scoring --------------------------------------------------------------------------------

def _walls(rooms: list[Room]) -> list[tuple[str, float, float, float]]:
    out = []
    for r in rooms:
        out.append(("x", r.x, r.y, r.y + r.h))
        out.append(("x", r.x + r.w, r.y, r.y + r.h))
        out.append(("y", r.y, r.x, r.x + r.w))
        out.append(("y", r.y + r.h, r.x, r.x + r.w))
    return out


def _over_wet(r: Room, wet: list[Room]) -> bool:
    for w in wet:
        ix = min(r.x + r.w, w.x + w.w) - max(r.x, w.x)
        iy = min(r.y + r.h, w.y + w.h) - max(r.y, w.y)
        if ix > 0 and iy > 0 and ix * iy > 6:
            return True
        dx = max(0.0, max(r.x, w.x) - min(r.x + r.w, w.x + w.w))
        dy = max(0.0, max(r.y, w.y) - min(r.y + r.h, w.y + w.h))
        if (dx * dx + dy * dy) ** 0.5 < 3.0:
            return True
    return False


def _touch(a: Room, b: Room) -> float:
    """Length of the wall two rooms share (0 when they don't)."""
    if abs(a.x + a.w - b.x) < 1e-6 or abs(b.x + b.w - a.x) < 1e-6:
        return max(0.0, min(a.y + a.h, b.y + b.h) - max(a.y, b.y))
    if abs(a.y + a.h - b.y) < 1e-6 or abs(b.y + b.h - a.y) < 1e-6:
        return max(0.0, min(a.x + a.w, b.x + b.w) - max(a.x, b.x))
    return 0.0


def score(rooms: list[Room], wet: list[Room], walls, prog: Program, W: float = 0.0, D: float = 0.0,
          wing_side: Optional[str] = None) -> Optional[float]:
    from .details import _shape_ok
    s = 0.0
    W = W or max(r.x + r.w for r in rooms)
    D = D or max(r.y + r.h for r in rooms)

    def outside(r: Room) -> float:
        """Length of outside wall a room has (windows)."""
        n = 0.0
        if r.y < 0.01 or abs(r.y + r.h - D) < 0.01:
            n += r.w
        if r.x < 0.01 and wing_side != "L":
            n += r.h
        if abs(r.x + r.w - W) < 0.01 and wing_side != "R":
            n += r.h
        return n
    for r in rooms:
        if r.kind == "bedroom" and outside(r) < 3.5:
            return None  # a bedroom needs a window to climb out of
    halls = [r for r in rooms if r.kind in ("hall", "stair")]
    for r in rooms:
        if r.kind in ("hall", "stair"):
            continue
        n = r.name.lower()
        if r.kind == "bedroom" or (r.kind in ("bath", "laundry") and not ("ensuite" in n or n.startswith("primary"))):
            if not any(_touch(r, h) >= 2.6 for h in halls):
                return None  # no door onto the hall
        elif r.kind == "closet" and r.name in ("Linen", "Laundry"):
            if not any(_touch(r, o) >= 2.6 for o in rooms if o.kind in ("hall", "bath", "bedroom", "stair")):
                return None
    area = sum(r.area for r in rooms) or 1.0
    beds = [r for r in rooms if r.kind == "bedroom"]
    baths = [r for r in rooms if r.kind == "bath"]
    for r in beds:
        lo, hi = sorted((r.w, r.h))
        if lo < 9.5 or hi / lo > 2.1:
            return None
        if lo < 10:
            s += 15
        if hi / lo > 1.8:
            s += 15
        target = next((sp.target for sp in prog.bedrooms + prog.primary[:1] if sp.name == r.name), 140.0)
        s += 10.0 * abs(r.area - target) / target
    prim = next((r for r in beds if r.name.startswith("Primary")), None)
    others = [r.area for r in beds if r is not prim]
    if prim is None and prog.primary:
        return None
    if others and prim is not None:
        if prim.area < max(others) + 6.0:
            return None  # (the suites would trade names: details.primary_biggest)
        if prim.area < 1.15 * max(others):
            s += 20
    for r in rooms:
        if r.kind in ("bath", "laundry", "closet") and not _shape_ok(r):
            s += 40
    for r in baths:
        if not _over_wet(r, wet):
            s += 15
    for i, a in enumerate(baths):
        for c in baths[i + 1:]:
            if _touch(a, c) > 2.0:
                return None  # twin baths
            # a row: only closets between two baths, under 5'
            gap = [r for r in rooms if r.kind not in ("bath",) and _touch(r, a) > 2 and _touch(r, c) > 2]
            if gap and all(r.kind == "closet" and min(r.w, r.h) < 5 for r in gap):
                s += 60
    closets = sum(r.area for r in rooms if r.kind == "closet") / area
    s += 200.0 * max(0.0, closets - 0.12)
    halls = [r for r in rooms if r.kind == "hall"]
    share = sum(r.area for r in halls) / area
    s += 300.0 * max(0.0, share - 0.12)
    s += 10.0 * sum(max(r.w, r.h) > 30 for r in halls)
    # walls standing on walls below
    lines = {}
    for ax, c, lo, hi in walls:
        lines.setdefault(ax, []).append((c, lo, hi))
    miss = 0.0
    for ax, c, lo, hi in _walls(rooms):
        if c < 0.05 or (ax == "x" and abs(c - max(r.x + r.w for r in rooms)) < 0.05) or \
                (ax == "y" and abs(c - max(r.y + r.h for r in rooms)) < 0.05):
            continue
        under = sum(max(0.0, min(hi, h2) - max(lo, l2)) for c2, l2, h2 in lines.get(ax, []) if abs(c2 - c) < 0.6)
        miss += max(0.0, (hi - lo) - under)
    s += 0.15 * miss / 2  # each wall is counted from both rooms
    return s


__all__ = ["plan", "score"]
