"""Brief -> house: program, layout variants, details, scoring.

    from dreambuilt.brief import parse_text
    from dreambuilt.design import design
    house = design(parse_text("2 story colonial 4 bed 2.5 bath 2400 sqft 70x140"))
"""
from __future__ import annotations

import itertools
from typing import Optional
import math
from dataclasses import dataclass

from .. import checks, styles
from ..brief import DesignBrief
from ..model import Brief, House, Level, RoofMass, Room
from . import details, layout, wing as wings
from .program import build_program


class BriefError(ValueError):
    pass


@dataclass
class Option:
    house: House
    score: float
    notes: list[str]


def footprint(b: DesignBrief, style: dict, fireplace: bool) -> tuple[float, float]:
    """Width and depth of the rectangle each floor sits in."""
    per = b.sqft / b.stories
    aspect = style.get("layout", {}).get("aspect", 1.4)
    if b.wants("wide"):
        aspect *= 1.35  # "wider than it is long": more frontage, shallower rooms
    if b.stories == 1:
        aspect = max(aspect, 1.45)  # a one-storey wants length for its bedroom wing (even a "foursquare")
    D = math.sqrt(per / aspect)
    # two storeys: deep enough for front rooms, the hall, a U stair and a mudroom behind it
    if b.stories > 1:
        D = max(D, min(31.5, per / 30.0), 26.0)  # small plans stay at least 30' wide
    else:
        D = max(D, 24.0)
    W = per / D
    buildable = b.lot_width - 10.0 - (2.0 if fireplace else 0.0)
    if W > buildable:
        W = buildable
        D = per / W
    porch = style.get("layout", {}).get("porch_depth", 8)
    if b.stories == 1 and D > (50 if getattr(b, "_tandem", False) else 44):
        raise BriefError(f"a {b.sqft:,} sq ft one-storey would be {D:.0f}' deep on a {b.lot_width:g}' lot; "
                         "try two storeys or a wider lot")
    if D > b.lot_depth - 45 - porch - 2:
        raise BriefError(f"{b.sqft:,} sq ft over {b.stories} floor(s) does not fit a "
                         f"{b.lot_width:g}' x {b.lot_depth:g}' lot with standard setbacks")
    snap = lambda v: round(v * 2) / 2
    return snap(W), snap(D)


def build_estate(b: DesignBrief, mirror: bool, variant: bool, style: dict) -> House:
    from . import basement, estate
    from ..model import Opening
    import copy
    above = b
    if b.basement:
        # the basement holds roughly a main floor's worth of the total, or the size asked for
        above = copy.copy(b)
        above.sqft = int(b.sqft - b.basement_sqft) if b.basement_sqft else int(round(b.sqft / 1.62))
    floors, ex = estate.plan(above, variant or b.wants("open plan"))
    W, D = ex["W"], ex["D"]
    bex = dict(ex)
    if b.basement_sqft:
        # a small basement: only as deep as its size needs (the rest stays on fill)
        if not b.suites:
            bex["W"] = ex["xc"]  # under the living side only, nothing under the garage
        bex["D"] = max(16.0 + 12.0, min(D, round(b.basement_sqft / bex["W"] * 2) / 2))
    base_rooms = basement.plan(bex, b.suites, b.features) if b.basement else []
    if mirror:
        estate.mirror(floors + ([base_rooms] if base_rooms else []), W)
    fz = float(style.get("floor_z", 1.0))
    if b.basement:
        fz = 3.5  # main floor up over a daylight basement: five or six steps to the door
    ceil = float(b.ceiling or style.get("ceiling", 10.0))
    levels = [Level(n, fz + i * (ceil + 1.0), ceil if i == 0 else min(ceil, 10.0), rooms=rooms)
              for i, (n, rooms) in enumerate(zip(["Main Floor", "Upper Floor"], floors))]
    if "big windows" in b.features or "big-windows" in style.get("details", []):
        style = dict(style, windows=dict(style.get("windows", {}), big=True, head_height=8.5))
    ex["gable_pitch"] = (10, 12, 9)[_pick(b, "gable", 3)]
    ex["grand"] = b.wants("grand entrance")
    roofs, porches, balconies = estate.roofs_and_porches(ex, style, floors, levels, b.features)
    great, foyer, garage = ex["great"], ex["foyer"], ex["garage"]
    # the chase runs up to the eave over it: the wing's on a half upper, the upper floor's otherwise
    eave = levels[0].plate_z if ex["half"] or ex["living"].y < -0.1 else levels[1].plate_z
    chimney = details.make_chimney(ex["hearth"], W, eave) if b.has("fireplace") else None
    details.use_open_plan(ex["open"])
    details.primary_biggest(levels)
    for lv in levels:
        lv.rooms = details.split_long(lv.rooms)
    details.primary_biggest(levels)  # split_long can trim the primary too
    from .. import edit as _edit
    for lv in levels:
        _edit.widen_primary(lv.rooms)
    details.absorb_closets(levels)
    for i, lv in enumerate(levels):
        details.use_footprint(lv.footprint)
        lv.doors = details.make_doors(lv.rooms)
        span = (chimney.y, chimney.y + chimney.h) if (chimney and i == 0) else None
        lv.openings = details.make_openings(lv, W, D, style, i == 0, foyer.x + foyer.w / 2,
                                            chimney.hearth_wall if span else None, span)
        if i == 0:
            # garage doors to grade, French doors from the great room to the deck
            g = garage
            # two singles or one double: chosen per brief, so streets of these don't repeat
            singles = _pick(b, "garage-doors", 2) == 1 and g.w >= 21
            widths = [16.0, 9.0] if ex["cars"] == 3 else ([8.0, 8.0] if singles else [16.0])
            gap = (g.w - sum(widths)) / (len(widths) + 1)
            x = g.x + gap
            for w in widths:
                lv.openings.append(Opening("garage", "S", x, w, 8.0, -fz, operation="overhead",
                                           line=g.y))
                x += w + gap
            deck = porches[1]
            ds = deck.x + deck.w / 2 - 3
            # the patio doors onto the deck replace any window where they land
            lv.openings = [o for o in lv.openings if not (o.face == "N" and o.kind == "window" and
                                                          o.start < ds + 6.5 and o.start + o.width > ds - 0.5)]
            lv.openings.append(Opening("door", "N", ds, 6.0, 7.5, operation="swing", line=D))
        if ex.get("grand"):
            ent = next((r for r in roofs if r.name == "Entry"), None)
            if i == 0:
                for o in lv.openings:
                    if o.kind == "door" and o.face == "S" and o.width < 5:
                        o.start, o.width = o.start - 1.5, 6.0  # double front doors
            elif ent is not None:
                lv.openings = [o for o in lv.openings if not (o.face == "S" and o.start < ent.x + ent.w + 0.5
                                                              and o.start + o.width > ent.x - 0.5)]
        if i == 1 and ex["half"]:
            # the upper wall facing the wing sits behind its roof: windows there would be
            # half hidden, so that wall stays clean (fans vent the rooms behind it)
            toward = "W" if ex["living"].x < 1e-6 else "E"
            lv.openings = [o for o in lv.openings if o.face != toward]
        lv.fixtures = details.make_fixtures(lv, W, D, upper=i > 0)
        details.use_footprint(None)
    details.even_windows(levels)
    details.align_windows(levels)
    details.even_windows(levels)  # aligning can crowd two windows: merge them
    details.daylight(levels)
    details.use_open_plan(False)
    if ex["open"]:
        notes_open = ["Open concept: great room, kitchen and nook share one space."]
    else:
        notes_open = ["Separate great room and kitchen, joined by wide cased openings."]
    base_level = basement.build_level(base_rooms, fz, W, bex["D"]) if base_rooms else None
    name = b.name or f"Plan {b.style[:2].upper()}-{b.sqft}"
    from shapely.ops import unary_union
    outline = unary_union([lv.footprint for lv in levels]).bounds
    lot = details.make_lot(b.lot_width, b.lot_depth, outline[2], D, -outline[1] + 6,
                           chimney.hearth_wall if chimney else None, "Main Street")
    notes = [f"Generated from the brief: {b.summary()}."] + notes_open
    notes += [f"Style detail: {d.replace('-', ' ')}." for d in style.get("details", [])[:3]]
    roofs = roofs + details.cover_gaps(levels, roofs)
    details.drop_unplaced(levels)
    return House(name=name, style=b.style, levels=levels, roofs=roofs, porches=porches,
                 claddings=estate.claddings(ex, style, b.features),
                 chimneys=[chimney] if chimney else [], balconies=balconies, basement=base_level, lot=lot,
                 brief=Brief(style["name"], b.stories, b.beds, b.baths, b.sqft,
                             lot=f"{b.lot_width:g}' x {b.lot_depth:g}'", must_haves=list(b.must_haves)),
                 notes=notes)


