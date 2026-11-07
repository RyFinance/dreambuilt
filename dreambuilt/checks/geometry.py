"""Geometric and constructional consistency of the one building model every drawing comes
from. These are hard constraints: when one fails, the plans and elevations can't agree.

G1 rooms on a floor never overlap
G2 every door and window sits on a real exterior wall of its floor, and no two openings on
   the same wall overlap
G3 the roofs cover every part of every floor (nothing left open to the sky)
G4 every upper-floor room stands on something: a room or the garage below (2' cantilevers allowed)
G5 floor-to-floor alignment: an upper floor's outside walls sit over walls below (advisory)
"""
from __future__ import annotations

from shapely.geometry import box
from shapely.ops import unary_union

from ..model import House


def check(house: House) -> list:
    from . import Finding
    from ..views.scene import place_opening
    out: list = []
    bad = 0
    for lv in house.all_levels:
        rooms = [r for r in lv.rooms if r.kind != "void"]
        # G1
        for i, a in enumerate(rooms):
            ra = a.rect
            for b in rooms[i + 1:]:
                ov = ra.intersection(b.rect).area
                if ov > 0.5:
                    out.append(Finding("G1 no overlaps", "fail", f"{lv.name}: {a.name} / {b.name}",
                                       f"rooms overlap by {ov:.0f} sq ft"))
                    bad += 1
        # G2
        spans: dict = {}
        for op in lv.openings:
            if op.kind == "garage" or op.face not in "NSEW":
                continue
            pl = place_opening(lv, op)
            if pl is None:
                out.append(Finding("G2 openings on walls", "fail", f"{lv.name}: {op.kind} {op.face}",
                                   f"at {op.start:g}' there is no exterior wall to carry it"))
                bad += 1
                continue
            (px, py), (qx, qy) = pl.plan_points()
            key = (op.face, round(px if op.face in "EW" else py, 1))
            lo, hi = (min(px, qx), max(px, qx)) if op.face in "NS" else (min(py, qy), max(py, qy))
            for (a0, a1) in spans.get(key, []):
                if min(hi, a1) - max(lo, a0) > 0.1:
                    out.append(Finding("G2 openings on walls", "fail", f"{lv.name}: {op.face} wall",
                                       f"two openings overlap at {lo:g}'-{hi:g}'"))
                    bad += 1
            spans.setdefault(key, []).append((lo, hi))
    # G3: the roof outline covers every floor
    if house.roofs:
        from ..roof.analytic import eave_rect
        cover = unary_union([eave_rect(m) for m in house.roofs]).buffer(0.05)
        for lv in house.levels:
            gap = lv.footprint.difference(cover).area
            if gap > 1.0:
                out.append(Finding("G3 roof covers plan", "fail", lv.name,
                                   f"{gap:.0f} sq ft of the floor has no roof over it"))
                bad += 1
    # G4 / G5: each floor stands on the one below
    for below, above in zip(house.levels, house.levels[1:]):
        # (a cantilever up to 2' is ordinary framing: the floor over a recessed garage door)
        base = unary_union([r.rect for r in below.rooms]).buffer(2.05, join_style=2)
        for r in above.rooms:
            hang = r.rect.difference(base).area
            if hang > 2.0:
                out.append(Finding("G4 floors supported", "fail", f"{above.name}: {r.name}",
                                   f"{hang:.0f} sq ft stands on nothing below"))
                bad += 1
        # (over a garage, the wall may sit on the 2' cantilever over the recessed door, as G4
        # allows)
        edges_below = unary_union([r.rect.exterior.buffer(2.05 if r.kind == "garage" else 0.3)
                                   for r in below.rooms])
        ring = above.footprint.exterior
        on = ring.intersection(edges_below).length / max(ring.length, 1e-6)
        if on < 0.9:
            out.append(Finding("G5 walls stack", "warn", above.name,
                               f"only {on:.0%} of the outside walls sit over walls below"))
    if not bad:
        out.append(Finding("G1-G4 geometry", "pass", "Model",
                           "rooms, openings, roofs and floors agree"))
    return out
