"""Single views (a plan, an elevation) rendered frameless for the app's concept screen."""
from __future__ import annotations

from dataclasses import dataclass

from ..render import themes
from ..render.backends import sheet_to_svg
from ..render.canvas import Canvas, Sheet
from ..views.elevation_view import ElevationView
from ..views.plan import PlanView
from ..views.scene import build_scene


@dataclass
class ViewImage:
    svg: str
    width: float  # inches
    height: float
    k: float  # inches per foot
    ox: float
    oy: float

    def to_px(self, x: float, y: float, rx: float, ry: float, rw: float, rh: float):
        """Model feet -> widget pixels, for a render into the rect (rx, ry, rw, rh)."""
        sx = (self.ox + x * self.k) / self.width
        sy = 1 - (self.oy + y * self.k) / self.height
        return rx + sx * rw, ry + sy * rh


def _fit(bounds, w, h, pad=0.35):
    bw, bh = bounds[2] - bounds[0], bounds[3] - bounds[1]
    k = min((w - 2 * pad) / bw, (h - 2 * pad) / bh)
    ox = (w - bw * k) / 2 - bounds[0] * k
    oy = (h - bh * k) / 2 - bounds[1] * k
    return k, ox, oy


def plan_image(house, level_index: int, w: float = 9.0, h: float = 8.0, theme: str = "noir") -> ViewImage:
    th = themes.get(theme)
    v = PlanView(house, house.all_levels[level_index])
    b = v.bounds
    sheet = Sheet("", "", w, h)
    cv = Canvas(sheet)
    k, ox, oy = _fit((b[0], b[1], b[2] - 4.0, b[3] - 4.0), w, h)
    cv.set_transform(k, ox, oy)
    v.draw(cv, th, None, labels=False, dims=False)
    return ViewImage(sheet_to_svg(sheet, th), w, h, k, ox, oy)


def elevation_image(house, face: str = "S", w: float = 12.0, h: float = 8.0,
                    theme: str = "noir", faces=None) -> ViewImage:
    th = themes.get(theme)
    faces = faces or build_scene(house)[0]
    ev = ElevationView(house, faces, face)
    x0, y0, x1, y1 = ev.extent
    sheet = Sheet("", "", w, h)
    cv = Canvas(sheet)
    k, ox, oy = _fit((x0 - 2, -1, x1 + 2, y1 + 2), w, h, pad=0.2)
    cv.set_transform(k, ox, oy)
    ev.draw(cv, th, markers=False)
    svg = sheet_to_svg(sheet, th).replace('fill="#000000"', 'fill="#08090b"', 1)  # match the pane
    return ViewImage(svg, w, h, k, ox, oy)
