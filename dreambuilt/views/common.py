"""Shared drafting conventions: feet-inch text, dimensions, arrows, tags."""
from __future__ import annotations

import math

from ..render.canvas import Canvas, arc_points


def fmt_ft(v: float) -> str:
    """12.5 -> 12'-6\" (rounded to the nearest inch)."""
    inches = int(round(abs(v) * 12))
    sign = "-" if v < 0 else ""
    return f"{sign}{inches // 12}'-{inches % 12}\""


def fmt_size(w: float, h: float) -> str:
    return f"{fmt_ft(w)} x {fmt_ft(h)}"


def fmt_area(a: float) -> str:
    return f"{a:,.0f} sq ft"


def dim(cv: Canvas, p1, p2, off: float, text: str | None = None, size: float = 6.0):
    """Linear dimension between p1 and p2, offset (model units) to the left of p1->p2."""
    (x1, y1), (x2, y2) = p1, p2
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-6:
        return
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    gap = 0.08 / cv.k
    ext = 0.08 / cv.k
    a = (x1 + nx * off, y1 + ny * off)
    b = (x2 + nx * off, y2 + ny * off)
    sgn = 1 if off >= 0 else -1
    for (px, py), (qx, qy) in (((x1, y1), a), ((x2, y2), b)):
        cv.line((px + nx * gap * sgn, py + ny * gap * sgn),
                (qx + nx * ext * sgn, qy + ny * ext * sgn), "dim")
    over = 0.06 / cv.k
    cv.line((a[0] - ux * over, a[1] - uy * over), (b[0] + ux * over, b[1] + uy * over), "dim")
    t = 0.05 / cv.k
    for px, py in (a, b):  # architectural slash ticks
        cv.line((px - (ux + nx) * t, py - (uy + ny) * t), (px + (ux + nx) * t, py + (uy + ny) * t),
                "cut")
    ang = math.degrees(math.atan2(uy, ux))
    if ang > 90.01 or ang < -89.99:
        ang += 180
    lift = 0.045 / cv.k
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    # lift text off the line, away from the object when the offset is negative
    rad = math.radians(ang)
    lx, ly = -math.sin(rad), math.cos(rad)
    cv.text(mx + lx * lift, my + ly * lift, text or fmt_ft(L), size=size, anchor="middle",
            rotate=ang)


def north_arrow(cv: Canvas, x: float, y: float, r: float = 0.32):
    """North arrow at sheet position (x, y) in inches; resets the transform."""
    cv.reset()
    cv.circle(x, y, r, "thin")
    cv.polyline([(x, y + r * 1.05), (x + r * 0.38, y - r * 0.7), (x, y - r * 0.35)], "thin",
                closed=True, fill="ink")
    cv.polyline([(x, y + r * 1.05), (x - r * 0.38, y - r * 0.7), (x, y - r * 0.35)], "thin",
                closed=True)
    cv.text(x, y + r * 1.25, "N", size=9, anchor="middle", font="title")


def scale_bar(cv: Canvas, x: float, y: float, k: float, feet=(0, 4, 8, 16)):
    cv.reset()
    h = 0.06
    for i, (a, b) in enumerate(zip(feet, feet[1:])):
        cv.rect(x + a * k, y, x + b * k, y + h, "thin", fill="ink" if i % 2 == 0 else None)
    for f in feet:
        cv.text(x + f * k, y + h + 0.05, f"{f}'", size=5.5, anchor="middle")


def tag(cv: Canvas, x: float, y: float, label: str, kind: str = "hex", r_in: float = 0.085):
    """Small symbol tag (window type, door number) at model point (x, y)."""
    r = r_in / cv.k
    if kind == "hex":
        pts = [(x + r * math.cos(math.radians(30 + 60 * i)), y + r * math.sin(math.radians(30 + 60 * i)))
               for i in range(6)]
        cv.polyline(pts, "thin", closed=True, fill="paper")
    else:
        cv.circle(x, y, r, "thin", fill="paper")
    cv.text(x, y - r * 0.42, label, size=5.5, anchor="middle", font="title")


def arrow(cv: Canvas, a, b, role="thin", head_in=0.07):
    (x1, y1), (x2, y2) = a, b
    cv.line(a, b, role)
    L = math.hypot(x2 - x1, y2 - y1)
    if L == 0:
        return
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    h = head_in / cv.k
    cv.polyline([(x2, y2), (x2 - ux * h - uy * h * 0.45, y2 - uy * h + ux * h * 0.45),
                 (x2 - ux * h + uy * h * 0.45, y2 - uy * h - ux * h * 0.45)], role, closed=True,
                fill="ink")


def ellipse(cx, cy, rx, ry, n=28):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
            for i in range(n)]


__all__ = ["arc_points", "arrow", "dim", "ellipse", "fmt_area", "fmt_ft", "fmt_size",
           "north_arrow", "scale_bar", "tag"]
