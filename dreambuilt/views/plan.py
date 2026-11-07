"""Floor plans: cut walls with openings, door swings, fixtures, labels, dimensions."""
from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from ..geometry import hatch_lines, lines_of, polygons_of
from ..model import Fixture, House, InteriorDoor, Level
from ..render.canvas import Canvas
from ..render.themes import Theme
from ..roof.analytic import build_roof
from .common import dim, ellipse, fmt_ft, fmt_size, tag
from .scene import _normal, place_opening

EXT_T = 0.5  # exterior wall, 6"
INT_T = 0.375  # interior partition, 4-1/2"


def cap(theme: Theme, s: str) -> str:
    return s.upper() if theme.upper else s


def interior_segments(level: Level, walls_only: bool = False, rails: bool = False) -> list[LineString]:
    """Shared room edges. walls_only skips edges of an open-to-below; rails returns only those."""
    segs = []
    rooms = level.rooms
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            open_edge = "void" in (a.kind, b.kind)
            if (walls_only and open_edge) or (rails and not open_edge):
                continue
            shared = a.rect.boundary.intersection(b.rect.boundary)
            segs += [s for s in lines_of(shared) if s.length > 0.05]
    return segs


def wall_geometry(house: House, level: Level, marks: dict | None = None):
    """Cut wall poche, plus the openings carved out of it."""
    fp = level.footprint
    inner = fp.buffer(-EXT_T, join_style=2)
    walls = fp.difference(inner)
    parts = [s.buffer(INT_T / 2, cap_style=2) for s in interior_segments(level, walls_only=True)]
    if parts:
        walls = walls.union(unary_union(parts).intersection(fp))
    for c in house.chimneys:
        if c.hearth_wall and level is house.levels[0]:
            walls = walls.union(_firebox_mass(c))
    cuts = []
    placements = []
    for op in level.openings:
        pl = place_opening(level, op)
        if pl is None:
            continue
        p, q = pl.plan_points()
        nx, ny = _normal(pl.edge)
        o, i = 0.2, EXT_T + 0.05
        cut = Polygon([(p[0] + nx * o, p[1] + ny * o), (q[0] + nx * o, q[1] + ny * o),
                       (q[0] - nx * i, q[1] - ny * i), (p[0] - nx * i, p[1] - ny * i)])
        cuts.append(cut)
        placements.append(pl)
    for d in level.doors:
        cuts.append(_door_rect(d, INT_T + 0.1))
    walls = walls.difference(unary_union(cuts)) if cuts else walls
    return walls, placements


def _firebox_mass(c):
    if c.hearth_wall == "W":
        return box(c.x + c.w, c.y, c.x + c.w + EXT_T + 1.5, c.y + c.h)
    if c.hearth_wall == "E":
        return box(c.x - EXT_T - 1.5, c.y, c.x, c.y + c.h)
    if c.hearth_wall == "S":
        return box(c.x, c.y + c.h, c.x + c.w, c.y + c.h + EXT_T + 1.5)
    return box(c.x, c.y - EXT_T - 1.5, c.x + c.w, c.y)


def _door_rect(d: InteriorDoor, t: float) -> Polygon:
    if d.axis == "x":
        return box(d.x - d.width / 2, d.y - t / 2, d.x + d.width / 2, d.y + t / 2)
    return box(d.x - t / 2, d.y - d.width / 2, d.x + t / 2, d.y + d.width / 2)