def _pick(b: DesignBrief, what: str, n: int) -> int:
    """A stable choice among n for this brief (same brief, same answer)."""
    import zlib
    return zlib.crc32(f"{what}|{b.summary()}|{b.name}".encode()) % n


def copy_with(b: DesignBrief, **kw) -> DesignBrief:
    import copy
    out = copy.copy(b)
    for k, v in kw.items():
        setattr(out, k, v)
    return out


def _styled(style: dict, b: DesignBrief) -> dict:
    """The style with the client's asks folded in: roof shape, big windows."""
    from .estate import roof_kind
    kind = roof_kind(style, b.features)
    roof = dict(style.get("roof", {}))
    if kind == "flat":
        roof.update(kind="shed", pitch=0.25, overhang=max(roof.get("overhang", 1.5), 2.5))
    elif kind != roof.get("kind"):
        roof.update(kind=kind, pitch=max(roof.get("pitch", 6), 6 if kind == "gable" else 5))
    if b.wants("dormers") and roof.get("kind") in ("gable", "hip"):
        roof.update(kind="gable", pitch=max(roof.get("pitch", 6), 10))  # steep enough to stand a dormer in
    out = dict(style, roof=roof)
    if "big windows" in b.features or "big-windows" in style.get("details", []):
        out["windows"] = dict(style.get("windows", {}), big=True,
                              head_height=max(style.get("windows", {}).get("head_height", 7.0), 8.0))
    return out


def _dormers(b: DesignBrief, style: dict, main, W: float, porch) -> tuple[list, list]:
    """Gabled dormers on the street slope of a side-gabled roof: asked for, or the Cape Cod
    colonial / craftsman bungalow way. Kept clear of the porch gable."""
    from ..model import Dormer
    asked = b.wants("dormers")
    natural = b.stories == 1 and b.style in ("colonial", "craftsman") and not b.wants("flat roof")
    if not (asked or natural) or main.kind != "gable" or main.ridge != "x" or main.pitch < 6:
        return [], []
    p, pz = main.pitch, main.plate_z
    rise = lambda dy: dy * p / 12
    if rise(main.h / 2) < 7.0:
        return [], []  # too low a roof for a window to stand in it
    yd = 2.5
    base = pz + rise(yd)
    w, dp = 6.0, 12.0
    plate = base + 4.5
    ridge = plate + (w / 2) * dp / 12
    if ridge > pz + rise(main.h / 2) - 1.0:
        return [], []
    back = (ridge - pz) * 12 / p + 1.0
    n = 2 if W >= 38 else 1
    xs = [W * (i + 1) / (n + 1) - w / 2 for i in range(n)]
    xs = [x for x in xs if x + w < porch.x - 1.5 or x > porch.x + porch.w + 1.5] or \
        ([W * 0.2] if porch.x > W / 2 else [W * 0.8 - w])
    dormers, roofs = [], []
    for i, x in enumerate(xs):
        dormers.append(Dormer(x, yd, w, base, plate))
        roofs.append(RoofMass(f"Dormer {i + 1}", x, yd, w, back - yd, kind="gable", ridge="y", pitch=dp,
                              overhang=0.6, plate_z=plate, gable_ends=("S",)))
    return dormers, roofs


def _claddings(b: DesignBrief, style: dict, n_levels: int) -> list:
    from ..model import Cladding
    out = []
    if "stone" in b.features:
        out.append(Cladding(0, "S", -1e3, 1e3, "stone"))
    elif "brick" in b.features:
        out.append(Cladding(0, "S", -1e3, 1e3, "brick"))
    if "wood" in b.features and n_levels > 1:
        out.append(Cladding(n_levels - 1, "S", -1e3, 1e3, "wood"))
    elif "board and batten" in b.features:
        out += [Cladding(i, f, -1e3, 1e3, "board-and-batten") for i in range(n_levels) for f in "SNEW"]
    return out


def build_micro(b: DesignBrief, mirror: bool, style: dict) -> House:
    """A townhouse on a tiny or narrow lot, the whole buildable footprint on each floor."""
    from . import micro
    from ..model import Opening
    style = _styled(style, b)
    W, D = micro.footprint(b)
    fz = float(style.get("floor_z", 1.0))
    ceil = float(b.ceiling or min(9.0, style.get("ceiling", 9.0)))  # 9' keeps the stair short
    floors = micro.plan(b, W, D, mirror, ftf=ceil + 1.0)
    levels = [Level(["First Floor", "Second Floor", "Third Floor"][i], fz + i * (ceil + 1.0), ceil, rooms=rooms)
              for i, rooms in enumerate(floors)]
    main = details.make_roof(style, W, D, levels[-1].plate_z)
    entry = next(r for r in levels[0].rooms if r.kind == "entry")
    door_x = entry.x + entry.w / 2
    # the front yard is tiny: the canopy and step stay on the lot
    front_yard = micro.setbacks(b)[0]
    lay = dict(style.get("layout", {}), porch_depth=max(1.5, front_yard), porch_width=6.0)
    porch, porch_roofs = details.make_porch(dict(style, layout=lay), W, D, fz, levels[0].plate_z, door_x,
                                            b.stories, False)
    for i, lv in enumerate(levels):
        details.use_footprint(lv.footprint)
        lv.doors = details.make_doors(lv.rooms)
        lv.openings = details.make_openings(lv, W, D, style, i == 0, door_x, None, None)
        gar = next((r for r in lv.rooms if r.kind == "garage"), None)
        if i == 0 and gar is not None:
            # a tuck-under garage: its overhead door on the street, no window there
            gw = min(9.0, gar.w - 2.0)
            lv.openings = [o for o in lv.openings if not (o.face == "S" and o.kind == "window"
                                                          and gar.x - 0.5 < o.start < gar.x + gar.w)]
            lv.openings.append(Opening("garage", "S", gar.x + (gar.w - gw) / 2, gw, 7.5, -fz,
                                       operation="overhead", line=gar.y))
        lv.fixtures = details.make_fixtures(lv, W, D, upper=i > 0)
        details.use_footprint(None)
    details.even_windows(levels)
    details.align_windows(levels)
    details.even_windows(levels)  # aligning can crowd two windows: merge them
    details.daylight(levels)
    yards = micro.setbacks(b)
    lot = details.make_lot(b.lot_width, b.lot_depth, W, D, 0.0, None, "Main Street", yards=yards)
    f, r, sd = yards
    notes = [f"Generated from the brief: {b.summary()}.",
             f"Lot {b.lot_width:g}' x {b.lot_depth:g}' kept as given: {f:g}' front and {r:g}' rear yards, "
             f"{'zero side setbacks (townhouse / infill, party walls need fire separation)' if sd == 0 else f'{sd:g} side yards'}"
             f" leave a {W:g}' x {D:g}' footprint ({W * D:,.0f} sq ft a floor). Confirm with the local zoning bylaw."]
    if b.wants("roof terrace"):
        notes.append("Rooftop terrace: possible on the flat roof over the stair (guard rail, structure to confirm).")
    notes += [f"Detail: {w}." for w in b.wishes[:12]]
    return House(name=b.name or f"Plan {b.style[:2].upper()}-{round(sum(lv.heated_area for lv in levels))}",
                 style=b.style, levels=levels, roofs=[main] + porch_roofs, porches=[porch], lot=lot,
                 claddings=_claddings(b, style, len(levels)),
                 brief=Brief(style["name"], b.stories, b.beds, b.baths, round(sum(lv.heated_area for lv in levels)),
                             lot=f"{b.lot_width:g}' x {b.lot_depth:g}'", must_haves=list(b.must_haves)),
                 notes=notes)


