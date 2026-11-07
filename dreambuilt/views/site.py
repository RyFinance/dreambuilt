"""Site plan: lot, setbacks, footprint, roof line, drive, walk, street."""
from __future__ import annotations

from shapely.affinity import translate
from shapely.geometry import Polygon, box

from ..geometry import hatch_lines
from ..model import House, Lot
from ..render.canvas import Canvas
from ..render.themes import Theme
from ..roof.analytic import build_roof
from .common import dim, fmt_area


def car(cv: Canvas, cx: float, cy: float, k: int = 0) -> None:
    """Top view of a parked car, nose toward the garage."""
    w, l = 6.2, 15.0
    x0, y0 = cx - w / 2, cy - l / 2
    body = box(x0, y0, x0 + w, y0 + l).buffer(1.1, join_style=1).buffer(-1.1, join_style=1)
    cv.geom(body, "outline", fill="paper")
    cv.geom(box(x0 + 0.7, y0 + l * 0.55, x0 + w - 0.7, y0 + l * 0.72), "thin")  # windshield
    cv.geom(box(x0 + 0.8, y0 + l * 0.18, x0 + w - 0.8, y0 + l * 0.3), "thin")  # rear glass
    cv.line((x0 + 0.6, y0 + l * 0.3), (x0 + 0.6, y0 + l * 0.55), "thin")
    cv.line((x0 + w - 0.6, y0 + l * 0.3), (x0 + w - 0.6, y0 + l * 0.55), "thin")
    _ = k


def shrub(cv: Canvas, x: float, y: float, r: float) -> None:
    """A clipped shrub: scalloped circle with a centre dot."""
    import math
    pts = []
    for i in range(24):
        a = 2 * math.pi * i / 24
        rr = r * (1 + 0.12 * math.cos(a * 6))
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
    cv.polyline(pts, "thin", closed=True, fill="paper")
    cv.circle(x, y, 0.15, "thin", fill="ink")


class SitePlanView:
    def __init__(self, house: House):
        self.house = house
        self.lot: Lot = house.lot or Lot(house.outline().bounds[2] + 20, 120)
        self.bounds = (-8.0, -36.0, self.lot.width + 12.0, self.lot.depth + 6.0)
        self.title = "Site Plan"

    def stats(self) -> list[tuple[str, str]]:
        lot = self.lot
        foot = self.house.outline()
        return [("Lot", f"{lot.width:g}' x {lot.depth:g}' ({fmt_area(lot.width * lot.depth)})"),
                ("Footprint incl. porch", fmt_area(foot.area)),
                ("Lot coverage", f"{100 * foot.area / (lot.width * lot.depth):.1f}%"),
                ("Setbacks", f"front {lot.front:g}', sides {lot.side:g}', rear {lot.rear:g}'")]

    def draw(self, cv: Canvas, theme: Theme) -> None:
        lot, h = self.lot, self.house
        W, D = lot.width, lot.depth
        mv = lambda g: translate(g, lot.house_x, lot.house_y)
        # street and sidewalk
        cv.line((-8, -6), (W + 12, -6), "outline")
        cv.line((-8, -10), (W + 12, -10), "outline")
        cv.line((-8, -12), (W + 12, -12), "thin")
        cv.line((-8, -34), (W + 12, -34), "thin")
        cv.line((-8, -23), (W + 12, -23), "hidden")
        cv.text(W / 2, -21.5, h.lot.street.upper() if h.lot else "STREET", size=9, anchor="middle",
                font="title", spacing=theme.title_spacing)
        # lot and setbacks
        cv.rect(0, 0, W, D, "lot")
        cv.rect(lot.side, lot.front, W - lot.side, D - lot.rear, "setback")
        foot = mv(h.outline())
        fx0, fy0, fx1, fy1 = foot.bounds
        roof = mv(build_roof(h).eave_outline)
        east, west = W - fx1, fx0
        garage = next((r for lv in h.levels[:1] for r in lv.rooms if r.kind == "garage"), None)
        if garage is not None:
            # drive straight out from the garage doors, flaring to the street
            gx0, gy0 = lot.house_x + garage.x, lot.house_y + garage.y
            gx1 = gx0 + garage.w
            drive = Polygon([(gx0 - 0.5, gy0), (gx1 + 0.5, gy0), (gx1 + 2.5, -10), (gx0 - 2.5, -10)])
            cv.geom(drive, "outline", fill="tone")
            n = 2 if garage.w >= 20 else 1
            for i in range(n):
                cx = gx0 + garage.w * (i + 0.5) / n
                car(cv, cx, gy0 - 10.5, i)
        elif max(east, west) >= 9:
            if east >= west:
                dx0, dx1 = W - min(10, east - 1) - 1, W - 1
            else:
                dx0, dx1 = 1, 1 + min(10, west - 1)
            drive = box(dx0, -10, dx1, fy1 + 6)
            cv.geom(drive, "outline", fill="tone")
            cv.text((dx0 + dx1) / 2, fy1 - 4, "DRIVE", size=6, anchor="middle", rotate=90)
        # front walk to the porch steps
        for p in h.porches:
            for st in p.steps:
                if st.face == "S":
                    x0 = lot.house_x + st.x + st.width / 2 - 2
                    y_top = lot.house_y + p.y - (st.risers - 1)
                    cv.geom(box(x0, -6, x0 + 4, y_top), "outline", fill="tone")
        # foundation planting along the front, skipping doors, steps and the drive
        front = [r for lv in h.levels[:1] for r in lv.rooms
                 if r.kind not in ("garage", "entry") and abs(r.y - min(q.y for q in lv.rooms if abs(q.x - r.x) < 99)) < 99]
        hy = lot.house_y
        for r in front:
            if r.kind in ("living", "office", "bedroom", "dining", "family") and \
                    abs(r.y - min(q.y for q in h.levels[0].rooms if q.x < r.x + r.w and q.x + q.w > r.x)) < 1e-6:
                x = lot.house_x + r.x + 1.5
                while x < lot.house_x + r.x + r.w - 1.0:
                    shrub(cv, x, hy + r.y - 2.2, 1.4 + 0.35 * ((int(x) * 7) % 3))
                    x += 3.6
        cv.geom(foot, "cut", fill="footprint")
        cv.lines(hatch_lines(foot, 45, 2.0), "hatch")
        cv.geom(roof.exterior, "eave")
        cx, cy = foot.centroid.x, foot.centroid.y
        cv.text(cx, cy + 0.6, h.name.upper(), size=7, anchor="middle", font="title")
        cv.text(cx, cy - 2.6, f"{len(h.levels)}-STORY RESIDENCE", size=5.5, anchor="middle")
        # trees
        for tx, ty, r in ((8, D - 14, 9), (W - 12, D - 22, 7), (6, 10, 6), (W - 6, 12, 5)):
            if not foot.buffer(2).intersects(box(tx - r, ty - r, tx + r, ty + r)):
                cv.circle(tx, ty, r, "thin")
                cv.circle(tx, ty, 0.6, "thin", fill="ink")
        # setback dimensions
        dim(cv, (lot.house_x + 4, 0), (lot.house_x + 4, lot.house_y), 3)
        dim(cv, (0, fy1 + 10), (fx0, fy1 + 10), 1.5)
        dim(cv, (fx1, fy1 + 10), (W, fy1 + 10), 1.5)
        dim(cv, (W / 2, fy1), (W / 2, D), 3)
        dim(cv, (0, D), (W, D), 3)
        dim(cv, (W, D), (W, 0), 5)