class PlanView:
    def __init__(self, house: House, level: Level):
        self.house = house
        self.level = level
        self.roof = build_roof(house) if level is house.levels[-1] else None
        outline = house.outline() if level is house.levels[0] else level.footprint
        b = outline.bounds
        if self.roof is not None:
            rb = self.roof.eave_outline.bounds
            b = (min(b[0], rb[0]), min(b[1], rb[1]), max(b[2], rb[2]), max(b[3], rb[3]))
        y0 = b[1]
        if level is house.levels[0]:
            for p in house.porches:
                for st in p.steps:
                    if st.face == "S":
                        y0 = min(y0, p.y - (st.risers - 1))
        fx0, fy0, fx1, fy1 = level.footprint.bounds
        idx = house.levels.index(level) if level in house.levels else -1
        for f in level.fixtures:  # exterior stairwells down to basement suites
            b = (min(b[0], f.x), min(b[1], f.y), max(b[2], f.x + f.w), max(b[3], f.y + f.h))
        for bal in house.balconies:
            if bal.level == idx:
                b = (min(b[0], bal.x), min(b[1], bal.y), max(b[2], bal.x + bal.w), max(b[3], bal.y + bal.h))
        self.bounds = (b[0] - 0.5, y0 - 0.4, max(b[2], fx1 + 4.1), max(b[3], fy1 + 4.1))

    @property
    def title(self) -> str:
        return f"{self.level.name} Plan"

    def draw(self, cv: Canvas, theme: Theme, window_marks: dict | None = None,
             labels: bool = True, dims: bool = True) -> None:
        h, lv = self.house, self.level
        first = lv is h.levels[0]
        if first:
            for p in h.porches:
                self._porch(cv, p)
        if self.roof is not None:
            cv.geom(self.roof.eave_outline.exterior, "eave")
        walls, placements = wall_geometry(h, lv)
        if theme.wall_fill == "solid":
            cv.geom(walls, "cut", fill="poche")
        else:
            cv.geom(walls, "cut")
            for poly in polygons_of(walls):
                cv.lines(hatch_lines(poly, 45, 0.35), "hatch")
        if first:
            for c in h.chimneys:
                self._chimney(cv, theme, c)
        for pl in placements:
            self._opening(cv, pl, window_marks)
        for d in lv.doors:
            self._door(cv, d)
        for f in lv.fixtures:
            draw_fixture(cv, f)
        for s in interior_segments(lv, rails=True):  # railings around an open-to-below
            cv.geom(s.buffer(0.12, cap_style=2), "thin", fill="paper")
        for r in lv.rooms:
            if r.kind == "void":
                cv.line((r.x + 0.4, r.y + 0.4), (r.x + r.w - 0.4, r.y + r.h - 0.4), "hidden")
                cv.line((r.x + 0.4, r.y + r.h - 0.4), (r.x + r.w - 0.4, r.y + 0.4), "hidden")
        idx = h.levels.index(lv) if lv in h.levels else -1
        for b in h.balconies:
            if b.level == idx:
                cv.rect(b.x, b.y, b.x + b.w, b.y + b.h, "outline")
                cv.rect(b.x + 0.15, b.y + 0.15, b.x + b.w - 0.15, b.y + b.h - 0.15, "thin")
                cv.text(b.x + b.w / 2, b.y + b.h / 2 - 0.2, cap(theme, "Balcony"), size=6,
                        anchor="middle", font="label")
        if labels:
            for r in lv.rooms:
                self._label(cv, theme, r)
        if dims:
            self._dims(cv, placements)

    # -- pieces -----------------------------------------------------------
    def _opening(self, cv, pl, marks):
        op = pl.opening
        p, q = pl.plan_points()
        nx, ny = _normal(pl.edge)
        out = lambda pt, d: (pt[0] + nx * d, pt[1] + ny * d)
        if op.kind == "window":
            cv.line(out(p, 0), out(q, 0), "thin")
            cv.line(out(p, -EXT_T), out(q, -EXT_T), "thin")
            cv.line(out(p, -EXT_T / 2 + 0.06), out(q, -EXT_T / 2 + 0.06), "glass")
            cv.line(out(p, -EXT_T / 2 - 0.06), out(q, -EXT_T / 2 - 0.06), "glass")
            cv.line(out(p, 0.15), out(q, 0.15), "thin")  # sill
            if marks is not None and id(op) in marks:
                mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
                tag(cv, mx + nx * 1.2, my + ny * 1.2, marks[id(op)])
        elif op.kind == "garage":
            cv.line(out(p, -EXT_T / 2), out(q, -EXT_T / 2), "hidden")
            cv.line(out(p, 0.1), out(q, 0.1), "thin")
        else:
            hinge = out(p, -EXT_T)
            w = op.width
            leaf = (hinge[0] - nx * w, hinge[1] - ny * w)
            cv.line(hinge, leaf, "outline")
            a0 = math.degrees(math.atan2(-ny, -nx))
            a1 = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
            _arc_between(cv, hinge, w, a0, a1)
            cv.line(out(p, 0.3), out(q, 0.3), "thin")  # threshold

    def _door(self, cv, d: InteriorDoor):
        if d.kind == "cased":
            return
        half = d.width / 2
        sgn = 1 if d.swing == "+" else -1
        t = INT_T / 2 * sgn
        if d.axis == "x":
            hx = d.x - half if d.hinge == "start" else d.x + half
            ox = d.x + half if d.hinge == "start" else d.x - half
            hinge = (hx, d.y + t)
            if d.kind == "pocket":
                cv.line((d.x - half, d.y), (d.x - 3 * half, d.y), "hidden")
                return
            leaf = (hx, d.y + t + sgn * d.width)
            cv.line(hinge, leaf, "outline")
            _arc_between(cv, hinge, d.width, 90 * sgn, 0 if ox > hx else 180)
        else:
            hy = d.y - half if d.hinge == "start" else d.y + half
            oy = d.y + half if d.hinge == "start" else d.y - half
            hinge = (d.x + t, hy)
            if d.kind == "pocket":
                cv.line((d.x, d.y - half), (d.x, d.y - 3 * half), "hidden")
                return
            leaf = (d.x + t + sgn * d.width, hy)
            cv.line(hinge, leaf, "outline")
            _arc_between(cv, hinge, d.width, 0 if sgn > 0 else 180, 90 if oy > hy else -90)

    def _porch(self, cv, p):
        cv.rect(p.x, p.y, p.x + p.w, p.y + p.h, "outline")
        for x in frange(p.x + 0.5, p.x + p.w, 0.5):  # deck boards
            cv.line((x, p.y + 0.15), (x, p.y + p.h - 0.15), "hatch")
        cw = 1.67
        for cx, cy in p.columns:
            cv.rect(cx - cw / 2, cy - cw / 2, cx + cw / 2, cy + cw / 2, "cut", fill="poche")
        for st in p.steps:
            n = st.risers - 1
            if st.face == "S":
                cv.rect(st.x, p.y - n, st.x + st.width, p.y, "outline")
                for k in range(1, n):
                    cv.line((st.x, p.y - k), (st.x + st.width, p.y - k), "thin")
                cv.text(st.x + st.width / 2, p.y - n - 0.45 / 1, f"{st.risers} R", size=5.5,
                        anchor="middle")
            elif st.face == "N":
                top = p.y + p.h
                cv.rect(st.x, top, st.x + st.width, top + n, "outline")
                for k in range(1, n):
                    cv.line((st.x, top + k), (st.x + st.width, top + k), "thin")

    def _chimney(self, cv, theme, c):
        cv.rect(c.x, c.y, c.x + c.w, c.y + c.h, "cut", fill="poche" if theme.wall_fill == "solid" else None)
        if theme.wall_fill != "solid":
            cv.lines(hatch_lines(box(c.x, c.y, c.x + c.w, c.y + c.h), 45, 0.35), "hatch")
        if c.hearth_wall == "W":
            x = c.x + c.w + EXT_T + 1.5
            cv.polyline([(x, c.y + 0.7), (x - 1.1, c.y + 1.2), (x - 1.1, c.y + c.h - 1.2),
                         (x, c.y + c.h - 0.7)], "thin", closed=True, fill="paper")
            cv.rect(x, c.y - 0.75, x + 1.67, c.y + c.h + 0.75, "thin")
            cv.text(x + 0.85, c.y + c.h / 2 - 0.15, "HEARTH", size=4.5, anchor="middle", rotate=90)

    def _label(self, cv, theme, r):
        cx, cy = self._label_spot(cv, theme, r)
        name = cap(theme, r.name)
        if r.kind == "hall" or min(r.w, r.h) < 5:
            cv.text(cx, cy - 0.3, name, size=6, anchor="middle", font="label")
            return
        cv.text(cx, cy + 0.25, name, size=7.5, anchor="middle", font="label")
        cv.text(cx, cy - 0.85, fmt_size(r.w, r.h), size=5.5, anchor="middle")

    def _label_spot(self, cv, theme, r):
        """Room centre, nudged off any fixture the label would overlap."""
        from ..render.backends import text_width
        w = max(text_width(cap(theme, r.name), theme.fonts["label"], 7.5),
                text_width(fmt_size(r.w, r.h), theme.fonts["body"], 5.5)) / cv.k + 0.4
        hgt = 0.32 / cv.k
        blocks = [box(f.x, f.y, f.x + f.w, f.y + f.h) for f in self.level.fixtures]
        blocks = [b for b in blocks if b.intersects(r.rect)]
        cx, cy = r.center
        cands = [(cx, cy)]
        for step in (0.15, 0.25, 0.35):
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                cands.append((cx + dx * step * r.w, cy + dy * step * r.h))
        for x, y in cands:
            lab = box(x - w / 2, y - hgt * 0.75, x + w / 2, y + hgt * 0.6)
            if r.rect.buffer(-0.3).contains(lab) and not any(lab.intersects(b) for b in blocks):
                return x, y
        return cx, cy

    def _dims(self, cv, placements):
        fp = self.level.footprint
        x0, y0, x1, y1 = fp.bounds
        # north: room breaks along the north wall, then overall
        north = sorted({r.x for r in self.level.rooms if abs(r.y + r.h - y1) < 1e-6} |
                       {r.x + r.w for r in self.level.rooms if abs(r.y + r.h - y1) < 1e-6})
        for a, b in zip(north, north[1:]):
            dim(cv, (a, y1), (b, y1), 2.0)
        dim(cv, (x0, y1), (x1, y1), 3.6)
        east = sorted({r.y for r in self.level.rooms if abs(r.x + r.w - x1) < 1e-6} |
                      {r.y + r.h for r in self.level.rooms if abs(r.x + r.w - x1) < 1e-6})
        for a, b in zip(east, east[1:]):
            dim(cv, (x1, b), (x1, a), 2.0)
        dim(cv, (x1, y1), (x1, y0), 3.6)


