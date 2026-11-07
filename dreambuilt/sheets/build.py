"""Assemble the concept set: cover, notes, site, plans, roof, elevations, schedules."""
from __future__ import annotations

import datetime as dt

from .. import checks, schedules, styles
from ..model import House
from ..render.backends import text_width
from ..render.canvas import Canvas, Sheet
from ..render.themes import Theme
from ..views.common import fmt_area, fmt_ft, north_arrow, scale_bar
from ..views.elevation_view import ElevationView
from ..views.plan import EXT_T, PlanView, draw_fixture
from ..views.roofplan import RoofPlanView
from ..views.scene import build_scene
from ..views.site import SitePlanView
from .layout import FRAME, SCALES, cap, draw_frame, fit_scale, place, view_title

TITLE_H = 0.6  # space under a view for its title
TITLE_W = 3.2  # space beside a view when the title goes to the side


def style_line(house: House) -> str:
    st = styles.get(house.style)
    return f"{st['name']} ({st['era']}) - {house.stories}-story"


class SetBuilder:
    def __init__(self, house: House, theme: Theme, date: str | None = None,
                 max_scale: float = 0.25, mode: str = "rough"):
        if mode not in ("rough", "full"):
            raise ValueError("mode is 'rough' or 'full'")
        self.mode = mode
        self.h = house
        self.t = theme
        self.date = date or dt.date.today().isoformat()
        self.max_scale = max_scale
        self.faces, self.roof = build_scene(house)
        self.style = styles.get(house.style)
        self.findings = checks.run(house)
        self.wtypes, self.wmarks = schedules.window_types(house)
        self.sheets: list[Sheet] = []

    # -- helpers ----------------------------------------------------------
    def new_sheet(self, number: str, title: str) -> tuple[Sheet, Canvas]:
        sh = Sheet(number, title)
        self.sheets.append(sh)
        return sh, Canvas(sh)

    def frame(self, cv: Canvas, sh: Sheet) -> None:
        draw_frame(cv, self.t, sh, self.h.name, style_line(self.h), self.date)

    def single_view(self, number: str, title: str, view, draw, arrow=False, num="1",
                    max_scale=None) -> Sheet:
        """One view per sheet at the largest standard scale that fits; title below or beside."""
        sh, cv = self.new_sheet(number, title)
        a = FRAME.area
        below = (a[0], a[1] + TITLE_H, a[2], a[3])
        beside = (a[0], a[1], a[2] - TITLE_W, a[3])
        cap_ = max_scale or self.max_scale
        kb, lb = fit_scale(view.bounds, (below[2] - below[0], below[3] - below[1]), cap_)
        ks, ls = fit_scale(view.bounds, (beside[2] - beside[0], beside[3] - beside[1]), cap_)
        side = ks > kb
        k, label = (ks, ls) if side else (kb, lb)
        sh.scale_note = label
        self.frame(cv, sh)
        bb = place(cv, view.bounds, beside if side else below, k)
        draw(cv)
        if side:
            tx, ty = bb[2] + 0.3, a[1] + 0.9
        else:
            tx, ty = bb[0], a[1] + 0.35
        view_title(cv, self.t, tx, ty, view.title, label, num)
        if arrow:
            north_arrow(cv, a[2] - 0.6, a[3] - 0.7)
        if k >= 0.09:
            scale_bar(cv, tx + 0.44, ty - 0.55 if not side else ty - 0.5, k)
        return sh

    # -- sheets -----------------------------------------------------------
    def index(self) -> list[tuple[str, str]]:
        """Sheet numbers and names, in order. Rough: brief, site, plans, roof, elevations."""
        names = [("A0.0", "Cover & brief")]
        if self.mode == "full":
            names.append(("A0.1", "Legend & notes"))
        names.append(("A1.1", "Site plan"))
        if self.h.basement:
            names.append(("A2.0", "Basement plan"))
        names += [(f"A2.{i}", f"{lv.name} plan") for i, lv in enumerate(self.h.levels, 1)]
        names += [("A3.1", "Roof plan"), ("A4.1", "South elevation"), ("A4.2", "North elevation"),
                  ("A4.3", "East elevation"), ("A4.4", "West elevation")]
        if self.mode == "full":
            names.append(("A5.1", "Schedules"))
        return names

    def build(self) -> list[Sheet]:
        self.cover()
        if self.mode == "full":
            self.notes()
        self.site()
        plans = ([(0, self.h.basement)] if self.h.basement else []) + list(enumerate(self.h.levels, start=1))
        for i, lv in plans:
            v = PlanView(self.h, lv)
            self.single_view(f"A2.{i}", f"{lv.name} Plan", v,
                             lambda cv, v=v: v.draw(cv, self.t, self.wmarks), arrow=True)
        rv = RoofPlanView(self.h)
        self.single_view("A3.1", "Roof Plan", rv, lambda cv: rv.draw(cv, self.t), arrow=True)
        for i, face in enumerate("SNEW", start=1):
            ev = ElevationView(self.h, self.faces, face)
            self.single_view(f"A4.{i}", ev.title.split(" (")[0], ev,
                             lambda cv, ev=ev: ev.draw(cv, self.t))
        if self.mode == "full":
            self.schedule_sheet()
        return self.sheets

    def cover(self) -> None:
        h, t, st = self.h, self.t, self.style
        sh, cv = self.new_sheet("A0.0", "Cover")
        sh.scale_note = "Not to scale"
        self.frame(cv, sh)
        a = FRAME.area
        cv.reset()
        pb = t.name == "patternbook"
        cx = (a[0] + a[2]) / 2
        top = a[3] - 0.35
        if pb:
            book = st.get("pattern_book", {})
            cv.text(cx, top, cap(t, book.get("catalog", "Home Designs")), size=11, anchor="middle",
                    font="italic", spacing=3)
            cv.text(cx, top - 0.75, f"DESIGN No. {int(round(h.heated_area))}", size=32,
                    anchor="middle", font="title", spacing=4)
            cv.line((cx - 3, top - 0.95), (cx + 3, top - 0.95), "heavy")
            cv.text(cx, top - 1.35, cap(t, h.name), size=18, anchor="middle", font="title",
                    spacing=t.title_spacing)
            cv.text(cx, top - 1.7, f"“{book.get('tagline', '')}”", size=11,
                    anchor="middle", font="italic")
            elev_box = (a[0] + 1.5, a[1] + 1.6, a[2] - 1.5, top - 2.0)
        else:
            cv.text(a[0] + 0.2, top - 0.35, cap(t, h.name), size=34, font="title",
                    spacing=t.title_spacing)
            cv.text(a[0] + 0.22, top - 0.75, cap(t, style_line(h)), size=12, font="italic")
            cv.line((a[0] + 0.2, top - 0.95), (a[0] + 6.5, top - 0.95), "heavy")
            elev_box = (a[0] + 5.6, a[1] + 1.4, a[2] - 0.2, top - 1.2)
        ev = ElevationView(h, self.faces, "S")
        bx = ev.extent[0] - 1, -0.5, ev.extent[2] + 1, ev.extent[3] + 0.5
        k = min((elev_box[2] - elev_box[0]) / (bx[2] - bx[0]),
                (elev_box[3] - elev_box[1]) / (bx[3] - bx[1]))
        place(cv, bx, elev_box, k)
        ev.draw(cv, t, markers=False)
        cv.reset()
        stats = [("Heated area", fmt_area(h.heated_area)), ("Bedrooms", str(len(h.bedrooms))),
                 ("Bathrooms", f"{h.baths:g}"), ("Stories", str(h.stories)),
                 ("Footprint", f"{fmt_ft(h.levels[0].footprint.bounds[2] - h.levels[0].footprint.bounds[0])}"
                               f" x {fmt_ft(h.levels[0].footprint.bounds[3] - h.levels[0].footprint.bounds[1])}"),
                 ("Lot", h.brief.lot if h.brief and h.brief.lot else "-")]
        if pb:
            y = a[1] + 1.05
            line = "   ·   ".join(f"{v} {k.lower()}" if k in ("Bedrooms", "Bathrooms") else v
                                       for k, v in stats[:4])
            cv.text(cx, y, cap(t, line), size=10, anchor="middle", spacing=1)
            cv.text(cx, y - 0.3, cap(t, st["summary"]), size=7.5, anchor="middle", font="italic")
            self._index(cv, a[2] - 2.6, a[1] + 0.95, small=True)
            return
        y = top - 1.45
        for k_, v in stats:
            cv.text(a[0] + 0.22, y, cap(t, k_), size=7, font="label")
            cv.text(a[0] + 1.9, y, v, size=10, font="title")
            y -= 0.33
        y -= 0.2
        cv.text(a[0] + 0.22, y, cap(t, "Character"), size=7, font="label")
        y = self._wrap(cv, a[0] + 0.22, y - 0.22, st["summary"], 4.9, 8)
        if h.brief and h.brief.must_haves:
            y -= 0.15
            cv.text(a[0] + 0.22, y, cap(t, "Must-haves"), size=7, font="label")
            y = self._wrap(cv, a[0] + 0.22, y - 0.22, ", ".join(h.brief.must_haves), 4.9, 8)
        if self.mode == "rough":
            s = checks.summary(self.findings)
            y -= 0.15
            cv.text(a[0] + 0.22, y, cap(t, "Code pre-check"), size=7, font="label")
            y = self._wrap(cv, a[0] + 0.22, y - 0.22,
                           f"{s['pass']} pass, {s['warn']} warn, {s['fail']} fail (informal, "
                           "after the 2021 IRC; run dreambuilt check for detail).", 4.9, 8)
        self._index(cv, a[0] + 0.22, min(y - 0.3, a[1] + 2.9))

    def _index(self, cv, x, y, small=False) -> None:
        t = self.t
        cv.text(x, y, cap(t, "Sheet index"), size=7, font="label")
        y -= 0.22
        names = self.index()
        col = 0
        y0 = y
        for i, (n, s) in enumerate(names):
            if small and i == (len(names) + 1) // 2:
                col, y = 1.3, y0
            cv.text(x + col, y, n, size=7, font="title")
            cv.text(x + col + 0.42, y, s, size=7)
            y -= 0.17

    def _wrap(self, cv, x, y, text, width_in, size) -> float:
        words, line = text.split(), ""
        font = self.t.fonts["body"]
        for w in words:
            trial = f"{line} {w}".strip()
            if text_width(trial, font, size) > width_in and line:
                cv.text(x, y, line, size=size)
                y -= size / 72 * 1.35
                line = w
            else:
                line = trial
        if line:
            cv.text(x, y, line, size=size)
            y -= size / 72 * 1.35
        return y

    def notes(self) -> None:
        t = self.t
        sh, cv = self.new_sheet("A0.1", "Legend & Notes")
        sh.scale_note = "Not to scale"
        self.frame(cv, sh)
        a = FRAME.area
        cv.reset()
        cols = [a[0] + 0.2, a[0] + 5.3, a[0] + 10.4]
        top = a[3] - 0.3
        # symbols
        cv.text(cols[0], top, cap(t, "Legend"), size=12, font="title", spacing=t.title_spacing)
        y = top - 0.55
        x = cols[0]

        def row(label):
            nonlocal y
            cv.reset()
            cv.text(x + 1.5, y - 0.04, label, size=7.5)
            y -= 0.48

        k = 0.25
        cv.set_transform(k, x, y)
        if t.wall_fill == "solid":
            cv.rect(0, -0.25, 5, 0.25, "cut", fill="poche")
        else:
            cv.rect(0, -0.25, 5, 0.25, "cut")
        row("Exterior wall, 2x6 framed (cut)")
        cv.set_transform(k, x, y)
        cv.rect(0, -0.19, 5, 0.19, "cut", fill="poche" if t.wall_fill == "solid" else None)
        row("Interior partition, 2x4 framed")
        cv.set_transform(k, x, y)
        cv.rect(0, -0.25, 1, 0.25, "cut", fill="poche" if t.wall_fill == "solid" else None)
        cv.rect(4, -0.25, 5, 0.25, "cut", fill="poche" if t.wall_fill == "solid" else None)
        for d in (-0.25, 0.25):
            cv.line((1, d), (4, d), "thin")
        cv.line((1, 0.06), (4, 0.06), "glass")
        cv.line((1, -0.06), (4, -0.06), "glass")
        row("Window in wall, with type tag")
        cv.set_transform(k, x, y - 0.15)
        cv.line((1, 0), (1, 3), "outline")
        cv.arc(1, 0, 3, 0, 90, "thin")
        cv.rect(0, -0.19, 1, 0.19, "cut", fill="poche" if t.wall_fill == "solid" else None)
        cv.rect(4, -0.19, 5, 0.19, "cut", fill="poche" if t.wall_fill == "solid" else None)
        y -= 0.3
        row("Door and swing")
        cv.set_transform(k, x, y)
        cv.line((0, 0), (5, 0), "eave")
        row("Roof eave above")
        cv.set_transform(k, x, y)
        cv.line((0, 0), (5, 0), "hidden")
        row("Hidden / overhead / shelf & rod")
        cv.set_transform(k, x, y)
        from ..views.common import dim
        dim(cv, (0, -0.4), (5, -0.4), 0.0, "5'-0\"")
        row("Dimension (outside face of framing)")
        cv.set_transform(k, x, y)
        from ..views.common import tag
        tag(cv, 2.5, 0, "A")
        row("Window type (see schedule)")
        cv.set_transform(k, x, y)
        draw_fixture(cv, __import__("dreambuilt.model", fromlist=["Fixture"]).Fixture(
            "tub", 0, -1.2, 5, 2.5, "N"))
        y -= 0.25
        row("Plumbing fixtures (indicative)")
        # abbreviations
        cv.reset()
        cv.text(cols[1], top, cap(t, "Abbreviations"), size=12, font="title",
                spacing=t.title_spacing)
        abbr = [("FF", "Finished floor"), ("TOP", "Top of plate"), ("CLG", "Ceiling"),
                ("DH", "Double-hung"), ("CSMT", "Casement"), ("AWN", "Awning"), ("FX", "Fixed"),
                ("REF", "Refrigerator"), ("W / D", "Washer / dryer"), ("R", "Riser"),
                ("TYP", "Typical"), ("NTS", "Not to scale")]
        y = top - 0.45
        for ab, full in abbr:
            cv.text(cols[1], y, ab, size=7.5, font="title")
            cv.text(cols[1] + 0.7, y, full, size=7.5)
            y -= 0.2
        y -= 0.3
        cv.text(cols[1], y, cap(t, "General notes"), size=12, font="title", spacing=t.title_spacing)
        y -= 0.4
        notes = [
            "Concept set for discussion with an architect. Not for permit or construction.",
            "Dimensions are to outside face of exterior framing and centreline of interior partitions.",
            f"Exterior walls drawn {fmt_ft(EXT_T)} thick; interior partitions 4-1/2\".",
            "Window and door sizes are nominal and indicative; verify rough openings.",
            "Roof framing, structure, energy and mechanical design by others.",
        ] + list(self.h.notes)
        for i, n in enumerate(notes, 1):
            cv.text(cols[1], y, f"{i}.", size=7.5, font="title")
            y = self._wrap(cv, cols[1] + 0.25, y, n, 4.3, 7.5) - 0.05
        # code pre-check
        cv.text(cols[2], top, cap(t, "Code pre-check"), size=12, font="title",
                spacing=t.title_spacing)
        s = checks.summary(self.findings)
        y = top - 0.4
        cv.text(cols[2], y, f"{s['pass']} pass   {s['warn']} warn   {s['fail']} fail", size=8,
                font="title")
        y -= 0.18
        y = self._wrap(cv, cols[2], y, "Informal screen loosely after the 2021 IRC. Not a code "
                       "review; zoning, structure and energy not covered.", 4.6, 6.5) - 0.1
        mark = {"pass": "OK", "warn": "!", "fail": "X"}
        for f in sorted(self.findings, key=lambda f: ("fail", "warn", "pass").index(f.status)):
            if y < a[1] + 0.25:
                cv.text(cols[2], y, "... see dreambuilt check for the full list", size=6.5,
                        font="italic")
                break
            role = "accent" if f.status != "pass" else "text"
            cv.text(cols[2], y, mark[f.status], size=7, font="title", role=role)
            cv.text(cols[2] + 0.3, y, f"{f.rule} - {f.where}", size=6.8, font="title")
            cv.text(cols[2] + 0.3, y - 0.14, f.detail, size=6.3)
            y -= 0.34

    def site(self) -> None:
        sv = SitePlanView(self.h)
        sh = self.single_view("A1.1", "Site Plan", sv, lambda cv: sv.draw(cv, self.t), arrow=True,
                              max_scale=0.05)
        cv = Canvas(sh)
        a = FRAME.area
        y = a[3] - 1.6
        for k, v in sv.stats():
            cv.text(a[2] - 3.0, y, cap(self.t, k), size=6.5, font="label")
            cv.text(a[2] - 3.0, y - 0.16, v, size=7.5)
            y -= 0.42

    def schedule_sheet(self) -> None:
        t = self.t
        sh, cv = self.new_sheet("A5.1", "Schedules")
        sh.scale_note = "Not to scale"
        self.frame(cv, sh)
        a = FRAME.area
        cv.reset()
        top = a[3] - 0.3
        self._table(cv, a[0] + 0.2, top, "Room schedule",
                    ["Room", "Level", "Size", "Sq ft", "Ceiling"], [1.5, 1.0, 1.25, 0.6, 0.6],
                    schedules.room_rows(self.h))
        self._table(cv, a[0] + 5.6, top, "Window schedule",
                    ["Type", "Qty", "Size (W x H)", "Op.", "Grille", "Sill"],
                    [0.45, 0.4, 1.3, 0.55, 0.95, 0.6], schedules.window_rows(self.h))
        y = self._table(cv, a[0] + 5.6, top - 0.45 - 0.22 * (len(self.wtypes) + 2) - 0.4,
                        "Door schedule", ["No.", "Size", "Type", "Location"],
                        [0.45, 1.1, 1.15, 2.0], schedules.door_rows(self.h))
        # area summary
        x = a[0] + 0.2
        y = top - 0.45 - 0.2 * (len(schedules.room_rows(self.h)) + 2) - 0.4
        cv.text(x, y, cap(t, "Area summary"), size=11, font="title", spacing=t.title_spacing)
        y -= 0.3
        rows = [(lv.name, fmt_area(lv.area)) for lv in self.h.levels]
        rows.append(("Total heated", fmt_area(self.h.heated_area)))
        rows += [("Porch", fmt_area(p.w * p.h)) for p in self.h.porches]
        from ..roof.analytic import roof_area
        rows.append(("Roof surface (approx.)", fmt_area(roof_area(self.roof))))
        for k_, v in rows:
            cv.text(x, y, k_, size=7.5)
            cv.text(x + 2.6, y, v, size=7.5, anchor="end", font="title")
            y -= 0.2

    def _table(self, cv, x, y, title, header, widths, rows) -> float:
        t = self.t
        cv.text(x, y, cap(t, title), size=11, font="title", spacing=t.title_spacing)
        y -= 0.3
        total = sum(widths)
        rh = 0.2
        cv.line((x, y + 0.04), (x + total, y + 0.04), "heavy")
        cx = x
        for hdr, w in zip(header, widths):
            cv.text(cx + 0.05, y - 0.12, cap(t, hdr), size=6.5, font="title")
            cx += w
        y -= rh
        cv.line((x, y + 0.02), (x + total, y + 0.02), "rule")
        for r in rows:
            cx = x
            for val, w in zip(r, widths):
                cv.text(cx + 0.05, y - 0.13, val, size=7)
                cx += w
            y -= rh
            cv.line((x, y + 0.02), (x + total, y + 0.02), "hatch")
        cv.line((x, y + 0.02), (x + total, y + 0.02), "rule")
        return y


def build_set(house: House, theme: Theme, date: str | None = None,
              mode: str = "rough") -> list[Sheet]:
    return SetBuilder(house, theme, date, mode=mode).build()


__all__ = ["SCALES", "SetBuilder", "build_set"]
