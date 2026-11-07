"""Room, door and window schedules, with type marks shared by plans and tables."""
from __future__ import annotations

from dataclasses import dataclass

from . import styles
from .model import House
from .views.common import fmt_ft

OPERATION = {"double-hung": "DH", "casement": "CSMT", "awning": "AWN", "fixed": "FX",
             "swing": "SWING"}


@dataclass
class WindowType:
    mark: str
    width: float
    height: float
    operation: str
    grille: str
    sill: float
    count: int


def window_types(house: House) -> tuple[list[WindowType], dict[int, str]]:
    """Group identical windows into lettered types; return types and id(opening) -> mark."""
    default = styles.get(house.style).get("windows", {}).get("grille", "1/1")
    types: dict[tuple, WindowType] = {}
    marks: dict[int, str] = {}
    for lv in house.levels:
        for op in lv.openings:
            if op.kind != "window":
                continue
            key = (op.width, op.height, op.operation, op.grille or default, op.sill)
            if key not in types:
                letter = chr(ord("A") + len(types))
                types[key] = WindowType(op.mark or letter, *key, count=0)
            types[key].count += 1
            marks[id(op)] = types[key].mark
    return list(types.values()), marks


def window_rows(house: House) -> list[list[str]]:
    types, _ = window_types(house)
    return [[t.mark, str(t.count), f"{fmt_ft(t.width)} x {fmt_ft(t.height)}",
             OPERATION.get(t.operation, t.operation.upper()), t.grille.replace("/", " over "),
             fmt_ft(t.sill)] for t in types]


def door_rows(house: House) -> list[list[str]]:
    rows = []
    n = 1
    for lv in house.levels:
        for op in lv.openings:
            if op.kind == "door":
                room = _room_near(lv, op)
                rows.append([f"D{n}", f"{fmt_ft(op.width)} x {fmt_ft(op.height)}", "Exterior",
                             "Entry" if op.face == "S" else f"{room} ({op.face})", lv.name])
                n += 1
        for d in lv.doors:
            a = lv.room_at(d.x + (0.3 if d.axis == "y" else 0), d.y + (0.3 if d.axis == "x" else 0))
            b = lv.room_at(d.x - (0.3 if d.axis == "y" else 0), d.y - (0.3 if d.axis == "x" else 0))
            names = " / ".join(sorted({r.name for r in (a, b) if r}))
            kind = {"swing": "Interior swing", "cased": "Cased opening", "pocket": "Pocket",
                    "bifold": "Bifold"}[d.kind]
            h = "-" if d.kind == "cased" else fmt_ft(d.height)
            rows.append([f"D{n}", f"{fmt_ft(d.width)} x {h}", kind, names, lv.name])
            n += 1
    return rows


def _room_near(lv, op) -> str:
    from .views.scene import _normal, place_opening
    pl = place_opening(lv, op)
    if not pl:
        return ""
    p, q = pl.plan_points()
    nx, ny = _normal(pl.edge)
    r = lv.room_at((p[0] + q[0]) / 2 - nx, (p[1] + q[1]) / 2 - ny)
    return r.name if r else ""


def room_rows(house: House) -> list[list[str]]:
    rows = []
    for lv in house.all_levels:
        for r in lv.rooms:
            rows.append([r.name, lv.name, f"{fmt_ft(r.w)} x {fmt_ft(r.h)}", f"{r.area:,.0f}",
                         fmt_ft(lv.ceiling)])
    return rows