def build(b: DesignBrief, mirror: bool, variant: bool, preset: Optional[list] = None,
          preset_name: str = "", genome: Optional[dict] = None) -> House:
    """One design. `genome` holds the candidate engine's choices (see candidates.py); a key
    that's missing falls back to the house type's usual answer, and nothing in it ever
    overrides what the client asked for."""
    g_ = genome or {}
    style = styles.get(b.style)
    from . import estate
    above = b
    if b.basement:
        import copy
        above = copy.copy(b)
        above.sqft = int(b.sqft - b.basement_sqft) if b.basement_sqft else int(round(b.sqft / 1.62))
    if estate.applies(above, style) and g_.get("estate", True):
        return build_estate(b, mirror, variant, style)
    from . import micro
    if micro.applies(b) and micro.footprint(b) and b.stories >= 2 and not b.basement:
        return build_micro(b, mirror, style)
    full = b
    if b.basement:
        # the basement holds about one floor's worth of the total
        import copy
        b = copy.copy(b)
        b.sqft = int(full.sqft - full.basement_sqft) if full.basement_sqft else \
            int(round(full.sqft * b.stories / (b.stories + 1)))
    fire = b.has("fireplace")
    style = _styled(style, b)
    lot_full = b.lot_width
    above_total = b.sqft
    want_garage = b.garage == "side" or (b.garage == "auto" and (b.has("garage") or b.cars))
    if b.stories == 2 and b.primary_floor == "main" and not want_garage and b.lot_width - 34.0 >= 32:
        b = copy_with(b, lot_width=b.lot_width - 24.0)  # room beside the house for the primary wing
    if want_garage:
        # keep the garage's width free on the lot before the house is sized; the bonus room
        # over it counts toward the house's size
        from . import garage as garages
        bonus = garages.width(b.cars) * garages.DEPTH * (b.stories - 1)
        b0 = b
        b = copy_with(b, lot_width=b.lot_width - garages.width(b.cars),
                      sqft=int(b.sqft - bonus) if b.sqft - bonus > 900 * b.stories else b.sqft)
    tandem = False
    try:
        W, D = footprint(b, style, fire)
    except BriefError:
        if not (want_garage and b.stories == 1 and b.cars != 1):
            raise
        # a one-storey on a narrow lot stays one storey: the cars park nose to tail in a
        # one-car-wide garage beside it
        tandem = True
        b = copy_with(b0, lot_width=b0.lot_width - garages.width(1))
        b._tandem = True
        W, D = footprint(b, style, fire)
    prog = build_program(b)
    fz = float(style.get("floor_z", 2.0))
    if full.basement:
        fz = 3.0  # main floor up over a daylight basement
    ceil = float(b.ceiling or style.get("ceiling", 9.0))
    known_doors = None
    gar, suite, over, blocks = None, [], None, []
    if b.stories == 1 and preset is not None:
        preset, known_doors = preset
        floors = [preset]
        x0, y0, x1, y1 = Level("_", 0, 9, rooms=preset).footprint.bounds
        W, D = x1, y1
    elif b.stories == 1:
        split = None
        if variant and not g_.get("plan1"):
            # the split-bedroom plan wants frontage: re-shape the box wider for it
            from . import bungalow
            sw = min(math.sqrt(b.sqft * 1.8), b.lot_width - 10.0 - (2.0 if fire else 0.0))
            sw = round(sw * 2) / 2
            sd = round(b.sqft / sw * 2) / 2
            split = bungalow.plan(b, sw, sd, stair=full.basement, dining_front=not mirror)
            if split is not None:
                W, D = sw, sd
                if mirror:
                    bungalow.mirror(split, W)
        plan1 = g_.get("plan1")
        if split is None and plan1 in ("ell", "ell-side", "courtyard"):
            from . import wings1
            got = wings1.plan(prog, b, W, D, mirror, kind=plan1, stair=full.basement,
                              lot_w=lot_full - 10.0 - (2.0 if fire else 0.0))
            if got is None:
                raise BriefError(f"no {plan1} plan for this brief")
            floors, W, D, blocks = [got[0]], got[1], got[2], got[3]
            gar = next((r for r in got[0] if r.kind == "garage"), None)
        elif split is None and W < 42 and D >= 33 and b.sqft <= 1600 and b.beds <= 2 and len(prog.primary) >= 2:
            # a small house on a narrow lot: side-by-side rooms off a centre hall
            floors = [layout.one_story_compact(prog, W, D, mirror, stair=full.basement)]
        elif split is None and W < 40 and D >= 47:
            # a narrow lot: front-to-back plan with a hall down the middle
            floors = [layout.one_story_narrow(prog, W, D, mirror, stair=full.basement)]
        else:
            floors = [split or layout.one_story(prog, W, D, mirror, dining_front=variant, stair=full.basement)]
    else:
        from .layout import HALL, STAIR_UL, STAIR_UW
        # every floor its own size: the main floor runs out the back under a one-storey roof,
        # the floor above is shallower, a third floor shallower again
        snap = lambda v: round(v * 2) / 2
        # areas first: the main floor takes an extra share that runs out the back under a
        # one-storey roof; the upper floor gets what its bedrooms need; a third floor is smaller
        n = b.stories
        from . import garage as garages, wing as wings
        gw = garages.width(b.cars) if want_garage else 0.0
        # the floor over a built-in garage holds real rooms (bedrooms, a bath), counted upstairs
        gtop = gw * (garages.DEPTH + garages.RECESS) if want_garage else 0.0
        # the client's word decides the primary's floor; when they gave none, the candidate
        # engine may try it downstairs
        prim_main = n == 2 and (b.primary_floor == "main" or
                                (b.primary_floor == "auto" and g_.get("primary") == "main"))
        pw = sum(s.target for s in prog.primary) * 1.12 if prim_main else 0.0
        upstairs = (sum(s.target for s in prog.bedrooms + prog.primary + prog.baths) + 77) * 1.22
        # floors stay the same size unless the client asks for a bigger main floor / rear addition
        extra = (0.06, 0.09, 0.12)[_pick(b, "rear", 3)] if b.wants("rear addition") else 0.0
        spare = (above_total / n - upstairs / (n - 1) * (1.0 if n == 2 else 0.8)) / above_total * n / (n - 1)
        extra = min(extra, spare) if spare >= 0.04 else 0.0
        main_total = above_total * (1.0 / n + extra)
        main_a = main_total - pw  # a main-floor primary gets its own wing at the back
        rest = above_total - main_total
        if n == 3 and b.wants("rear addition"):
            up_a, top_a = rest * 0.56, rest * 0.44
        elif n == 3:
            up_a = top_a = rest / 2
        else:
            up_a = top_a = rest
        up0, top0 = up_a, top_a
        for g in ((gtop, 0.0) if gtop else (0.0,)):
            up_a, top_a = max(up0 - g, up0 * 0.55), max(top0 - g, top0 * 0.55)
            buildable = b.lot_width - 10.0 - (2.0 if fire else 0.0)
            # keep the upper floor a good width for its rooms; the main floor's extra depth is
            # capped so it never turns into a bowling alley
            wmin = 36.0 if style.get("layout", {}).get("symmetric") else 32.0  # centre-hall needs 36'
            # wide enough for the main floor too (a main floor deeper than ~40' turns into corridors)
            W = min(buildable, max(wmin, up_a / 32.5, main_a / 40.0 if n == 2 else 0.0))
            if up_a / W < 28.5 and (n > 2 or main_a / W < 31.5):
                # a small upper floor: narrower rather than too shallow for rooms + hall + stair
                W = up_a / 28.5
            W = snap(W)
            D_up = snap(max(up_a / W, 28.5 if n == 2 else 0.0))
            # centre-hall plans keep two rooms a side, so only while the main floor is shallow enough
            # (a main-floor primary the client asked for beats the style's centre hall)
            core = g_.get("core")
            if "entry:center" in (b.rules or []):
                core = "center"  # the client wants the front door in the middle
            centered = (style.get("layout", {}).get("symmetric", False) if core is None else core == "center") \
                and W >= (34 if "entry:center" in (b.rules or []) else 36) and \
                (main_a / W <= 34 or "entry:center" in (b.rules or [])) and not prim_main

            # bedrooms go over the garage only when the house proper can't hold them along its
            # front (and its back, when the primary is downstairs); otherwise the garage keeps a
            # one-storey roof and nothing upstairs is a leftover "bonus" room
            fit = max(1, int(W // 12.0)) + (1 if prim_main else 0)
            k_wing = min(wings.beds_over(gw), len(prog.bedrooms) - fit, len(prog.bedrooms) - 1) if g else 0
            # a narrow house: the primary suite goes over the garage instead
            wing_primary = bool(g) and not prim_main and n == 2 and gw >= 20 and \
                (W - STAIR_UW < 22 or (k_wing <= 0 and W - STAIR_UW < 26))
            if wing_primary:
                k_wing = 0  # too narrow behind the stair for the primary suite: it goes over the garage
            if g and g_.get("over_garage") == "none":
                k_wing, wing_primary = 0, False  # this candidate keeps the garage one storey
            if g and k_wing <= 0 and not wing_primary:
                continue
            break
        gtop = g
        ext_cap = 14.0 if prim_main else 12.0
        stepped = b.wants("rear addition") or (prim_main and b.primary_floor == "main")
        if not stepped:
            # every floor the same size: one footprint for the whole house (the client's rule;
            # a smaller floor above only when they ask for a rear addition / bigger main floor)
            D_up = snap(max(28.5, (main_a + up_a) / 2 / W))
            ext, top_cut = 0.0, 0.0
        else:
            if n == 2:
                # the floor above is only as deep as its rooms need (no closets the size of rooms);
                # what's left goes to the main floor's one-storey section out back
                wing_bath = 1 if k_wing and len(prog.baths) >= 2 else 0  # (as the try loop below decides)
                body = prog.bedrooms[:len(prog.bedrooms) - k_wing] + prog.baths[:len(prog.baths) - wing_bath] + \
                    ([] if prim_main or wing_primary else prog.primary)
                roomy = max(1.0, min(1.35, above_total / max(b.beds * 700.0, 1)))  # bigger rooms in a bigger house
                need = sum(s.target for s in body) * 1.25 * roomy + W * HALL + STAIR_UW * STAIR_UL + 40
                d_need = snap(max(31.5 if roomy < 1.15 else 34.0, need / W))  # roomy houses: deeper bedrooms
                if d_need < D_up - 1:
                    main_a += (D_up - d_need) * W
                    D_up = d_need
                    ext_cap += 4.0
            # a narrow house reaches its size with a longer one-storey section out back (up to 20')
            ext_cap = max(ext_cap, min(20.0, main_a / W - D_up)) if n == 2 else ext_cap
            ext = snap(min(ext_cap, main_a / W - D_up))
            top_cut = snap(max(0.0, min(D_up - 27.0, D_up - top_a / W))) if n == 3 else 0.0
            if ext < 5.0:
                ext = 0.0
        # the upper hall sits right where the U stair arrives, so the front rooms' depth also
        # sets the stair
        room = D_up - HALL - STAIR_UL - 1.0
        D = D_up + ext
        # the front rooms take what the stair doesn't need behind the hall (deep bedrooms, not
        # a deep band of bathrooms and linen closets behind it)
        front_depth = max(10.0, min(15.5, round(max(D_up * 0.42, room - 2.5) * 2) / 2, room))
        if not stepped and D_up - HALL - front_depth > 17.5:
            # a deep floor (same size as the one below): front and back rooms share the depth
            # evenly instead of the back row turning into corridors
            front_depth = max(front_depth, min(19.0, round((D_up - HALL) / 2 * 2) / 2, room))
        if variant:
            front_depth = max(10.0, front_depth - 1.0)
        tries = [(prim_main, k_wing, wing_primary), (prim_main, 0, False), (False, 0, False)]
        for pm, k, wp in dict.fromkeys(tries):
            import dataclasses
            beds_up = prog.bedrooms[:len(prog.bedrooms) - k] if k else prog.bedrooms
            wing_beds = prog.bedrooms[len(prog.bedrooms) - k:] if k else []
            body_beds = len(beds_up) - (0 if pm else -1)
            take_bath = k and (len(prog.baths) >= 2 or (len(prog.baths) == 1 and not beds_up) or
                               (k == 1 and len(prog.baths) >= 1 and len(beds_up) <= 1))
            wing_baths = prog.baths[-1:] if take_bath else []
            p2 = dataclasses.replace(prog, bedrooms=beds_up,
                                     baths=prog.baths[:len(prog.baths) - len(wing_baths)])
            grid_floors = None
            if g_.get("plan2") == "grid" and b.stories == 2 and not pm and not wp and not k:
                from . import grid
                grid_floors = grid.plan(p2, W, D_up, mirror, upstairs_laundry=bool(p2.upstairs_laundry))
                if grid_floors is None:
                    raise BriefError("the grid plan doesn't suit this house")
            floors = grid_floors or layout.multi_story(p2, b.stories, W, D_up, mirror, front_depth,
                                        centered=centered and not mirror, D_main=D_up + ext,
                                        D_top=D_up - top_cut, primary_main=pm,
                                        dining_front="dining:front" in b.places or g_.get("dining") == "front",
                                        primary_elsewhere=wp,
                                        kitchen_rear="kitchen:rear" in b.places or g_.get("kitchen") == "rear",
                                        living_rear=g_.get("living") == "rear" and not b.places)
            if g_.get("upper") == "stacked" and b.stories == 2 and not pm \
                    and not grid_floors and not ext and not top_cut:
                # the upper floor laid out on the main floor's stair, walls and wet rooms
                from . import upper
                lower_kinds = {r.kind for r in floors[0]}
                up_laundry = any(sp.kind == "laundry" for sp in prog.service) and "laundry" not in lower_kinds
                wing_side = None
                if want_garage and k:
                    # the rooms over the garage hang off the upstairs hall: it must reach that wall
                    probe = garages.built_in(floors[0], W, min(D_up, garages.DEPTH + garages.RECESS), b.cars,
                                             lot_full - 10.0 - W - (2.0 if fire else 0.0),
                                             lot_full - 10.0 - W - (2.0 if fire else 0.0),
                                             max_depth=max(D_up, garages.DEPTH + garages.RECESS))
                    if probe is not None:
                        wing_side = "R" if probe.x >= W - 1e-6 else "L"
                if want_garage and wp and wing_side is None:
                    probe = garages.built_in(floors[0], W, min(D_up, garages.DEPTH + garages.RECESS), b.cars,
                                             lot_full - 10.0 - W - (2.0 if fire else 0.0),
                                             lot_full - 10.0 - W - (2.0 if fire else 0.0),
                                             max_depth=max(D_up, garages.DEPTH + garages.RECESS))
                    if probe is not None:
                        wing_side = "R" if probe.x >= W - 1e-6 else "L"
                got = upper.plan(p2, floors[0], W, D_up, upstairs_laundry=up_laundry, wing_side=wing_side,
                                 primary_elsewhere=wp)
                if got is None:
                    raise BriefError("the stacked upper floor doesn't suit this house")
                floors = [floors[0], got]
            gar = None
            if want_garage:
                # built into the house, deep enough to open into the mudroom; the floor above
                # runs over it with real rooms, and one roof covers the lot
                lot_spare = lot_full - 10.0 - W - (2.0 if fire else 0.0)
                top_d = max(r.y + r.h for r in floors[-1])
                cap = (D_up + ext - 13.0) if pm else max(top_d, garages.DEPTH + garages.RECESS)
                gar = garages.built_in(floors[0], W, min(top_d, garages.DEPTH + garages.RECESS), b.cars,
                                       lot_spare, lot_spare, max_depth=cap)
            if (k or wp) and gar is None:
                continue
            over = None
            if gar is not None and len(floors) > 1:
                if wp:
                    over = wings.over_garage(floors[1], gar, [], [], W, primary=prog.primary)
                elif k:
                    over = wings.over_garage(floors[1], gar, wing_beds, wing_baths, W)
                if (k or wp) and over is None:
                    continue
            suite = []
            if pm:
                y1 = D_up + ext
                if gar is not None:
                    east = gar.x >= W - 1e-6
                    y0, sw = gar.y + gar.h, gar.w
                else:
                    stair = next(r for r in floors[0] if r.kind == "stair")
                    east = stair.x + stair.w / 2 > W / 2
                    sw = snap(max(22.0, min(30.0, pw / 15.0)))
                    if lot_full - 10.0 - W - (2.0 if fire else 0.0) < sw:
                        # no room beside the house: the suite runs across the back of the main floor
                        floors = layout.multi_story(p2, b.stories, W, D_up, mirror, front_depth,
                                                    centered=False, D_main=D_up + max(ext, 15.0),
                                                    D_top=D_up - top_cut, primary_main=True,
                                                    dining_front="dining:front" in b.places,
                                                    primary_rear=15.0, kitchen_rear="kitchen:rear" in b.places or g_.get("kitchen") == "rear",
                                        living_rear=g_.get("living") == "rear" and not b.places)
                        break
                    y0 = y1 - snap(max(13.0, min(18.0, pw / sw)))
                if y1 - y0 < 11.0:
                    continue
                suite = wings.primary_behind(gar, W if east else 0.0, east, y0, y1, sw, prog.primary)
            break
        if gar is not None:
            floors[0].append(gar)
            if len(floors) > 1 and over:
                floors[1] += over
                for up in floors[2:]:
                    up.append(Room("Storage", "closet", gar.x, 0, gar.w, wings.over_depth(over)))
            # with nothing over it, the garage is one storey under its own roof
        floors[0] += suite
    if b.stories == 1 and want_garage and gar is None and not blocks:
        # beside the house, set back a little, opening into the mudroom / laundry / a hall
        from . import garage as garages
        lot_spare = lot_full - 10.0 - W - (2.0 if fire else 0.0)
        top_d = max(r.y + r.h for r in floors[0])
        if tandem:
            gar = garages.built_in(floors[0], W, min(top_d, 2 * 20.0 + garages.RECESS), 1, lot_spare, lot_spare)
            if gar is not None:
                gar.name = "2-Car Tandem Garage"
        else:
            gar = garages.built_in(floors[0], W, min(top_d, garages.DEPTH + garages.RECESS), b.cars,
                                   lot_spare, lot_spare)
        if gar is not None:
            floors[0].append(gar)
    names = ["First Floor", "Second Floor", "Third Floor"]
    up_ceil = min(ceil, 9.0) if b.ceiling else ceil
    levels = [Level(names[i], fz + (0 if i == 0 else ceil + 1.0 + (i - 1) * (up_ceil + 1.0)),
                    ceil if i == 0 else up_ceil, rooms=rooms)
              for i, rooms in enumerate(floors)]
    plate = levels[-1].plate_z
    depths = [lv.footprint.bounds[3] for lv in levels]
    # the main roof over the house; a built-in garage wing gets its own lower cross roof that
    # joins it (one composition, the wing subordinate)
    main = details.make_roof(style, W, depths[-1], plate)
    block_roofs = []
    if blocks:
        # a house of wings: the bedroom wing carries the main roof, each front wing its own
        # roof running toward the street (the garage wing's comes with the garage below)
        bx, by, bw, bh, _ = next(bl for bl in blocks if bl[4] == "Bedroom wing")
        main = details.make_roof(style, bw, bh, plate, x0=bx)
        main.y = by
        main.ridge = "x" if bw >= bh else "y"  # along the wing's length
        for x, y, w, h, name in blocks:
            if name in ("Bedroom wing", "Garage wing"):
                continue
            k = main.kind
            if main.ridge == "x":
                # a front wing off a long back wing: its ridge runs to the street and into the main roof
                block_roofs.append(RoofMass(name, x, y, w, h + bh / 2, kind=k, ridge="y", pitch=main.pitch,
                                            overhang=main.overhang, plate_z=plate,
                                            gable_ends=("S",) if k == "gable" else (),
                                            low_side="N" if k == "shed" else "S"))
            else:
                # a side wing running back: the front block's ridge runs across, the wing's dies into it
                main.y -= h / 2
                main.h += h / 2
                block_roofs.append(RoofMass(name, x, y, w, h, kind=k, ridge="x", pitch=main.pitch,
                                            overhang=main.overhang, plate_z=plate,
                                            low_side="N" if k == "shed" else "S"))
    if gar is not None:
        k = main.kind
        wing_plate = levels[min(1, len(levels) - 1)].plate_z if over else levels[0].plate_z
        wd = wings.over_depth(over) if over else gar.y + gar.h
        if k == "shed":
            wing = RoofMass("Garage wing", gar.x, 0, gar.w, wd, kind="shed", pitch=main.pitch,
                            overhang=main.overhang, plate_z=wing_plate, low_side="N")
        else:
            wing = RoofMass("Garage wing", gar.x, 0, gar.w, wd,
                            kind="gable" if k == "gable" else "hip", ridge="y", pitch=main.pitch,
                            overhang=main.overhang, plate_z=wing_plate,
                            gable_ends=("S",) if k == "gable" else ())
    lower_roofs = []
    flat = style.get("roof", {}).get("kind") == "shed" and style["roof"].get("pitch", 6) < 1
    for i in range(len(levels) - 1):
        if depths[i] > depths[i + 1] + 0.5:
            # the part of this floor that runs out past the floor above: its own low roof
            lower_roofs.append(RoofMass(f"Rear {i + 1}", 0, depths[i + 1], W, depths[i] - depths[i + 1],
                                        kind="shed", pitch=0.25 if flat else 3.0, overhang=0.4,
                                        plate_z=levels[i].plate_z, low_side="N"))
    if gar is not None and over and wings.over_depth(over) < gar.y + gar.h - 0.5:
        # the back of a deep garage, past the rooms above it: a low roof
        wd = wings.over_depth(over)
        lower_roofs.append(RoofMass("Garage rear", gar.x, wd, gar.w, gar.y + gar.h - wd, kind="shed",
                                    pitch=0.25 if flat else 3.0, overhang=0.4, plate_z=levels[0].plate_z,
                                    low_side="N"))
    if suite:
        # the main-floor primary wing: its own low roof, like the one-storey section out back
        x0s, y0s = min(r.x for r in suite), min(r.y for r in suite)
        x1s, y1s = max(r.x + r.w for r in suite), max(r.y + r.h for r in suite)
        lower_roofs.append(RoofMass("Primary wing", x0s, y0s, x1s - x0s, y1s - y0s, kind="shed",
                                    pitch=0.25 if flat else 3.0, overhang=0.4, plate_z=levels[0].plate_z,
                                    low_side="N"))
    living = next(r for r in levels[0].rooms if r.kind == "living")
    entry = next((r for r in levels[0].rooms if r.kind == "entry"), living)
    door_x = entry.x + entry.w / 2
    grand = b.wants("grand entrance") or (b.sqft >= 4500 and b.stories > 1)
    if grand and b.stories > 1:
        # a grand entry: a two-storey portico on tall columns over double doors
        flat = style.get("roof", {}).get("kind") == "shed" and style["roof"].get("pitch", 6) < 1
        lay = dict(style.get("layout", {}), porch="canopy" if flat else "portico",
                   porch_width=max(12.0, min(16.0, W * 0.28)), porch_depth=7, porch_pitch=10)
        porch, porch_roofs = details.make_porch(dict(style, layout=lay), W, D, fz, levels[1].plate_z - 0.5,
                                                door_x, b.stories, True)
    else:
        porch, porch_roofs = details.make_porch(style, W, D, fz, levels[0].plate_z, door_x,
                                                b.stories, b.has("porch"))
    if gar is not None:
        # the porch stays centred on the door but narrows to keep clear of the garage wing
        gap = main.overhang + 1.0
        room_east = (W - gap - door_x) if gar.x >= W - 1e-6 else (door_x - gap)
        if porch.x <= 0.01 and porch.w >= W - 0.5 and not (grand and b.stories > 1):
            pass  # a full-width porch runs across the house, up to the garage wing
        elif porch.w / 2 > room_east:
            half = max(4.0, room_east)
            lay = dict(style.get("layout", {}))
            if grand and b.stories > 1:
                lay.update(porch="portico", porch_width=2 * half, porch_depth=7, porch_pitch=10)
                plate_p = levels[1].plate_z - 0.5
            else:
                lay.update(porch_width=2 * half)
                plate_p = levels[0].plate_z
            porch, porch_roofs = details.make_porch(dict(style, layout=lay), W, D, fz, plate_p, door_x,
                                                    b.stories, True)
    if style.get("roof", {}).get("ridge") == "front" and main.kind == "gable" and main.ridge == "x" and not blocks:
        # too wide for one street gable: a side-gabled roof with a cross gable over part of the
        # front (the farmhouse / tudor composition), kept clear of the porch roof
        from .estate import front_gable
        cw = round(min(18.0, W * 0.38) * 2) / 2
        cx = W * 0.27 if (porch.x + porch.w / 2) > W / 2 else W * 0.73
        cg = front_gable("Cross gable", 0, W, 0, depths[-1], plate, main.pitch, max(main.pitch, 10),
                         main.overhang, cx, max_w=cw)
        cg.cladding = {"timber": "timber"}.get(style.get("siding", {}).get("gables", ""), "")
        lower_roofs.append(cg)
    details.match_peaks(main, ([wing] if gar is not None else []) +
                        [r for r in lower_roofs if r.name == "Cross gable"])
    roofs = [main] + block_roofs + lower_roofs + porch_roofs + ([wing] if gar is not None else [])

    dormers, dormer_roofs = _dormers(b, style, main, W, porch)
    roofs += dormer_roofs
    from ..roof.analytic import z_range
    chimney = details.make_chimney(living, W, levels[0].plate_z if b.stories == 1 else
                                   levels[-1].plate_z) if fire else None
    details.primary_biggest(levels)
    for lv in levels:
        details.use_footprint(lv.footprint)
        lv.rooms = details.split_long(lv.rooms)
        details.use_footprint(None)
    details.primary_biggest(levels)
    for lv in levels:
        lv.rooms = [r for r in lv.rooms if r.w > 0.4 and r.h > 0.4]
    from .. import edit as _edit
    for lv in levels:
        _edit.widen_primary(lv.rooms)  # the primary clearly the best bedroom, not a near tie
    details.absorb_closets(levels)
    open_plan = b.wants("open plan") or "open:on" in (b.rules or [])
    for i, lv in enumerate(levels):
        D = lv.footprint.bounds[3]
        details.use_footprint(lv.footprint)
        details.use_open_plan(open_plan and i == 0)  # kitchen, living / family and dining flow together
        lv.doors = details.make_doors(lv.rooms, known_doors if i == 0 else None)
        details.use_open_plan(False)
        span = (chimney.y, chimney.y + chimney.h) if (chimney and i == 0) else None
        lv.openings = details.make_openings(lv, W, D, style, i == 0, door_x,
                                            chimney.hearth_wall if (chimney and i == 0) else None,
                                            span)
        if i == 0 and grand:
            for o in lv.openings:
                if o.kind == "door" and o.face == "S" and o.width < 5:
                    o.start, o.width = o.start - 1.5, 6.0  # double front doors
        if i == 1 and any(pr.kind == "gable" for pr in porch_roofs):
            # no upstairs window half hidden behind the porch gable (a bedroom keeps its egress
            # window if it has no other)
            def host(o):
                c = o.start + o.width / 2
                return next((r for r in lv.rooms if r.x <= c <= r.x + r.w and abs(r.y - (o.line or 0)) < 0.6), None)
            for pr in porch_roofs:
                hidden = [o for o in lv.openings if o.face == "S" and o.kind == "window"
                          and o.start < pr.x + pr.w + 0.3 and o.start + o.width > pr.x - 0.3]
                for o in hidden:
                    r = host(o)
                    from ..checks import clear_opening
                    # (another window only counts if a person could climb out of it)
                    others = [p for p in lv.openings if p is not o and p.kind == "window" and r is not None
                              and host(p) is r and clear_opening(p)[2] >= 5.7]
                    if r is not None and r.kind == "bedroom" and not others:
                        continue
                    lv.openings.remove(o)
        if i == 1 and grand and b.stories > 1:
            # nothing upstairs hides behind the tall portico (except a bedroom's only way out:
            # that window moves to the bedroom's side wall when it has one, else it stays)
            from ..checks import clear_opening
            def owner(o):
                c = o.start + o.width / 2
                return next((r for r in lv.rooms if r.x <= c <= r.x + r.w and abs(r.y - (o.line or 0)) < 0.6), None)
            keep = []
            for o in lv.openings:
                behind = o.face == "S" and o.start < porch.x + porch.w and o.start + o.width > porch.x
                if behind:
                    r = owner(o)
                    others = [p for p in lv.openings if p is not o and r is not None and p.kind == "window"
                              and owner(p) is r and clear_opening(p)[2] >= 5.7 and not (
                                  p.face == "S" and p.start < porch.x + porch.w and p.start + p.width > porch.x)]
                    if not (r is not None and r.kind == "bedroom" and not others):
                        continue
                keep.append(o)
            lv.openings = keep
        if i == 0 and porch.columns and b.stories > 1:  # (a bungalow keeps bedroom egress)
            # no window half hidden behind a porch column: only the door sits under the porch
            lv.openings = [o for o in lv.openings if not (
                o.face == "S" and o.kind == "window" and o.start < porch.x + porch.w + 0.5
                and o.start + o.width > porch.x - 0.5)]
        if i == 0 and gar is not None:
            from ..model import Opening
            widths = {1: [9.0], 2: [16.0], 3: [16.0, 9.0]}[int(gar.name[0])]
            gap = (gar.w - sum(widths)) / (len(widths) + 1)
            x = gar.x + gap
            for w in widths:
                lv.openings.append(Opening("garage", "S", x, w, 8.0, -fz, operation="overhead", line=gar.y))
                x += w + gap
            lv.openings = [o for o in lv.openings if not (o.kind == "window" and o.face == "S" and
                           gar.x - 0.5 < o.start < gar.x + gar.w)]
        lv.fixtures = details.make_fixtures(lv, W, D, upper=i > 0 or (b.stories == 1 and full.basement))
        details.use_footprint(None)
    details.even_windows(levels)
    details.align_windows(levels)
    details.even_windows(levels)  # aligning can crowd two windows: merge them
    details.daylight(levels)
    D = depths[0]
    b = copy_with(b, sqft=full.sqft, lot_width=lot_full)
    base_level = None
    if full.basement:
        from . import basement
        stair = next(r for r in levels[0].rooms if r.kind == "stair")
        # the basement sits under the house proper, not under the one-storey section out back
        BD = depths[1] if len(depths) > 1 else D
        if b.stories > 1 and (b.has("theatre") or b.has("gym") or b.has("wine room") or b.wants("theatre")
                              or b.wants("gym") or b.wants("wine room")):
            # rooms asked for downstairs: the basement runs under the whole main floor
            BD = max(r.y + r.h for r in levels[0].rooms if r.kind != "garage" and -0.1 < r.x < W - 0.1)
        if full.basement_sqft:
            # a small basement: just deep enough for its size and the stair down into it
            BD = max(stair.y + stair.h + 4.0, min(BD, round(full.basement_sqft / W * 2) / 2))
        base_rooms = basement.under(W, BD, stair, full.suites, full.features, guest=full.beds < 6,
                                    seed=_pick(b, "basement", 4), area=full.basement_sqft)
        base_level = basement.build_level(base_rooms, fz, W, BD)
    name = b.name or f"Plan {b.style[:2].upper()}-{b.sqft}"
    ox0 = min(r.x for r in levels[0].rooms)
    ox1 = max(r.x + r.w for r in levels[0].rooms)
    lot = details.make_lot(b.lot_width, b.lot_depth, ox1 - ox0, D, porch.h,
                           chimney.hearth_wall if chimney else None, "Main Street")
    lot.house_x = round((lot.house_x - ox0) * 2) / 2  # a garage on the west sits left of x = 0
    notes = [f"Generated from the brief: {b.summary()}."]
    if preset_name:
        notes.append(f"Layout adapted from a real floor plan ({preset_name}, CubiCasa5K).")
    notes += [f"Style detail: {d.replace('-', ' ')}." for d in style.get("details", [])[:3]]
    roofs = roofs + details.cover_gaps(levels, roofs)
    details.drop_unplaced(levels + ([base_level] if base_level else []))
    return House(
        name=name, style=b.style, levels=levels, roofs=roofs, porches=[porch], basement=base_level,
        claddings=_claddings(b, style, len(levels)), dormers=dormers,
        chimneys=[chimney] if chimney else [], lot=lot,
        brief=Brief(style["name"], b.stories, b.beds, b.baths, full.sqft,
                    lot=f"{b.lot_width:g}' x {b.lot_depth:g}'", must_haves=list(b.must_haves)),
        notes=notes,
    )


def score(h: House, b: DesignBrief) -> tuple[float, list[str]]:
    """Lower is better: code failures, cramped or skinny rooms, missing rooms."""
    found = checks.run(h)
    s = 100.0 * sum(f.status == "fail" for f in found) + 4.0 * sum(f.status == "warn" for f in found)
    s += 60.0 * sum(f.rule.startswith("P13") for f in found)  # a row of bathrooms: avoid it hard
    notes = []
    for lv in h.levels:
        for r in lv.rooms:
            lo, hi = sorted((r.w, r.h))
            if r.kind in ("bedroom", "living", "dining", "kitchen", "family", "office"):
                if hi / max(lo, 0.1) > 1.7:
                    s += 25 * (hi / lo - 1.7)
                    notes.append(f"{r.name} is long and narrow ({lo:g}' x {hi:g}')")
                if lo < 9.5:
                    s += 15
            if r.kind == "bath" and lo < 5:
                s += 20
        real = [r for r in lv.rooms if r.kind != "void"]
        start = next((r for r in real if r.kind in ("entry", "stair")), real[0])
        reachable = details._reach(start, details.connections(real))
        if len(reachable) < len(real):
            s += 50
            notes.append(f"{lv.name}: some rooms have no door")
    if len(h.bedrooms) < min(b.beds, 5):
        s += 200
    s += design_penalty(h, found)
    # a symmetric style (colonial, foursquare, georgian...) is a centre-hall house: the front
    # door and stair on the middle line, unless a candidate says otherwise on purpose
    from .. import styles as style_lib
    if style_lib.get(b.style).get("layout", {}).get("symmetric") and b.stories >= 2 and \
            (getattr(h, "genome", None) or {}).get("core") is None:
        W = h.levels[0].footprint.bounds[2]
        door = next((o for o in h.levels[0].openings if o.kind == "door" and o.face == "S"), None)
        if door is not None and abs(door.start + door.width / 2 - W / 2) > 5:
            s += 80.0
            notes.append("front door off the centre line of a symmetric style")
    from . import stats
    extra, why = stats.layout_penalty(h.levels)
    return s + extra, notes + why[:3]


def design_penalty(h: House, found=None) -> float:
    """What an architect would mark that the pass/fail rules don't: circulation over 12% of a
    floor (CubiCasa median 8%, p75 12%) or one corridor over 30', habitable rooms without
    daylight and living rooms lit from one side only, closets eating the floor, upstairs baths
    with no wet room under them, and a primary that isn't clearly the best bedroom."""
    from ..checks import _windows_in
    found = found if found is not None else checks.run(h)
    s = 15.0 * sum(f.rule.startswith("P11") and f.status == "warn" for f in found)
    s += 10.0 * sum(f.rule.startswith("G5") and f.status != "pass" for f in found)
    beds = []
    for lv in h.all_levels:
        rooms = [r for r in lv.rooms if r.kind != "void"]
        area = sum(r.area for r in rooms) or 1.0
        halls = [r for r in rooms if r.kind == "hall"]
        share = sum(r.area for r in halls) / area
        s += 300.0 * max(0.0, share - 0.12)
        s += 10.0 * sum(max(r.w, r.h) > 30 for r in halls)
        closet = sum(r.area for r in rooms if r.kind == "closet") / area
        s += 200.0 * max(0.0, closet - 0.14)
        if lv is not h.basement:
            for r in rooms:
                if r.kind in ("bedroom", "living", "family", "dining", "kitchen", "office") and not r.unit:
                    n = len([o for o in _windows_in(lv, r) if o.kind == "window"])
                    if n == 0:
                        s += 30.0
                    elif r.kind in ("living", "family") and n < 2:
                        s += 10.0
        for r in rooms:
            if r.kind in ("bedroom", "living", "family", "dining", "kitchen", "office") and not r.unit:
                lo, hi = sorted((r.w, r.h))
                if hi / max(lo, 0.1) > 1.8:
                    s += 15.0  # a bowling-alley room
                if (r.kind == "bedroom" and lo < 10) or (r.kind in ("living", "family") and lo < 12):
                    s += 15.0
        beds += [r for r in rooms if r.kind == "bedroom" and not r.unit]
    prim = [r for r in beds if r.name.startswith("Primary")]
    others = sorted((r.area for r in beds if not r.name.startswith("Primary")), reverse=True)
    if prim and others and prim[0].area < 1.15 * others[0]:
        s += 20.0
    return s


ROOM_FOR = {"theatre": "Theatre", "gym": "Gym", "wet bar": "Bar", "wine room": "Wine Room",
            "office": "Office", "spice kitchen": "Spice Kitchen", "mudroom": "Mud", "pantry": "Pantry"}


def missing(h: House, b: DesignBrief) -> list[str]:
    """What the brief asked for that the drawing doesn't have."""
    names = " | ".join(r.name for lv in h.all_levels for r in lv.rooms)
    out = []
    for want in list(b.must_haves) + list(b.features):
        room = ROOM_FOR.get(want)
        if room and room not in names:
            out.append(want)
    if b.has("fireplace") and not h.chimneys:
        out.append("fireplace")
    if b.wants("dormers") and not h.dormers:
        out.append("dormers")
    garages = [r for r in h.levels[0].rooms if r.kind == "garage"]
    if b.garage in ("front", "side") and not garages:
        out.append(f"{b.garage} garage")
    if b.garage == "none" and garages:
        out.append("no garage")
    if b.cars and garages and int(garages[0].name[0]) < b.cars:
        out.append(f"{b.cars}-car garage (fits {garages[0].name[0]})")
    if b.cars and not garages and b.garage != "none":
        out.append(f"{b.cars}-car garage")
    if b.primary_floor == "main" and len(h.levels) > 1:
        if not any(r.name == "Primary Bedroom" for r in h.levels[0].rooms):
            out.append("primary on the main floor")
    if b.primary_floor == "upper" and len(h.levels) > 1:
        if not any(r.name == "Primary Bedroom" for lv in h.levels[1:] for r in lv.rooms):
            out.append("primary upstairs")
    if b.ceiling and abs(h.levels[0].ceiling - b.ceiling) > 0.1:
        out.append(f"{b.ceiling:g}' ceilings")
    for p in getattr(b, "places", []):
        room, side = p.split(":")
        rooms = [r for lv in h.levels for r in lv.rooms
                 if (r.name.startswith("Primary Bedroom") if room == "primary" else r.kind == room)]
        ok = False
        for lv in h.levels:
            y0, y1 = lv.footprint.bounds[1], lv.footprint.bounds[3]
            for r in rooms:
                if r in lv.rooms and ((side == "rear" and abs(r.y + r.h - y1) < 0.6) or
                                      (side == "front" and r.y <= y0 + 8)):
                    ok = True
        if rooms and not ok:
            out.append(f"{'primary bedroom' if room == 'primary' else room} at the {side}")
    if b.basement and h.basement is None:
        out.append("basement")
    if b.basement and b.suites:
        got = len({r.unit for r in h.basement.rooms if r.unit}) if h.basement else 0
        if got < len(b.suites):
            out.append(f"{len(b.suites) - got} rental suite(s)")
    beds = len([r for lv in h.all_levels for r in lv.rooms if r.kind == "bedroom" and not r.unit])
    if beds < b.beds:
        out.append(f"{b.beds - beds} bedroom(s)")
    from .. import custom_rules
    for rule in getattr(b, "rules", []) or []:
        kept, _why = custom_rules.check(h, rule)
        if not kept:
            out.append(custom_rules.describe(rule))
    return out


def adapt(b: DesignBrief) -> tuple[DesignBrief, list[str]]:
    """A rough concept should always come out: bend the brief the least it takes to build,
    and say what changed. Only nonsense (no bedrooms, an unknown style) is refused."""
    import copy
    b = copy.deepcopy(b)
    notes = []
    if b.sqft > 8000:
        notes.append(f"Drawn at 8,000 sq ft (asked {b.sqft:,}); the engine tops out there for now.")
        b.sqft = 8000
    b.beds = max(1, min(7, b.beds))
    b.baths = max(1.0, min(8.0, b.baths))
    from . import micro
    fixed = "strict lot" in b.features or "townhouse" in b.features
    if micro.applies(b) and micro.footprint(b):
        # a tiny or narrow infill lot: the townhouse plan, sized to what the lot holds
        f, r, sd = micro.setbacks(b)
        W, D = micro.footprint(b)
        cap = int(W * D * max(b.stories, 2))
        if b.stories < 2:
            b.stories = 2
            notes.append("Two storeys: the only way a home fits this lot.")
        if b.sqft != cap:
            b.sqft = cap
        return b, notes
    if fixed and micro.footprint(b) is None:
        f, r, sd = micro.setbacks(b)
        raise BriefError(f"A {b.lot_width:g}' x {b.lot_depth:g}' lot leaves only "
                         f"{max(b.lot_width - 2 * sd, 0):g}' x {max(b.lot_depth - f - r, 0):g}' after even minimal "
                         "infill setbacks: too small for a stair plus rooms on any floor")
    if b.lot_width < 30 and not fixed:
        notes.append(f"A {b.lot_width:g}' lot is too narrow for a house; drawn on a 40' lot.")
        b.lot_width = 40.0
    need = 380 + 150 * b.beds + 45 * b.baths + (650 * len(b.suites) if b.basement else 0)
    if b.sqft < need * 0.8 and not fixed:
        new = int(round(need / 50) * 50)
        notes.append(f"{b.beds} bed / {b.baths:g} bath needs about {new:,} sq ft; drawn at that size.")
        b.sqft = new
    for _ in range(4):
        try:
            build(b, False, False)
            return b, notes
        except BriefError as e:
            msg = str(e)
            said = getattr(b, "_stories_said", False)
            if not said and (b.stories < 2 or (b.stories < 3 and not b.basement and b.sqft / b.stories > 2600)):
                b.stories += 1
                notes.append(f"Drawn as {b.stories} storeys so it fits the lot ({msg.split(';')[0]}).")
            elif "basement" in msg:
                b.basement, b.suites = False, []
                notes.append("Basement left out: " + msg + ".")
            elif fixed:
                raise BriefError(f"{b.sqft:,} sq ft doesn't fit the {b.lot_width:g}' x {b.lot_depth:g}' lot "
                                 "(kept as given); try fewer square feet or another storey")
            else:
                b.lot_depth = round((b.lot_depth + 20) / 5) * 5
                b.lot_width = max(b.lot_width, min(b.lot_width + 10, 100))
                notes[:] = [n for n in notes if not n.startswith("Drawn on a ")]  # only the final lot
                notes.append(f"Drawn on a {b.lot_width:g}' x {b.lot_depth:g}' lot so it fits with standard setbacks.")
    return b, notes


def options(b: DesignBrief, n: int = 3, seed: int = 0, budget: int = 12) -> list[Option]:
    """Independent candidate designs from the brief, chosen by feasibility, then brief
    adherence, then design quality, then novelty (see candidates.py). Same brief + same seed
    gives the same designs; another seed explores and leads with a different good one."""
    from . import candidates as cands
    problems = [p for p in b.validate() if "style" in p]
    if problems:
        raise BriefError("; ".join(problems))
    from .. import custom_rules
    b = copy_with(b)
    custom_rules.apply(b)  # custom rules become ordinary brief fields the generators read
    b, adapted = adapt(b)
    symmetric = styles.get(b.style).get("layout", {}).get("symmetric", False)
    pool: list = []
    first_error = None
    for g in cands.genomes(b, seed, budget):
        bb = copy_with(b, style=g["style"]) if g.get("style") else b
        try:
            h = build(bb, g.get("mirror", False), g.get("variant", False), genome=g)
        except BriefError as e:
            first_error = first_error or e
            continue
        c = cands.evaluate(cands.Candidate(g, h), b)
        if g.get("estate") is False and styles.get(b.style).get("layout", {}).get("estate"):
            c.quality += 80  # the West Coast estate *is* that style: other types are alternatives
        if symmetric and b.stories > 1 and not g.get("style"):
            stair = next((r for r in h.levels[0].rooms if r.kind == "stair"), None)
            W = h.levels[0].footprint.bounds[2]
            if stair and abs(stair.x + stair.w / 2 - W / 2) < 4:
                c.quality -= 30  # the style wants a centred entry
        pool.append(c)
    if b.stories == 1 and not b.basement:
        # real floor plans with this many bedrooms, close in size, compete with the generated ones
        from . import library
        clean_real = 0
        for p in library.candidates(b.beds, b.sqft, 1, 16, seed=_pick(b, "library", 97) + seed):
            if clean_real >= 2:
                break  # two good real plans are plenty
            got = library.rooms_for(p, b.sqft, mirror=_pick(b, p["id"], 2) == 1)
            if not got:
                continue
            try:
                h = build(b, False, False, preset=got, preset_name=p["id"])
            except Exception:
                continue
            c = cands.evaluate(cands.Candidate({"preset": p["id"]}, h), b)
            if c.hard:
                continue  # a real plan only competes once it meets every rule
            clean_real += 1
            pool.append(c)
    if not pool:
        raise first_error or BriefError("no design fits this brief")
    chosen = cands.choose(pool, n, seed)
    out = []
    from .. import edit
    for i, c in enumerate(chosen):
        h = c.house
        h.genome = {k: v for k, v in c.genome.items() if k != "preset"}
        edit.assign_titles(h)
        notes = ([f"Couldn't fit: {', '.join(c.missing)}"] if c.missing else []) + c.notes
        h.notes = adapted + ([f"Couldn't fit: {', '.join(c.missing)}."] if c.missing else []) + h.notes
        for rule in b.rules or []:
            kept, why = custom_rules.check(h, rule)
            h.notes.append(f"Custom rule {'kept' if kept else 'NOT kept'}: {custom_rules.describe(rule)} ({why}).")
        if i:
            h.name = f"{h.name} ({'ABCDEFG'[i]})"
        out.append(Option(h, c.quality + 100.0 * c.hard + 150.0 * len(c.missing), adapted + notes))
    return out


def offspring(b: DesignBrief, a: House, c: House, n: int = 3, seed: int = 0) -> list[Option]:
    """Breed two designs: children that mix their decisions, best first, each clean of hard
    failures where possible and different from both parents."""
    from . import candidates as cands
    from .. import custom_rules, edit
    from .signature import novelty, signature
    bb = copy_with(b)
    custom_rules.apply(bb)
    bb, adapted = adapt(bb)
    parents = [signature(a), signature(c)]
    pool = []
    for g in cands.breed(bb, dict(a.genome or {}), dict(c.genome or {}), n=n * 3, seed=seed):
        b2 = copy_with(bb, style=g["style"]) if g.get("style") else bb
        try:
            h = build(b2, g.get("mirror", False), g.get("variant", False), genome=g)
        except BriefError:
            continue
        cd = cands.evaluate(cands.Candidate(g, h), bb)
        if novelty(cd.sig, parents) < 0.04:
            continue  # came out the same as a parent
        pool.append(cd)
    pool.sort(key=lambda x: (x.hard > 0, x.hard, len(x.missing), x.prefs > 0, x.quality))
    pool = [x for x in pool if x.hard == 0]  # a child that breaks a rule is never offered
    out = []
    for i, cd in enumerate(pool[:n]):
        cd.house.genome = cd.genome
        edit.assign_titles(cd.house)
        cd.house.name = f"{a.name.split(' (')[0]} × {i + 1}"
        out.append(Option(cd.house, cd.quality, ([f"Couldn't fit: {', '.join(cd.missing)}"] if cd.missing else [])))
    return out


def design(b: DesignBrief) -> House:
    return options(b, 1)[0].house
