"""Backend-neutral drawing: primitives in sheet inches (origin bottom-left).

Views draw in model feet through a transform; SVG and PDF backends replay
the same item list, so both outputs always match.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import LineString, Polygon

from ..geometry import lines_of, polygons_of, rings_of


@dataclass
class Path:
    rings: list[list[tuple[float, float]]]
    role: str
    closed: bool = False
    fill: Optional[str] = None  # fill role; None = no fill
    stroke: bool = True


@dataclass
class Text:
    x: float
    y: float
    text: str
    role: str = "text"
    size: float = 8.0  # points
    anchor: str = "start"  # start | middle | end
    font: str = "body"  # title | body | label | italic
    rotate: float = 0.0
    spacing: float = 0.0


@dataclass
class Circle:
    x: float
    y: float
    r: float
    role: str
    fill: Optional[str] = None


@dataclass
class Arc:
    x: float
    y: float
    r: float
    a0: float  # degrees, counter-clockwise from +x
    a1: float
    role: str


@dataclass
class Sheet:
    number: str
    title: str
    width: float = 17.0
    height: float = 11.0
    items: list = field(default_factory=list)
    scale_note: str = ""


class Canvas:
    """Collects primitives onto a sheet through a model->sheet transform."""

    def __init__(self, sheet: Sheet):
        self.sheet = sheet
        self.k = 1.0  # sheet inches per model unit
        self.ox = 0.0
        self.oy = 0.0

    # transform -----------------------------------------------------------
    def set_transform(self, k: float, ox: float, oy: float) -> None:
        self.k, self.ox, self.oy = k, ox, oy

    def reset(self) -> None:
        self.set_transform(1.0, 0.0, 0.0)

    def T(self, x: float, y: float) -> tuple[float, float]:
        return (self.ox + x * self.k, self.oy + y * self.k)

    def _ring(self, pts):
        return [self.T(x, y) for x, y in pts]

    # primitives ----------------------------------------------------------
    def line(self, a, b, role="outline"):
        self.sheet.items.append(Path([self._ring([a, b])], role))

    def polyline(self, pts, role="outline", closed=False, fill=None, stroke=True):
        pts = list(pts)
        if len(pts) < 2:
            return
        self.sheet.items.append(Path([self._ring(pts)], role, closed, fill, stroke))

    def rect(self, x0, y0, x1, y1, role="outline", fill=None, stroke=True):
        self.polyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], role, True, fill, stroke)

    def geom(self, g, role="outline", fill=None, stroke=True):
        """Draw any shapely geometry: polygons (with holes) or lines."""
        for poly in polygons_of(g):
            rings = [self._ring(r) for r in rings_of(poly)]
            self.sheet.items.append(Path(rings, role, True, fill, stroke))
        for ln in lines_of(g):
            self.sheet.items.append(Path([self._ring(ln.coords)], role))

    def lines(self, lines: list[LineString], role="outline"):
        for ln in lines:
            self.sheet.items.append(Path([self._ring(ln.coords)], role))

    def text(self, x, y, s, role="text", size=8.0, anchor="start", font="body", rotate=0.0,
             spacing=0.0):
        X, Y = self.T(x, y)
        self.sheet.items.append(Text(X, Y, s, role, size, anchor, font, rotate, spacing))

    def circle(self, x, y, r, role="outline", fill=None):
        X, Y = self.T(x, y)
        self.sheet.items.append(Circle(X, Y, r * self.k, role, fill))

    def arc(self, x, y, r, a0, a1, role="thin"):
        X, Y = self.T(x, y)
        self.sheet.items.append(Arc(X, Y, r * self.k, a0, a1, role))


def arc_points(cx, cy, r, a0, a1, n=24):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


__all__ = ["Arc", "Canvas", "Circle", "Path", "Sheet", "Text", "arc_points", "Polygon"]