def _arc_between(cv, c, r, a0, a1):
    """Quarter swing from angle a0 to a1 the short way round."""
    d = (a1 - a0 + 540) % 360 - 180
    cv.arc(c[0], c[1], r, a0, a0 + d, "thin") if d >= 0 else cv.arc(c[0], c[1], r, a0 + d, a0, "thin")


def frange(a, b, s):
    while a < b - 1e-9:
        yield a
        a += s


# -- fixtures ---------------------------------------------------------------

def _local(f: Fixture):
    """Map (u across the wall, d out from the wall) to plan, with width and depth."""
    x0, y0, x1, y1 = f.x, f.y, f.x + f.w, f.y + f.h
    if f.back == "N":
        return (lambda u, d: (x0 + u, y1 - d)), f.w, f.h
    if f.back == "S":
        return (lambda u, d: (x1 - u, y0 + d)), f.w, f.h
    if f.back == "E":
        return (lambda u, d: (x1 - d, y0 + u)), f.h, f.w
    return (lambda u, d: (x0 + d, y1 - u)), f.h, f.w


def draw_stair(cv: Canvas, f: Fixture) -> None:
    """Straight run; `back` is the direction of travel going up."""
    down = f.kind == "stair-down"
    x0, y0, x1, y1 = f.x, f.y, f.x + f.w, f.y + f.h
    cv.rect(x0, y0, x1, y1, "outline")
    along_y = f.back in ("N", "S")
    length = f.h if along_y else f.w
    n = max(int(round(length / (10 / 12))), 2)
    for i in range(1, n):
        t = length * i / n
        if along_y:
            cv.line((x0, y0 + t), (x1, y0 + t), "fixture")
        else:
            cv.line((x0 + t, y0), (x0 + t, y1), "fixture")
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ends = {"N": ((cx, y0 + 0.4), (cx, y1 - 0.4)), "S": ((cx, y1 - 0.4), (cx, y0 + 0.4)),
            "E": ((x0 + 0.4, cy), (x1 - 0.4, cy)), "W": ((x1 - 0.4, cy), (x0 + 0.4, cy))}
    a, b = ends[f.back]
    if down:
        a, b = b, a
        # break line across the run
        if along_y:
            cv.line((x0, cy - 0.6), (x1, cy + 0.6), "thin")
        else:
            cv.line((cx - 0.6, y0), (cx + 0.6, y1), "thin")
    from .common import arrow
    arrow(cv, a, b, "thin")
    lx, ly = a
    cv.text(lx + (0.35 if along_y else 0), ly + (0 if along_y else 0.35), "DN" if down else "UP",
            size=5.5, anchor="start" if along_y else "middle")


