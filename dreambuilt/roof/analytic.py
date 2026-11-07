"""Analytic roofs: gable and hip masses over rectangles, joined into cross-gables.

Each mass is convex, so its surface height is the minimum of its face planes.
Where masses overlap, a face survives only where it sits above the other
mass's surface. That rule produces valleys and buried ridges without any
special cases, and covers rectangle and L footprints (an L is two masses).
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from ..geometry import halfplane, polygons_of
from ..model import House, RoofMass

FASCIA = 0.6  # depth of the fascia / rake board, feet


@dataclass
class Plane:
    a: float
    b: float
    c: float  # z = a*x + b*y + c

    def z(self, x: float, y: float) -> float:
        return self.a * x + self.b * y + self.c

    @staticmethod
    def through(p1, p2, p3) -> "Plane":
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = p1, p2, p3
        det = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
        a = ((z2 - z1) * (y3 - y1) - (z3 - z1) * (y2 - y1)) / det
        b = ((x2 - x1) * (z3 - z1) - (x3 - x1) * (z2 - z1)) / det
        return Plane(a, b, z1 - a * x1 - b * y1)


@dataclass
class RoofFace:
    mass: str
    plane: Plane
    plan: Polygon  # visible part, in plan
    slope: tuple[float, float]  # downhill direction in plan
    pitch: float

    def points3d(self, poly: Polygon) -> list[tuple[float, float, float]]:
        return [(x, y, self.plane.z(x, y)) for x, y in list(poly.exterior.coords)[:-1]]


@dataclass
class GableWall:
    mass: str
    points: list[tuple[float, float, float]]
    face: str
    cladding: str = ""


@dataclass
class RoofModel:
    faces: list[RoofFace]
    gables: list[GableWall]
    fascia: list[list[tuple[float, float, float]]]
    eave_outline: Polygon
    masses: list[RoofMass]

    def ridge_z(self) -> float:
        return max(f.plane.z(x, y) for f in self.faces
                   for p in polygons_of(f.plan) for x, y in p.exterior.coords)


def z_range(m: RoofMass) -> tuple[float, float]:
    """Lowest eave and highest point of a mass."""
    s = m.pitch / 12.0
    if m.kind == "shed":
        run = m.h if m.low_side in ("S", "N") else m.w
    else:
        run = (m.h if m.ridge == "x" else m.w) / 2
    return m.plate_z - m.overhang * s, m.plate_z + run * s


def overhead(m: RoofMass, other: RoofMass) -> bool:
    """True when `other` sits wholly above `m`, so it covers it without intersecting."""
    return z_range(other)[0] > z_range(m)[1]


def eave_rect(m: RoofMass) -> Polygon:
    o = m.overhang
    x0, y0, x1, y1 = m.x - o, m.y - o, m.x + m.w + o, m.y + m.h + o
    if m.kind == "shed":  # no overhang on the high side, where it meets the wall
        high = {"S": "N", "N": "S", "E": "W", "W": "E"}[m.low_side]
        x0, y0, x1, y1 = {"N": (x0, y0, x1, m.y + m.h), "S": (x0, m.y, x1, y1),
                          "E": (x0, y0, m.x + m.w, y1), "W": (m.x, y0, x1, y1)}[high]
    return box(x0, y0, x1, y1)


def _mass_faces(m: RoofMass) -> list[tuple[Plane, Polygon, tuple[float, float]]]:
    """Full (unclipped) faces of one mass: (plane, plan polygon, downhill direction)."""
    s = m.pitch / 12.0
    o = m.overhang
    x0, y0, x1, y1 = m.x - o, m.y - o, m.x + m.w + o, m.y + m.h + o
    ze = m.plate_z - o * s
    out = []
    if m.kind == "shed":
        rect = eave_rect(m)
        plane = {"S": Plane(0, s, ze - s * y0), "N": Plane(0, -s, ze + s * y1),
                 "W": Plane(s, 0, ze - s * x0), "E": Plane(-s, 0, ze + s * x1)}[m.low_side]
        slope = {"S": (0, -1), "N": (0, 1), "W": (-1, 0), "E": (1, 0)}[m.low_side]
        return [(plane, rect, slope)]
    if m.ridge == "x":
        ym = m.y + m.h / 2
        zr = ze + (ym - y0) * s
        south = Polygon([(x0, y0), (x1, y0), (x1, ym), (x0, ym)])
        north = Polygon([(x0, ym), (x1, ym), (x1, y1), (x0, y1)])
        if m.kind == "hip":
            d = ym - y0
            south = Polygon([(x0, y0), (x1, y0), (x1 - d, ym), (x0 + d, ym)])
            north = Polygon([(x0 + d, ym), (x1 - d, ym), (x1, y1), (x0, y1)])
            out.append((Plane.through((x1, y0, ze), (x1, y1, ze), (x1 - d, ym, zr)),
                        Polygon([(x1, y0), (x1, y1), (x1 - d, ym)]), (1, 0)))
            out.append((Plane.through((x0, y0, ze), (x0, y1, ze), (x0 + d, ym, zr)),
                        Polygon([(x0, y1), (x0, y0), (x0 + d, ym)]), (-1, 0)))
        out.append((Plane(0, s, ze - s * y0), south, (0, -1)))
        out.append((Plane(0, -s, ze + s * y1), north, (0, 1)))
    else:
        xm = m.x + m.w / 2
        zr = ze + (xm - x0) * s
        west = Polygon([(x0, y0), (xm, y0), (xm, y1), (x0, y1)])
        east = Polygon([(xm, y0), (x1, y0), (x1, y1), (xm, y1)])
        if m.kind == "hip":
            d = xm - x0
            west = Polygon([(x0, y0), (xm, y0 + d), (xm, y1 - d), (x0, y1)])
            east = Polygon([(x1, y0), (x1, y1), (xm, y1 - d), (xm, y0 + d)])
            out.append((Plane.through((x0, y0, ze), (x1, y0, ze), (xm, y0 + d, zr)),
                        Polygon([(x0, y0), (x1, y0), (xm, y0 + d)]), (0, -1)))
            out.append((Plane.through((x0, y1, ze), (x1, y1, ze), (xm, y1 - d, zr)),
                        Polygon([(x1, y1), (x0, y1), (xm, y1 - d)]), (0, 1)))
        out.append((Plane(s, 0, ze - s * x0), west, (-1, 0)))
        out.append((Plane(-s, 0, ze + s * x1), east, (1, 0)))
    return out


def _gable_walls(m: RoofMass) -> list[GableWall]:
    if m.kind != "gable":
        return []
    s = m.pitch / 12.0
    walls = []
    if m.ridge == "x":
        ym, zr = m.y + m.h / 2, m.plate_z + m.h / 2 * s
        ends = {"W": m.x, "E": m.x + m.w}
        for face, x in ends.items():
            walls.append(GableWall(m.name, [(x, m.y, m.plate_z), (x, m.y + m.h, m.plate_z),
                                            (x, ym, zr)], face))
    else:
        xm, zr = m.x + m.w / 2, m.plate_z + m.w / 2 * s
        ends = {"S": m.y, "N": m.y + m.h}
        for face, y in ends.items():
            walls.append(GableWall(m.name, [(m.x, y, m.plate_z), (m.x + m.w, y, m.plate_z),
                                            (xm, y, zr)], face))
    if m.gable_ends:
        walls = [g for g in walls if g.face in m.gable_ends]
    for g in walls:
        g.cladding = m.cladding
    return walls


def build_roof(house: House) -> RoofModel:
    masses = house.roofs
    raw = {m.name: _mass_faces(m) for m in masses}
    faces: list[RoofFace] = []
    for m in masses:
        for plane, plan, slope in raw[m.name]:
            visible = plan
            for other in masses:
                if other is m or overhead(m, other):
                    continue
                rect = eave_rect(other)
                if not visible.intersects(rect):
                    continue
                # hidden where this plane is below every plane of the other mass
                below = rect
                for op, _, _ in raw[other.name]:
                    below = below.intersection(
                        halfplane(op.a - plane.a, op.b - plane.b, op.c - plane.c, rect.bounds))
                try:
                    visible = visible.difference(below)
                except Exception:  # a sliver from the pitch matching: snap to a fine grid and retry
                    import shapely
                    visible = shapely.set_precision(visible.buffer(0), 1e-4).difference(
                        shapely.set_precision(below.buffer(0), 1e-4))
            visible = visible.buffer(0)
            if visible.area > 1e-6:
                faces.append(RoofFace(m.name, plane, visible, slope, m.pitch))
    gables = [g for m in masses for g in _gable_walls(m)]
    outline = unary_union([eave_rect(m) for m in masses])
    fascia = _fascia(faces, outline)
    return RoofModel(faces, gables, fascia, outline, list(masses))


def _fascia(faces: list[RoofFace], outline: Polygon) -> list[list[tuple[float, float, float]]]:
    """Vertical boards hung under every face edge that lies on the eave outline."""
    ring = outline.exterior
    boards = []
    for f in faces:
        for poly in polygons_of(f.plan):
            pts = list(poly.exterior.coords)
            for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
                mid = ((xa + xb) / 2, (ya + yb) / 2)
                if ring.distance(_pt(mid)) > 1e-6:
                    continue
                za, zb = f.plane.z(xa, ya), f.plane.z(xb, yb)
                boards.append([(xa, ya, za), (xb, yb, zb), (xb, yb, zb - FASCIA),
                               (xa, ya, za - FASCIA)])
    return boards


def _pt(xy):
    from shapely.geometry import Point
    return Point(xy)


def roof_area(roof: RoofModel) -> float:
    """Sloped surface area of all faces, square feet."""
    total = 0.0
    for f in roof.faces:
        k = (1 + f.plane.a ** 2 + f.plane.b ** 2) ** 0.5
        total += f.plan.area * k
    return total


__all__ = ["Plane", "RoofFace", "RoofModel", "GableWall", "build_roof", "eave_rect",
           "roof_area", "FASCIA", "MultiPolygon"]
