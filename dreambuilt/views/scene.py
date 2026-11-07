"""3D scene of planar faces built from the house model, for orthographic views."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import LineString

from .. import styles
from ..model import House, Level, Opening
from ..roof.analytic import RoofModel, build_roof

Pt3 = tuple[float, float, float]
OUT = {"S": (0, -1), "N": (0, 1), "E": (1, 0), "W": (-1, 0)}


@dataclass
class Face3D:
    pts: list[Pt3]
    role: str  # wall, foundation, gable, roof, fascia, window, door, trim, column, chimney, ...
    hatch: Optional[str] = None  # lap, shingle, brick, lattice, roofing
    lines: list[list[Pt3]] = field(default_factory=list)  # detail lines in the face plane


def parse_grille(grille: str) -> tuple[int, int]:
    up, _, low = grille.partition("/")
    return int(up or 0), int(low or 0)


def lite_grid(n: int) -> tuple[int, int]:
    """Columns x rows for a sash with n lites."""
    return {0: (1, 1), 1: (1, 1), 2: (2, 1), 3: (3, 1), 4: (4, 1), 5: (5, 1), 6: (3, 2),
            8: (4, 2), 9: (3, 3), 12: (4, 3)}.get(n, (n, 1))


def edge_face(edge, z0: float, z1: float, out: float = 0.0) -> list[Pt3]:
    (xa, ya), (xb, yb) = edge
    nx, ny = _normal(edge)
    return [(xa + nx * out, ya + ny * out, z0), (xb + nx * out, yb + ny * out, z0),
            (xb + nx * out, yb + ny * out, z1), (xa + nx * out, ya + ny * out, z1)]


def _normal(edge) -> tuple[float, float]:
    """Outward normal of a CCW exterior ring edge."""
    (xa, ya), (xb, yb) = edge
    dx, dy = xb - xa, yb - ya
    L = (dx * dx + dy * dy) ** 0.5
    return (dy / L, -dx / L)


def box_faces(x0, y0, z0, x1, y1, z1, role, hatch=None) -> list[Face3D]:
    return [
        Face3D([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], role, hatch),
        Face3D([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], role, hatch),
        Face3D([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], role, hatch),
        Face3D([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], role, hatch),
    ]


def frustum_faces(cx, cy, z0, z1, w0, w1, role) -> list[Face3D]:
    """Square column tapering from w0 at z0 to w1 at z1."""
    a, b = w0 / 2, w1 / 2
    bot = [(cx - a, cy - a), (cx + a, cy - a), (cx + a, cy + a), (cx - a, cy + a)]
    top = [(cx - b, cy - b), (cx + b, cy - b), (cx + b, cy + b), (cx - b, cy + b)]
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        faces.append(Face3D([(*bot[i], z0), (*bot[j], z0), (*top[j], z1), (*top[i], z1)], role))
    return faces


@dataclass
class OpeningPlacement:
    opening: Opening
    edge: tuple[tuple[float, float], tuple[float, float]]
    a: float  # start/end along the edge, as fractions
    b: float
    level: Level

    def plan_points(self):
        (xa, ya), (xb, yb) = self.edge
        p = (xa + (xb - xa) * self.a, ya + (yb - ya) * self.a)
        q = (xa + (xb - xa) * self.b, ya + (yb - ya) * self.b)
        return p, q


def place_opening(level: Level, op: Opening) -> Optional[OpeningPlacement]:
    """Find the exterior edge carrying `op` and its span along that edge."""
    ring = list(level.footprint.exterior.coords)
    if level.footprint.exterior.is_ccw is False:
        ring = ring[::-1]
    nx_want, ny_want = OUT[op.face]
    best = None
    for e in zip(ring, ring[1:]):
        nx, ny = _normal(e)
        if abs(nx - nx_want) > 1e-6 or abs(ny - ny_want) > 1e-6:
            continue
        (xa, ya), (xb, yb) = e
        if op.face in ("S", "N"):
            line, lo, hi, s0, s1 = ya, min(xa, xb), max(xa, xb), xa, xb
        else:
            line, lo, hi, s0, s1 = xa, min(ya, yb), max(ya, yb), ya, yb
        if op.line is not None and abs(op.line - line) > 1e-6:
            continue
        if op.start < lo - 1e-6 or op.start + op.width > hi + 1e-6:
            continue
        a = (op.start - s0) / (s1 - s0)
        b = (op.start + op.width - s0) / (s1 - s0)
        a, b = min(a, b), max(a, b)
        # prefer the outermost edge on that face
        key = -line if op.face in ("S", "W") else line
        if best is None or key > best[0]:
            best = (key, OpeningPlacement(op, e, a, b, level))
    return best[1] if best else None


class SceneBuilder:
    def __init__(self, house: House):
        self.house = house
        self.style = styles.get(house.style)
        self.roof: RoofModel = build_roof(house)
        self.faces: list[Face3D] = []

    def build(self) -> list[Face3D]:
        h = self.house
        siding = self.style.get("siding", {})
        for i, lv in enumerate(h.levels):
            top = i == len(h.levels) - 1
            # stop just under the plate so the wall top tucks behind the eave
            z1 = lv.plate_z - 0.05 if top else lv.plate_z + lv.floor_depth
            fp = lv.footprint
            ring = list(fp.exterior.coords)
            if not fp.exterior.is_ccw:
                ring = ring[::-1]
            for e in zip(ring, ring[1:]):
                self.faces.append(Face3D(edge_face(e, lv.floor_z, z1), "wall",
                                         self._finish(i, e, siding.get("walls", "lap"))))
                if i == 0:
                    self.faces.append(Face3D(edge_face(e, 0.0, lv.floor_z), "foundation"))
            for op in lv.openings:
                pl = place_opening(lv, op)
                if pl is not None:
                    self._opening(pl)
        details = set(self.style.get("details", []))
        if h.basement:
            for op in h.basement.openings:
                if op.kind != "window":
                    continue  # suite doors sit down in their stairwells, below grade
                top = h.basement.floor_z + op.sill + op.height
                if top <= 0.4:
                    continue
                pl = place_opening(h.basement, op)
                if pl is None:
                    continue
                vis = Opening(op.kind, op.face, op.start, op.width, top - 0.05, 0.05 - h.basement.floor_z,
                              op.grille or "0/0", "fixed", line=op.line)
                self._opening(OpeningPlacement(vis, pl.edge, pl.a, pl.b, h.basement))
        for g in self.roof.gables:
            self.faces.append(Face3D(g.points, "gable", g.cladding or siding.get("gables", "shingle")))
            if "gable-windows" in details and g.face == "S":
                self._gable_window(g)
        for f in self.roof.faces:
            from ..geometry import polygons_of
            for poly in polygons_of(f.plan.simplify(1e-6)):
                self.faces.append(Face3D(f.points3d(poly), "roof",
                                         {"seam": "seam", "tile": "tile"}.get(self.style.get("roof", {}).get("texture"), "roofing")))
        for b in self.roof.fascia:
            self.faces.append(Face3D(b, "fascia"))
        for p in h.porches:
            self._porch(p)
        for b in h.balconies:
            self._balcony(b)
        for d in h.dormers:
            self._dormer(d, siding.get("walls", "lap"))
        for c in h.chimneys:
            # a clean stone box pushed out of the wall: the flue vents through the roof,
            # so no crown, cap or pipe
            self.faces += box_faces(c.x, c.y, c.base_z, c.x + c.w, c.y + c.h, c.top_z, "chimney", "stone")
        return self.faces

    def _finish(self, level: int, e, default: str) -> str:
        """The wall finish for one face: a cladding zone if one covers it, else the style's."""
        (x0, y0), (x1, y1) = e[0][:2], e[1][:2]
        dx, dy = x1 - x0, y1 - y0
        nx, ny = dy, -dx  # outward for a counter-clockwise ring
        if abs(nx) > abs(ny):
            face, mid = ("E" if nx > 0 else "W"), (y0 + y1) / 2
        else:
            face, mid = ("N" if ny > 0 else "S"), (x0 + x1) / 2
        for c in self.house.claddings:
            if c.level == level and c.face == face and c.a - 1e-6 <= mid <= c.b + 1e-6:
                return c.hatch
        return default

    # -- openings ---------------------------------------------------------
    def _opening(self, pl: OpeningPlacement) -> None:
        op, lv = pl.opening, pl.level
        win = self.style.get("windows", {})
        trim = win.get("trim", 0.42)
        p, q = pl.plan_points()
        e = (p, q)
        z0 = lv.floor_z + op.sill
        z1 = z0 + op.height
        nx, ny = _normal(pl.edge)
        tx, ty = q[0] - p[0], q[1] - p[1]
        L = (tx * tx + ty * ty) ** 0.5
        tx, ty = tx / L, ty / L

        def at(s, z, out):
            return (p[0] + tx * s + nx * out, p[1] + ty * s + ny * out, z)

        w = op.width
        lines: list[list[Pt3]] = []
        if op.kind == "window":
            grille = op.grille or win.get("grille", "1/1")
            up, low = parse_grille(grille)
            o = 0.04
            if op.operation == "double-hung":
                zm = z0 + op.height / 2
                lines.append([at(0, zm, o), at(w, zm, o)])
                lines += _grid(at, 0, w, zm, z1, up, o)
                lines += _grid(at, 0, w, z0, zm, low, o)
            else:
                lines += _grid(at, 0, w, z0, z1, max(up, 1), o, vertical_only=op.operation != "fixed")
            # inner sash outline
            m = 0.17
            lines.append([at(m, z0 + m, o), at(w - m, z0 + m, o), at(w - m, z1 - m, o),
                          at(m, z1 - m, o), at(m, z0 + m, o)])
            self.faces.append(Face3D([at(0, z0, o), at(w, z0, o), at(w, z1, o), at(0, z1, o)],
                                     "window", lines=lines))
            self.faces.append(Face3D([at(-0.15, z0 - 0.25, 0.12), at(w + 0.15, z0 - 0.25, 0.12),
                                      at(w + 0.15, z0, 0.12), at(-0.15, z0, 0.12)], "trim"))
            if "window-hoods" in self.style.get("details", []) and op.face == "S" and w >= 2.5 \
                    and not self._under_roof(p, q, z1):
                self._hood(at, w, z1)
        elif op.kind == "garage":
            o = 0.04
            for k in range(1, 4):  # sectional overhead door: four panels
                z = z0 + op.height * k / 4
                lines.append([at(0.15, z, o), at(w - 0.15, z, o)])
            for s_ in range(1, int(w // 2)):
                x = w * s_ / int(w // 2)
                for k in range(4):
                    za, zb = z0 + op.height * k / 4 + 0.35, z0 + op.height * (k + 1) / 4 - 0.35
                    lines.append([at(x, za, o), at(x, zb, o)])
            self.faces.append(Face3D([at(0, z0, o), at(w, z0, o), at(w, z1, o), at(0, z1, o)],
                                     "door", lines=lines))
        else:
            o = 0.04
            lites = self.style.get("front_door", {}).get("lites", 1) if op.face == "S" else 1
            panels = self.style.get("front_door", {}).get("panels", 2)
            m = 0.25
            if lites:
                zl = z1 - op.height * 0.28
                lines += _grid(at, m, w - m, zl, z1 - m, lites, o, vertical_only=True)
                lines.append([at(m, zl, o), at(w - m, zl, o), at(w - m, z1 - m, o),
                              at(m, z1 - m, o), at(m, zl, o)])
                ztop = zl - 0.3
            else:
                ztop = z1 - m
            n = max(panels, 1) if panels <= 2 else 2
            pw = (w - 2 * m - (n - 1) * 0.25) / n
            for k in range(n):
                s0 = m + k * (pw + 0.25)
                lines.append([at(s0, z0 + 0.5, o), at(s0 + pw, z0 + 0.5, o),
                              at(s0 + pw, ztop, o), at(s0, ztop, o), at(s0, z0 + 0.5, o)])
            self.faces.append(Face3D([at(0, z0, o), at(w, z0, o), at(w, z1, o), at(0, z1, o)],
                                     "door", lines=lines))
        # head and jamb trim boards
        t = trim
        self.faces.append(Face3D([at(-t, z1, 0.08), at(w + t, z1, 0.08),
                                  at(w + t, z1 + t * 1.25, 0.08), at(-t, z1 + t * 1.25, 0.08)], "trim"))
        zb = z0 - (0.25 if op.kind == "window" else 0)
        self.faces.append(Face3D([at(-t, zb, 0.08), at(0, zb, 0.08), at(0, z1, 0.08),
                                  at(-t, z1, 0.08)], "trim"))
        self.faces.append(Face3D([at(w, zb, 0.08), at(w + t, zb, 0.08), at(w + t, z1, 0.08),
                                  at(w, z1, 0.08)], "trim"))

    def _under_roof(self, p, q, z1) -> bool:
        """True when a porch or lower roof already shelters this window head."""
        from shapely.geometry import LineString
        seg = LineString([p, q]).buffer(1.5)
        for f in self.roof.faces:
            if f.plan.intersects(seg):
                mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2 - 1.0
                if f.plane.z(mx, my) < z1 + 4.0:
                    return True
        return False

    # -- character details ---------------------------------------------
    def _dormer(self, d, hatch) -> None:
        """The dormer's front wall with its window, and the two triangular cheeks back to the
        roof (its gable and roof come from its RoofMass)."""
        y, x0, x1 = d.y, d.x, d.x + d.w
        self.faces.append(Face3D([(x0, y, d.base_z), (x1, y, d.base_z), (x1, y, d.plate_z), (x0, y, d.plate_z)],
                                 "wall", hatch))
        run = (d.plate_z - d.base_z) * 12 / max(self._slope(), 1)
        for x in (x0, x1):
            self.faces.append(Face3D([(x, y, d.base_z), (x, y, d.plate_z), (x, y + run, d.plate_z)], "wall", hatch))
        w = min(3.0, d.w - 1.5)
        z0, z1 = d.base_z + 0.6, d.plate_z - 0.4
        cx = (x0 + x1) / 2
        self.faces.append(Face3D([(cx - w / 2, y - 0.05, z0), (cx + w / 2, y - 0.05, z0),
                                  (cx + w / 2, y - 0.05, z1), (cx - w / 2, y - 0.05, z1)], "window",
                                 lines=[[(cx, y - 0.06, z0), (cx, y - 0.06, z1)]]))

    def _slope(self) -> float:
        main = next((m for m in self.house.roofs if m.name == "Main"), None)
        return main.pitch if main else 8.0

    def _gable_window(self, g) -> None:
        """A window centred in a street-facing gable: round in a stone gable, square otherwise."""
        (xa, ya, za), (xb, yb, _), (xm, ym, zr) = g.points
        height = zr - za
        if height < 4.5 or abs(xb - xa) < 8:
            return
        y = min(ya, yb) - 0.06
        cx = (xa + xb) / 2
        zc = za + height * 0.42
        if g.cladding == "stone":
            r = min(1.4, height * 0.16)
            ring = [(cx + r * math.cos(t), y, zc + r * math.sin(t))
                    for t in [2 * math.pi * i / 28 for i in range(28)]]
            trim = [(cx + (r + 0.35) * math.cos(t), y + 0.02, zc + (r + 0.35) * math.sin(t))
                    for t in [2 * math.pi * i / 28 for i in range(28)]]
            self.faces.append(Face3D(ring, "window", lines=[[(cx - r, y - 0.01, zc), (cx + r, y - 0.01, zc)],
                                                           [(cx, y - 0.01, zc - r), (cx, y - 0.01, zc + r)]]))
            self.faces.append(Face3D(trim, "trim"))
        else:
            w, h = 2.5, min(3.5, height * 0.4)
            z0 = zc - h / 2
            pts = [(cx - w / 2, y, z0), (cx + w / 2, y, z0), (cx + w / 2, y, z0 + h), (cx - w / 2, y, z0 + h)]
            mid = [(cx - w / 2, y - 0.01, z0 + h * 0.62), (cx + w / 2, y - 0.01, z0 + h * 0.62)]
            v = [(cx, y - 0.01, z0 + h * 0.62), (cx, y - 0.01, z0 + h)]
            self.faces.append(Face3D(pts, "window", lines=[mid, v]))
            t = 0.4
            self.faces.append(Face3D([(cx - w / 2 - t, y + 0.03, z0 - t), (cx + w / 2 + t, y + 0.03, z0 - t),
                                      (cx + w / 2 + t, y + 0.03, z0 + h + t), (cx - w / 2 - t, y + 0.03, z0 + h + t)],
                                     "trim"))

    def _hood(self, at, w: float, z1: float) -> None:
        """Little shed roof over a window: sloped top and a front fascia."""
        o, d, rise = 0.15, 1.3, 0.7
        top = [at(-0.6, z1 + 0.9, o), at(w + 0.6, z1 + 0.9, o), at(w + 0.6, z1 + 0.9 - rise, d),
               at(-0.6, z1 + 0.9 - rise, d)]
        self.faces.append(Face3D(top, "roof"))
        self.faces.append(Face3D([at(-0.6, z1 + 0.9 - rise - 0.35, d), at(w + 0.6, z1 + 0.9 - rise - 0.35, d),
                                  at(w + 0.6, z1 + 0.9 - rise, d), at(-0.6, z1 + 0.9 - rise, d)], "fascia"))

    # -- balcony ----------------------------------------------------------
    def _balcony(self, b) -> None:
        lv = self.house.levels[min(b.level, len(self.house.levels) - 1)]
        z = lv.floor_z
        ring = lv.footprint.exterior
        from shapely.geometry import Point
        pts = [(b.x, b.y), (b.x + b.w, b.y), (b.x + b.w, b.y + b.h), (b.x, b.y + b.h)]
        for e in zip(pts, pts[1:] + pts[:1]):
            mid = ((e[0][0] + e[1][0]) / 2, (e[0][1] + e[1][1]) / 2)
            if ring.distance(Point(mid)) < 0.05:
                continue  # the side against the house
            self.faces.append(Face3D(edge_face(e, z - 0.75, z), "porch"))
            rail = edge_face(e, z, z + 3.5, 0.02)
            top = [rail[3], rail[2]]
            self.faces.append(Face3D(rail, "rail", lines=[top, [rail[0], rail[1]]]))

    # -- porch ------------------------------------------------------------
    def _porch_plate(self, p) -> float:
        """Plate of the lowest roof mass over the porch's centre."""
        cx, cy = p.x + p.w / 2, p.y + p.h / 2
        over = [m.plate_z for m in self.house.roofs
                if m.x <= cx <= m.x + m.w and m.y <= cy <= m.y + m.h]
        return min(over) if over else self.house.levels[0].plate_z

    def _porch(self, p) -> None:
        x0, y0, x1, y1 = p.x, p.y, p.x + p.w, p.y + p.h
        fz = p.floor_z
        rim = max(fz - 0.6, 0.0)
        # every deck edge that isn't against the house wall
        from shapely.geometry import Point
        ring = self.house.levels[0].footprint.exterior
        edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
        edges = [e for e in edges if ring.distance(Point((e[0][0] + e[1][0]) / 2,
                                                         (e[0][1] + e[1][1]) / 2)) > 0.05]
        for e in edges:
            self.faces.append(Face3D(edge_face(e, rim, fz), "porch"))
            if rim > 0:
                self.faces.append(Face3D(edge_face(e, 0.0, rim, -0.05), "skirt", "lattice"))
        # just under the plate, so the beam top never ties with the roof plane
        beam_top = (p.beam_z or self._porch_plate(p)) - 0.05
        bz = beam_top - 1.0
        cw = 1.67
        for cx, cy in p.columns:
            pz = fz + p.pier_height if p.pier_height else fz
            if p.pier_height:
                self.faces += box_faces(cx - cw / 2, cy - cw / 2, fz, cx + cw / 2, cy + cw / 2, pz,
                                        "pier", "brick")
            if p.column == "tapered":
                self.faces += frustum_faces(cx, cy, pz, bz, 1.25, 0.83, "column")
            elif p.column != "none":
                self.faces += frustum_faces(cx, cy, pz, bz, 0.75, 0.75, "column")
        if p.columns:
            fp = self.house.levels[0].footprint.bounds
            rear = y0 >= fp[3] - 0.05
            cy = max(c[1] for c in p.columns) if rear else min(c[1] for c in p.columns)
            self.faces += box_faces(x0, cy - 0.5, bz, x1, cy + 0.5, beam_top, "beam")
            for cx in sorted({c[0] for c in p.columns}):
                if abs(cx - x0) < 2 or abs(cx - x1) < 2:
                    ya, yb = (y0, cy) if rear else (cy, y1)
                    self.faces += box_faces(cx - 0.4, ya, bz, cx + 0.4, yb, beam_top, "beam")
        for st in p.steps:
            n = st.risers
            rise = fz / n
            for k in range(1, n):
                depth = (n - k)
                if st.face == "S":
                    self.faces += box_faces(st.x, y0 - depth, 0, st.x + st.width, y0, k * rise, "step")
                elif st.face == "N":
                    self.faces += box_faces(st.x, y1, 0, st.x + st.width, y1 + depth, k * rise, "step")


def _grid(at, s0, s1, z0, z1, n, out, vertical_only=False):
    cols, rows = lite_grid(n)
    lines = []
    for c in range(1, cols):
        s = s0 + (s1 - s0) * c / cols
        lines.append([at(s, z0, out), at(s, z1, out)])
    if not vertical_only:
        for r in range(1, rows):
            z = z0 + (z1 - z0) * r / rows
            lines.append([at(s0, z, out), at(s1, z, out)])
    return lines


def build_scene(house: House) -> tuple[list[Face3D], RoofModel]:
    sb = SceneBuilder(house)
    return sb.build(), sb.roof


__all__ = ["Face3D", "build_scene", "place_opening", "OpeningPlacement", "LineString"]