def draw_u_stair(cv: Canvas, f: Fixture) -> None:
    """Two flights side by side with a landing at the far (north) end: up the west flight,
    across the landing, and up the east flight back toward the south."""
    down = f.kind.endswith("down")
    x0, y0, x1, y1 = f.x, f.y, f.x + f.w, f.y + f.h
    xm = (x0 + x1) / 2
    land = min(f.w / 2, 4.0)
    cv.rect(x0, y0, x1, y1, "outline")
    cv.line((xm, y0), (xm, y1 - land), "outline")  # the wall between the flights
    run = (y1 - land) - y0
    n = max(int(round(run / (10 / 12))), 2)
    for i in range(1, n + 1):
        t = y0 + run * i / n
        cv.line((x0, t), (xm, t), "fixture")
        cv.line((xm, t), (x1, t), "fixture")
    cv.line((x0, y1 - land), (x1, y1 - land), "fixture")
    from .common import arrow
    a1, a2 = (x0 + f.w / 4, y0 + 0.5), (x0 + f.w / 4, y1 - land / 2)
    b1, b2 = (x1 - f.w / 4, y1 - land / 2), (x1 - f.w / 4, y0 + 0.5)
    if down:
        cv.line(b2, b1, "thin")
        cv.line(b1, a2, "thin")
        arrow(cv, a2, a1, "thin")
        cv.line((x0, y0 + run * 0.45), (xm, y0 + run * 0.55), "thin")
        cv.text(b2[0] + 0.35, b2[1] + 0.3, "DN", size=5.5, anchor="start")
    else:
        cv.line(a1, a2, "thin")
        cv.line(a2, b1, "thin")
        arrow(cv, b1, b2, "thin")
        cv.text(a1[0] + 0.35, a1[1] + 0.3, "UP", size=5.5, anchor="start")


