"""Sheet frame, title block and view placement on 11x17 sheets."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..render.backends import text_width
from ..render.canvas import Canvas, Sheet
from ..render.themes import Theme

# preferred architectural scales, inches per foot, largest first
SCALES = [(0.25, '1/4" = 1\'-0"'), (0.1875, '3/16" = 1\'-0"'), (0.125, '1/8" = 1\'-0"'),
          (0.09375, '3/32" = 1\'-0"'), (0.0625, '1/16" = 1\'-0"'), (0.05, '1" = 20\'-0"'), (1 / 30, '1" = 30\'-0"'), (0.03125, '1/32" = 1\'-0"')]


@dataclass
class Frame:
    x0: float = 0.75
    y0: float = 0.4
    x1: float = 16.6
    y1: float = 10.6
    tb: float = 0.95  # title block height

    @property
    def area(self):
        """Drawing area (x0, y0, x1, y1) above the title block, inches."""
        return (self.x0 + 0.25, self.y0 + self.tb + 0.25, self.x1 - 0.25, self.y1 - 0.25)


FRAME = Frame()


def cap(theme: Theme, s: str) -> str:
    return s.upper() if theme.upper else s


def draw_frame(cv: Canvas, theme: Theme, sheet: Sheet, project: str, style_label: str,
               date: str | None = None) -> None:
    cv.reset()
    f = FRAME
    if theme.grid:
        x = f.x0
        while x <= f.x1:
            cv.line((x, f.y0), (x, f.y1), "grid")
            x += 0.25
        y = f.y0
        while y <= f.y1:
            cv.line((f.x0, y), (f.x1, y), "grid")
            y += 0.25
    cv.rect(f.x0, f.y0, f.x1, f.y1, "frame")
    if theme.border in ("double", "ornate"):
        d = 0.07
        cv.rect(f.x0 - d, f.y0 - d, f.x1 + d, f.y1 + d, "thin")
    if theme.border == "ornate":
        for cx, cy in ((f.x0, f.y0), (f.x1, f.y0), (f.x1, f.y1), (f.x0, f.y1)):
            s = 0.13
            cv.polyline([(cx - s, cy), (cx, cy + s), (cx + s, cy), (cx, cy - s)], "thin",
                        closed=True, fill="ink")
            cv.circle(cx, cy, 0.2, "thin")
    # title block band
    tb = f.y0 + f.tb
    cv.line((f.x0, tb), (f.x1, tb), "frame")
    cells = [f.x0, f.x0 + 5.2, f.x0 + 9.4, f.x0 + 11.6, f.x0 + 13.9, f.x1]
    for x in cells[1:-1]:
        cv.line((x, f.y0), (x, tb), "rule")
    ty = f.y0 + f.tb - 0.27
    title_font = "title"
    cv.text(cells[0] + 0.15, ty, cap(theme, project), size=14, font=title_font,
            spacing=theme.title_spacing)
    cv.text(cells[0] + 0.15, ty - 0.24, cap(theme, style_label), size=7.5, font="italic")
    cv.text(cells[0] + 0.15, f.y0 + 0.1, cap(theme, "Concept set - not for construction"),
            size=6.5, font="title", role="accent")
    label = lambda x, s: cv.text(x + 0.12, tb - 0.17, cap(theme, s), size=5.5)
    label(cells[1], "Sheet title")
    cv.text(cells[1] + 0.12, f.y0 + 0.32, cap(theme, sheet.title), size=11, font="title",
            spacing=theme.title_spacing * 0.5)
    label(cells[2], "Scale")
    cv.text(cells[2] + 0.12, f.y0 + 0.32, sheet.scale_note or "As noted", size=8.5)
    label(cells[3], "Date / drawn by")
    cv.text(cells[3] + 0.12, f.y0 + 0.42, date or dt.date.today().isoformat(), size=8.5)
    cv.text(cells[3] + 0.12, f.y0 + 0.2, "Dream Built", size=7.5, font="italic")
    label(cells[4], "Sheet")
    cv.text((cells[4] + cells[5]) / 2, f.y0 + 0.22, sheet.number, size=22, font="title",
            anchor="middle")


def fit_scale(bounds, box_in, prefer_max: float = 0.25) -> tuple[float, str]:
    """Largest standard scale at which model `bounds` fit inside `box_in` (w, h inches)."""
    w = bounds[2] - bounds[0]
    h = bounds[3] - bounds[1]
    for k, label in SCALES:
        if k > prefer_max + 1e-9:
            continue
        if w * k <= box_in[0] and h * k <= box_in[1]:
            return k, label
    return SCALES[-1]


def place(cv: Canvas, bounds, region, k: float, align: str = "center"):
    """Set the transform so model `bounds` sit centred in sheet `region` at scale k."""
    x0, y0, x1, y1 = region
    w = (bounds[2] - bounds[0]) * k
    h = (bounds[3] - bounds[1]) * k
    ox = x0 + (x1 - x0 - w) / 2 - bounds[0] * k
    oy = y0 + (y1 - y0 - h) / 2 - bounds[1] * k
    if align == "top":
        oy = y1 - h - bounds[1] * k
    cv.set_transform(k, ox, oy)
    return (ox + bounds[0] * k, oy + bounds[1] * k, ox + bounds[2] * k, oy + bounds[3] * k)


def view_title(cv: Canvas, theme: Theme, x: float, y: float, title: str, scale: str,
               number: str = "1") -> None:
    """Architectural view title at sheet (x, y): bubble, title, rule, scale."""
    cv.reset()
    r = 0.17
    cv.circle(x + r, y, r, "outline")
    cv.text(x + r, y - 0.05, number, size=9, anchor="middle", font="title")
    t = cap(theme, title)
    tw = text_width(t, theme.fonts["title"], 11, theme.title_spacing)
    cv.text(x + 2 * r + 0.1, y + 0.02, t, size=11, font="title", spacing=theme.title_spacing)
    cv.line((x + 2 * r + 0.1, y - 0.06), (x + 2 * r + 0.1 + max(tw, 1.6), y - 0.06), "heavy")
    if scale:
        cv.text(x + 2 * r + 0.1, y - 0.22, f"SCALE: {scale}", size=6.5)
