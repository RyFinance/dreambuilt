"""Design checks in four tiers (hard, preference, code, advisory). The code tier is an
informal pre-check loosely after the 2021 IRC.

These flag likely problems for the architect conversation. They are not a
code review and do not cover structure, energy, fire separation or zoning.
"""
from __future__ import annotations

import math

from dataclasses import dataclass

from shapely.geometry import box

from ..model import House, Level, Room
from ..views.scene import place_opening

HABITABLE = {"living", "dining", "kitchen", "bedroom", "family", "office", "den"}
NOT_ROOMS = {"garage", "void"}


@dataclass
class Finding:
    rule: str
    status: str  # pass | warn | fail
    where: str
    detail: str
    tier: str = ""  # hard | preference | code | advisory (set from the rule)

    def __post_init__(self):
        if not self.tier:
            self.tier = tier_of(self.rule, self.status)


# hard: the house doesn't work (or the drawings can't agree); preference: an architect would
# push back; code: informal pre-checks loosely after the 2021 IRC, never a compliance claim
# (jurisdiction rules differ and are not modelled); advisory: worth a look
HARD = ("G1", "G2", "G3", "G4", "P1", "P2", "P4", "P5", "P7", "P9", "P10", "P12")
PREFERENCE = ("P3", "P6", "P8", "P11", "P13", "G5")


def tier_of(rule: str, status: str = "fail") -> str:
    code = rule.split()[0]
    if status == "warn":
        return "advisory"
    if code.startswith("R"):
        return "code"
    if code in HARD or code.startswith("P1-"):
        return "hard"
    if code in PREFERENCE:
        return "preference"
    return "advisory"


def blocking(findings: list) -> list:
    """The failures that make a design unusable: hard constraints and code pre-checks."""
    return [f for f in findings if f.status == "fail" and f.tier in ("hard", "code")]


def _windows_in(level: Level, room: Room):
    out = []
    for op in level.openings:
        pl = place_opening(level, op)
        if pl is None:
            continue
        p, q = pl.plan_points()
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        if room.rect.buffer(0.01).contains(box(mid[0] - 0.005, mid[1] - 0.005,
                                               mid[0] + 0.005, mid[1] + 0.005)):
            out.append(op)
    return out


def clear_opening(op) -> tuple[float, float, float]:
    """Approximate net clear (width, height, area) of a window, feet."""
    w = op.width - 0.33
    if op.operation == "double-hung":
        h = op.height / 2 - 0.25
    elif op.operation in ("casement", "awning"):
        h = op.height - 0.33
    else:
        h = 0.0
    return w, h, max(w, 0) * max(h, 0)


def run(house: House) -> list[Finding]:
    f: list[Finding] = []
    for lv in house.all_levels:
        if lv.ceiling < 7:
            f.append(Finding("R305 ceiling height", "fail", lv.name,
                             f"{lv.ceiling:g}' ceiling is under 7'"))
        else:
            f.append(Finding("R305 ceiling height", "pass", lv.name, f"{lv.ceiling:g}' ceilings"))
        for r in lv.rooms:
            if r.kind in NOT_ROOMS:
                continue
            wins = _windows_in(lv, r)
            if r.kind in HABITABLE:
                if r.area < 70 or min(r.w, r.h) < 7:
                    f.append(Finding("R304 room size", "fail", r.name,
                                     f"{r.area:.0f} sq ft, {min(r.w, r.h):g}' min - needs 70 sq ft and 7'"))
                glass = sum(o.width * o.height for o in wins if o.kind == "window")
                need = 0.08 * r.area
                if glass < need:
                    f.append(Finding("R303 natural light", "warn", r.name,
                                     f"{glass:.1f} sq ft glazing, 8% of floor is {need:.1f}"))
            if r.kind == "bedroom":
                eg = [o for o in wins if o.kind == "window"]
                ok = []
                for o in eg:
                    w, h, a = clear_opening(o)
                    if a >= 5.0 and w >= 20 / 12 and h >= 24 / 12 and o.sill <= 44 / 12:
                        ok.append(o)
                if ok:
                    f.append(Finding("R310 bedroom egress", "pass", r.name,
                                     f"{len(ok)} window(s) meet ~5.0-5.7 sq ft clear, sill <= 44\""))
                else:
                    f.append(Finding("R310 bedroom egress", "fail", r.name,
                                     "no window with ~5.7 sq ft clear opening and sill <= 44\""))
            if r.kind in ("bath", "powder"):
                if not [o for o in wins if o.kind == "window"]:
                    f.append(Finding("R303.3 bath ventilation", "warn", r.name,
                                     "no window - plan a 50 cfm exhaust fan"))
            if r.kind == "hall" and min(r.w, r.h) < 3:
                f.append(Finding("R311.6 hallway width", "fail", r.name,
                                 f"{min(r.w, r.h):g}' wide, needs 3'"))
    ext_doors = [o for lv in house.levels[:1] for o in lv.openings if o.kind == "door"]
    if not any(o.width >= 3.0 - 1e-6 for o in ext_doors):
        f.append(Finding("R311.2 egress door", "fail", "Exterior", "no 3'-0\" exterior door"))
    else:
        f.append(Finding("R311.2 egress door", "pass", "Exterior", "3'-0\" x 6'-8\" door provided"))
    f.extend(stairs(house))
    from . import geometry, planning
    f.extend(planning.check(house))
    f.extend(geometry.check(house))
    return f


