"""Exterior elevations: projected scene, hidden lines removed, hatched by material."""
from __future__ import annotations

import math

from shapely.geometry import box
from shapely.ops import unary_union

from ..geometry import hatch_lines, polygons_of
from ..model import FACE_NAMES, House
from ..render.canvas import Canvas
from ..render.themes import Theme
from .common import fmt_ft
from .hlr import Projected, elevation
from .scene import Face3D

EDGE_ROLE = {"window": "thin", "door": "thin", "rail": "thin", "trim": "thin", "skirt": "thin", "step": "thin",
             "fascia": "outline", "roof": "outline"}
# (angle, spacing) per hatch kind, in feet
HATCH = {"lap": [(0, 0.42)], "clapboard": [(0, 0.33)], "shingle": [(0, 0.5)],
         "brick": [(0, 0.25)], "lattice": [(45, 0.55), (-45, 0.55)], "roofing": [(0, 0.75)],
         "board-and-batten": [(90, 1.0)], "wood": [(90, 0.4)],
         "seam": [(90, 1.4)],                     # standing-seam metal roof
         "tile": [(0, 0.45), (90, 0.9)],          # clay tile courses
         "timber": [(90, 2.2), (0, 3.0)]}         # half-timbering

TITLES = {"S": "South Elevation (Front)", "N": "North Elevation (Rear)",
          "E": "East Elevation", "W": "West Elevation"}


def stone_lines(region, course: float = 0.55):
    """Ledgestone coursing: horizontal beds with staggered short joints."""
    from shapely.geometry import LineString
    from ..geometry import lines_of
    out = []
    x0, y0, x1, y1 = region.bounds
    k = math.floor(y0 / course)
    while k * course <= y1:
        y = k * course
        out += lines_of(LineString([(x0 - 1, y), (x1 + 1, y)]).intersection(region))
        step = 1.6 + (k % 3) * 0.55
        x = x0 + ((k * 0.9) % step)
        while x < x1:
            out += lines_of(LineString([(x, y), (x, y + course)]).intersection(region))
            x += step
        k += 1
    return out


class ElevationView:
    def __init__(self, house: House, faces: list[Face3D], view: str):
        self.house = house
        self.view = view
        self.items: list[Projected] = elevation(faces, view)
        self.ridge = max((max(z for _, _, z in f.pts) for f in faces if f.role == "roof"),
                         default=None)
        polys = [it.poly for it in self.items]
        self.extent = unary_union(polys).bounds if polys else (0, 0, 1, 1)
        x0, y0, x1, y1 = self.extent
        self.bounds = (x0 - 1.5, -1.0, x1 + 6.5, y1 + 0.5)  # room for grade and level markers

    @property
    def title(self) -> str:
        return TITLES[self.view]

    def draw(self, cv: Canvas, theme: Theme, markers: bool = True) -> None:
        # fills first: glass and roof tones
        for it in self.items:
            role = it.face.role
            if role in ("window", "rail"):
                cv.geom(it.visible, "none", fill="glass", stroke=False)
            elif role == "roof":
                cv.geom(it.visible, "none", fill="roof", stroke=False)
        for it in self.items:
            if it.face.hatch == "stone":
                for poly in polygons_of(it.visible):
                    cv.lines(stone_lines(poly), "hatch")
                continue
            h = it.face.hatch
            if h and theme.hatches.get(h) and h in HATCH:
                for poly in polygons_of(it.visible):
                    if poly.area < 0.05:
                        continue
                    for ang, sp in HATCH[h]:
                        cv.lines(hatch_lines(poly, ang, sp), "hatch")
        for it in self.items:
            cv.lines(it.visible_details, "detail")
        for it in self.items:
            cv.lines(it.visible_edges, EDGE_ROLE.get(it.face.role, "outline"))
        x0, _, x1, _ = self.extent
        cv.line((x0 - 3, 0), (x1 + 3, 0), "grade")
        if markers:
            self._markers(cv)

    def _markers(self, cv: Canvas) -> None:
        x1 = self.extent[2]
        marks = []
        for lv in self.house.levels:
            marks.append((lv.floor_z, f"{lv.name.upper()}", f"FF +{fmt_ft(lv.floor_z)}"))
        top = self.house.levels[-1]
        marks.append((top.plate_z, "TOP OF PLATE", f"+{fmt_ft(top.plate_z)}"))
        ridge = self.ridge
        if ridge:
            marks.append((ridge, "RIDGE", f"+{fmt_ft(ridge)}"))
        r = 0.06 / cv.k
        for z, name, val in marks:
            cv.line((x1 + 0.5, z), (x1 + 3.2, z), "hidden")
            cv.circle(x1 + 3.2 + r, z, r, "thin")
            cv.polyline([(x1 + 3.2, z), (x1 + 3.2 + r, z), (x1 + 3.2 + r, z + r)], "thin",
                        closed=True, fill="ink")
            cv.text(x1 + 3.2 + 2.6 * r, z + 0.02 / cv.k, name, size=5.5, font="title")
            cv.text(x1 + 3.2 + 2.6 * r, z - 0.1 / cv.k, val, size=5.5)


def face_title(view: str) -> str:
    return f"{FACE_NAMES[view]} Elevation"


__all__ = ["ElevationView", "box"]