def draw_fixture(cv: Canvas, f: Fixture) -> None:
    if f.kind in ("stair", "stair-down"):
        draw_stair(cv, f)
    elif f.kind in ("stair-u", "stair-u-down"):
        draw_u_stair(cv, f)
        return
    P, W, D = _local(f)
    rect = lambda u0, d0, u1, d1, role="fixture", fill=None: cv.polyline(
        [P(u0, d0), P(u1, d0), P(u1, d1), P(u0, d1)], role, closed=True, fill=fill)
    k = f.kind
    if k == "counter":
        rect(0, 0, W, D)
    elif k == "sink":
        rect(0, 0, W, D, fill="paper")
        g = 0.2
        half = (W - 3 * g) / 2
        rect(g, g, g + half, D - g)
        rect(2 * g + half, g, W - g, D - g)
    elif k == "range":
        rect(0, 0, W, D, fill="paper")
        for u, d in ((0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)):
            x, y = P(W * u, D * d)
            cv.circle(x, y, min(W, D) * 0.14, "fixture")
    elif k == "fridge":
        rect(0, 0, W, D, fill="paper")
        x, y = P(W / 2, D / 2)
        cv.text(x, y - 0.15, "REF", size=4.5, anchor="middle")
    elif k in ("washer", "dryer"):
        rect(0, 0, W, D, fill="paper")
        x, y = P(W / 2, D / 2)
        if k == "washer":
            cv.circle(x, y, min(W, D) * 0.33, "fixture")
        cv.text(x, y - 0.15, "W" if k == "washer" else "D", size=4.5, anchor="middle")
    elif k == "tub":
        rect(0, 0, W, D, fill="paper")
        rect(0.25, 0.2, W - 0.25, D - 0.2)
        x, y = P(W - 0.6, D / 2)
        cv.circle(x, y, 0.1, "fixture")
    elif k == "shower":
        rect(0, 0, W, D, fill="paper")
        cv.line(P(0, 0), P(W, D), "fixture")
        cv.line(P(W, 0), P(0, D), "fixture")
        x, y = P(W / 2, D / 2)
        cv.circle(x, y, 0.12, "fixture", fill="paper")
    elif k == "toilet":
        rect(0.05, 0, W - 0.05, 0.6, fill="paper")
        pts = [P(W / 2 + u, 0.6 + v) for u, v in ellipse(0, (D - 0.6) / 2, W * 0.42, (D - 0.6) / 2)]
        cv.polyline(pts, "fixture", closed=True, fill="paper")
    elif k == "vanity":
        rect(0, 0, W, D, fill="paper")
        n = 2 if W >= 4.5 else 1
        for i in range(n):
            cu = W * (i + 0.5) / n
            pts = [P(cu + u, D / 2 + v) for u, v in ellipse(0, 0, min(0.65, W / n * 0.32), D * 0.28)]
            cv.polyline(pts, "fixture", closed=True)
    elif k == "closet":
        rect(0, 0, W, D, "hidden")
        cv.line(P(0.1, D / 2), P(W - 0.1, D / 2), "hidden")
        cv.line(P(0, 1.0), P(W, 1.0), "fixture")  # shelf line
    else:
        rect(0, 0, W, D)