MAX_RISE = 7.75 / 12  # R311.7.5.1, feet
MIN_TREAD = 10 / 12  # R311.7.5.2
MIN_WIDTH = 3.0      # R311.7.1 (36" clear above the handrail)
MIN_HEAD = 6.67      # R311.7.2 (6'-8")


def stairs(house: House) -> list[Finding]:
    """R311.7: every stair rises at most 7 3/4" a step on treads of at least 10", is 36" wide,
    keeps 6'-8" of headroom, and has a landing at least as deep as it is wide at the top and
    bottom (R311.7.6)."""
    out = []
    levels = house.all_levels
    for i, lv in enumerate(levels[:-1]):
        nxt = levels[i + 1]
        ftf = nxt.floor_z - lv.floor_z
        st = [x for x in lv.fixtures if x.kind in ("stair", "stair-u")]
        if not st:
            st = [x for x in nxt.fixtures if x.kind in ("stair-down", "stair-u-down")]
        if not st:
            out.append(Finding("R311.7 stairs", "fail", lv.name, f"no stair up to the {nxt.name.lower()}"))
            continue
        x = st[0]
        u = x.kind.startswith("stair-u")
        width = (x.w / 2 if u else min(x.w, x.h))
        run = (max(x.w, x.h) - (min(x.w / 2, 4.0) if u else 0)) * (2 if u else 1)
        risers = math.ceil(ftf / MAX_RISE - 1e-9)
        tread = run / max(risers - 1, 1)
        rise = ftf / risers
        problems = []
        if width < MIN_WIDTH - 0.05:
            problems.append(f"{width * 12:.0f}\" wide (needs 36\")")
        if tread < MIN_TREAD - 0.01:
            problems.append(f"{tread * 12:.1f}\" treads (needs 10\"); the run is too short for {ftf:g}' floor to floor")
        head = (nxt.ceiling + nxt.floor_depth) if not u else lv.ceiling
        if head < MIN_HEAD:
            problems.append(f"{head:g}' headroom")
        if problems:
            out.append(Finding("R311.7 stairs", "fail", f"Stair to {nxt.name}", "; ".join(problems)))
        else:
            out.append(Finding("R311.7 stairs", "pass", f"Stair to {nxt.name}",
                               f"{risers} risers at {rise * 12:.2f}\", {tread * 12:.1f}\" treads, "
                               f"{width * 12:.0f}\" wide{', U with a landing' if u else ''}"))
    return out


def summary(findings: list[Finding]) -> dict[str, int]:
    out = {"pass": 0, "warn": 0, "fail": 0}
    for x in findings:
        out[x.status] += 1
    for t in ("hard", "preference", "code"):
        out[f"fail_{t}"] = sum(x.status == "fail" and x.tier == t for x in findings)
    return out
