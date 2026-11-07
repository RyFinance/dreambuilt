"""Roof plan: faces, ridges/hips/valleys, slope arrows, chimney, walls below dashed."""
from __future__ import annotations

from shapely.geometry import box

from ..geometry import hatch_lines, polygons_of
from ..model import House
from ..render.canvas import Canvas
from ..render.themes import Theme
from ..roof.analytic import build_roof, eave_rect, overhead
from .common import arrow, dim


def _pitch(p: float) -> str:
    return f"{p:g}:12"


class RoofPlanView:
    def __init__(self, house: House):
        self.house = house
        self.roof = build_roof(house)
        x0, y0, x1, y1 = self.roof.eave_outline.bounds
        for c in house.chimneys:
            x0, y0 = min(x0, c.x), min(y0, c.y)
            x1, y1 = max(x1, c.x + c.w), max(y1, c.y + c.h)
        self.bounds = (x0 - 0.5, y0 - 0.3, x1 + 3.0, y1 + 2.3)
        self.title = "Roof Plan"
        # from above, an overhead mass's eaves hide the lower roof beneath them
        by_name = {m.name: m for m in house.roofs}
        for f in self.roof.faces:
            m = by_name[f.mass]
            for other in house.roofs:
                if other is not m and overhead(m, other):
                    f.plan = f.plan.difference(eave_rect(other))

    def draw(self, cv: Canvas, theme: Theme) -> None:
        h = self.house
        for lv in h.levels[:1]:
            cv.geom(lv.footprint.exterior, "hidden")
        for f in self.roof.faces:
            for poly in polygons_of(f.plan):
                cv.geom(poly, "none", fill="roof", stroke=False)
                if theme.hatches.get("roofing"):
                    ang = 0 if f.slope[1] else 90
                    cv.lines(hatch_lines(poly, ang, 1.0), "hatch")
        for f in self.roof.faces:
            for poly in polygons_of(f.plan):
                cv.geom(poly.exterior, "ridge")
        cv.geom(self.roof.eave_outline.exterior, "heavy")
        for f in self.roof.faces:
            polys = polygons_of(f.plan)
            if not polys or max(p.area for p in polys) < 2.0:
                continue  # a slope that dies into a wall: nothing to label
            biggest = max(polys, key=lambda p: p.area)
            pt = biggest.representative_point()
            dx, dy = f.slope
            L = 3.0
            arrow(cv, (pt.x - dx * L / 2, pt.y - dy * L / 2), (pt.x + dx * L / 2, pt.y + dy * L / 2))
            cv.text(pt.x - dy * 0.9 + dx * 0.2, pt.y + dx * 0.9 - 0.25, _pitch(f.pitch), size=6,
                    anchor="middle")
        for c in h.chimneys:
            if c.base_z > 0:
                continue  # a fireplace box under the eaves doesn't show from above
            r = box(c.x, c.y, c.x + c.w, c.y + c.h)
            cv.geom(r, "cut", fill="paper")
            cv.lines(hatch_lines(r, 45, 0.4), "hatch")
            cv.rect(c.x + 0.5, c.y + 0.6, c.x + c.w - 0.5, c.y + c.h - 0.6, "thin")
        x0, y0, x1, y1 = self.roof.eave_outline.bounds
        dim(cv, (x0, y1), (x1, y1), 1.6)
        dim(cv, (x1, y1), (x1, y0), 1.6)
