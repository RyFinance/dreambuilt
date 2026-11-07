"""Concept view: the exterior large on the left, an interactive floor plan on the right."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from .. import checks
from ..views.common import fmt_ft
from . import style as S
from . import worker
from .render_views import elevation_image, plan_image
from .widgets import animate

FACES = [("S", "Front"), ("N", "Rear"), ("W", "Left"), ("E", "Right")]


class SvgPane(QWidget):
    """Draws a ViewImage fitted into the widget, with an optional fade."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.img = None
        self.renderer = None
        self.fade = 1.0

    def set_image(self, img):
        self.img = img
        self.renderer = QSvgRenderer(QByteArray(img.svg.encode()))
        animate(self, 0.0, 1.0, 320, lambda v: (setattr(self, "fade", v), self.update()))

    def target(self) -> QRectF:
        if not self.img:
            return QRectF()
        r = QRectF(self.rect())
        ar = self.img.width / self.img.height
        w = min(r.width(), r.height() * ar)
        h = w / ar
        return QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)

    def paintEvent(self, e):
        if not self.renderer:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.fade)
        self.renderer.render(p, self.target())
        self.paint_over(p)

    def paint_over(self, p):
        pass


class PlanPane(SvgPane):
    """Floor plan with room titles. Three ways to edit it:

    select  click rooms to pick them (their titles go to the edit bar)
    drag    grab an interior wall and slide it; the plan re-checks when you let go
    draw    sketch on it: a loop picks rooms, a stroke from one room into another swaps them,
            an X removes a room, a stroke along a wall moves the wall there
    """
    hovered = Signal(object)
    picked = Signal(list)          # selected room titles
    wall_moved = Signal(tuple)     # (axis, line, lo, hi, new line) in plan feet
    drawn = Signal(list)           # strokes, each a list of (x, y) plan feet

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = None
        self.hot = None
        self.mode = "select"
        self.selected: list[str] = []
        self.strokes: list[list[QPointF]] = []
        self._drag = None          # (wall, start px)
        self._drag_to = None
        self._walls = []
        self.setMouseTracking(True)

    def set_level(self, level, img, walls=()):
        self.level = level
        self.hot = None
        self.selected = []
        self.strokes = []
        self._walls = list(walls)
        self.set_image(img)

    def _room_rect(self, r) -> QRectF:
        t = self.target()
        x0, y1 = self.img.to_px(r.x, r.y, t.x(), t.y(), t.width(), t.height())
        x1, y0 = self.img.to_px(r.x + r.w, r.y + r.h, t.x(), t.y(), t.width(), t.height())
        return QRectF(QPointF(x0, y0), QPointF(x1, y1))

    def to_ft(self, pt: QPointF) -> tuple[float, float]:
        """Widget pixels -> plan feet (the inverse of ViewImage.to_px)."""
        t = self.target()
        sx = (pt.x() - t.x()) / t.width()
        sy = (pt.y() - t.y()) / t.height()
        return ((sx * self.img.width - self.img.ox) / self.img.k,
                ((1 - sy) * self.img.height - self.img.oy) / self.img.k)

    def _px(self, x: float, y: float) -> QPointF:
        t = self.target()
        return QPointF(*self.img.to_px(x, y, t.x(), t.y(), t.width(), t.height()))

    def _wall_near(self, pt: QPointF):
        x, y = self.to_ft(pt)
        best, best_d = None, 1.2  # within ~1.2 ft
        for w in self._walls:
            axis, line, lo, hi = w
            if axis == "y" and lo <= y <= hi:
                d = abs(x - line)
            elif axis == "x" and lo <= x <= hi:
                d = abs(y - line)
            else:
                continue
            if d < best_d:
                best, best_d = w, d
        return best

    def set_mode(self, mode: str):
        self.mode = mode
        self.strokes = []
        self._drag = None
        self.setCursor(Qt.CursorShape.CrossCursor if mode == "draw" else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, e):
        if not self.level or not self.img:
            return
        if self.mode == "draw":
            self.strokes.append([e.position()])
        elif self.mode == "drag":
            w = self._wall_near(e.position())
            if w:
                self._drag, self._drag_to = w, None
        else:
            hit = next((r for r in self.level.rooms if r.kind != "void" and self._room_rect(r).contains(e.position())), None)
            if hit is not None:
                t = hit.label
                if e.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier):
                    self.selected = [x for x in self.selected if x != t] if t in self.selected else self.selected + [t]
                else:
                    self.selected = [] if self.selected == [t] else [t]
                self.picked.emit(list(self.selected))
                self.update()

    def mouseMoveEvent(self, e):
        if not self.level or not self.img:
            return
        if self.mode == "draw" and self.strokes and e.buttons():
            self.strokes[-1].append(e.position())
            self.update()
            return
        if self.mode == "drag":
            if self._drag:
                x, y = self.to_ft(e.position())
                self._drag_to = round((x if self._drag[0] == "y" else y) * 2) / 2
            else:
                self.setCursor(Qt.CursorShape.SplitHCursor if (w := self._wall_near(e.position())) and w[0] == "y"
                               else Qt.CursorShape.SplitVCursor if w else Qt.CursorShape.ArrowCursor)
            self.update()
            return
        hit = None
        for r in self.level.rooms:
            if r.kind != "void" and self._room_rect(r).contains(e.position()):
                hit = r
        if hit is not self.hot:
            self.hot = hit
            self.hovered.emit(hit)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.mode == "drag" and self._drag:
            w, to = self._drag, self._drag_to
            self._drag, self._drag_to = None, None
            if to is not None and abs(to - w[1]) >= 0.5:
                self.wall_moved.emit((*w, to))
            self.update()

    def drawing_ft(self) -> list[list[tuple[float, float]]]:
        return [[self.to_ft(p) for p in s] for s in self.strokes if len(s) >= 2]

    def leaveEvent(self, e):
        self.hot = None
        self.hovered.emit(None)
        self.update()

    def paint_over(self, p):
        if not self.level:
            return
        p.setOpacity(1.0)
        for r in self.level.rooms:
            if r.label in self.selected:
                rr = self._room_rect(r)
                p.fillRect(rr.adjusted(2, 2, -2, -2), QColor(120, 170, 255, 60))
                p.setPen(QPen(QColor(150, 190, 255), 1.6))
                p.drawRect(rr.adjusted(2, 2, -2, -2))
        for r in self.level.rooms:
            if r.kind in ("void", "closet", "stair") or r.area < 30:
                continue
            rr = self._room_rect(r)
            if r is not self.hot and r.label not in self.selected and (rr.width() < 78 or rr.height() < 46 or r.kind == "hall"):
                continue  # too small to label; hover shows it
            if r is self.hot:
                p.fillRect(rr.adjusted(2, 2, -2, -2), QColor(241, 241, 239, 28))
            c = rr.center()
            p.setPen(QPen(S.WHITE, 1.2))
            p.setBrush(QColor(0, 0, 0) if r is not self.hot else S.WHITE)
            p.drawEllipse(c, 4.5, 4.5)
            p.setPen(QColor(241, 241, 239, 230 if r is self.hot else 170))
            p.setFont(S.mono(8.5, 0.6))
            p.drawText(QRectF(c.x() - 70, c.y() + 7, 140, 14), Qt.AlignmentFlag.AlignHCenter,
                       r.label.upper())
            if r is self.hot or rr.width() > 90:
                p.setPen(QColor(241, 241, 239, 110))
                p.drawText(QRectF(c.x() - 70, c.y() + 20, 140, 14), Qt.AlignmentFlag.AlignHCenter,
                           f"{r.area:,.0f} FT²")
        if self.mode == "drag":
            p.setPen(QPen(QColor(150, 190, 255, 140), 2.0))
            for axis, line, lo, hi in self._walls:
                a, b = ((line, lo), (line, hi)) if axis == "y" else ((lo, line), (hi, line))
                p.drawLine(self._px(*a), self._px(*b))
            if self._drag and self._drag_to is not None:
                axis, line, lo, hi = self._drag
                a, b = ((self._drag_to, lo), (self._drag_to, hi)) if axis == "y" else ((lo, self._drag_to), (hi, self._drag_to))
                p.setPen(QPen(QColor(255, 210, 120), 3.0))
                p.drawLine(self._px(*a), self._px(*b))
        if self.strokes:
            p.setPen(QPen(QColor(255, 120, 110), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for stroke in self.strokes:
                path = QPainterPath(stroke[0])
                for q in stroke[1:]:
                    path.lineTo(q)
                p.drawPath(path)


class ConceptView(QWidget):
    show_brief = Signal()
    edit_brief = Signal()
    show_set = Signal()
    refine = Signal(str, str, bool)
    edit_ops = Signal(object)      # [edit.Op] on the open option
    react = Signal(bool)           # like / pass on the open option
    breed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.opt = 0
        self.level_idx = 0
        self.face = "S"
        self.selected: list[str] = []
        self.optbtns = []
        self._faces_cache = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # top bar
        bar = QWidget()
        bar.setFixedHeight(58)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(28, 0, 28, 0)
        self.back = self._link("")
        self.back.hide()
        self.title = QLabel("")
        self.title.setStyleSheet("color:#f1f1ef; font-family:'Avenir Next Condensed'; font-size:22px; font-weight:600; letter-spacing:1px;")
        self.stats = QLabel("")
        self.stats.setStyleSheet("color: rgba(241,241,239,0.55); font-family: Menlo; font-size: 11px;")
        bl.addWidget(self.back)
        bl.addSpacing(22)
        bl.addWidget(self.title)
        bl.addSpacing(16)
        bl.addWidget(self.stats)
        bl.addStretch(1)
        self.optrow = QHBoxLayout()
        self.optrow.setSpacing(14)
        bl.addLayout(self.optrow)
        bl.addSpacing(28)
        self.editbtn = self._link("Edit brief")
        self.editbtn.clicked.connect(self.edit_brief.emit)
        bl.addWidget(self.editbtn)
        bl.addSpacing(18)
        self.setbtn = self._link("Drawing set  →")
        self.setbtn.clicked.connect(self.show_set.emit)
        bl.addWidget(self.setbtn)
        root.addWidget(bar)
        body = QHBoxLayout()
        body.setSpacing(0)
        # left: exterior
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(36, 18, 36, 26)
        self.kind = QLabel("")
        self.kind.setStyleSheet("color: rgba(241,241,239,0.5); font-family: Menlo; font-size: 11px; letter-spacing: 2px;")
        self.elev = SvgPane()
        faces = QHBoxLayout()
        faces.setSpacing(22)
        self.facebtns = {}
        for key, label in FACES:
            b = self._link(label.upper(), checkable=True)
            b.clicked.connect(lambda _c=False, k=key: self._face(k))
            faces.addWidget(b)
            self.facebtns[key] = b
        faces.addStretch(1)
        ll.addWidget(self.kind)
        ll.addWidget(self.elev, 1)
        ll.addLayout(faces)
        # right: floor panel
        right = QWidget()
        right.setFixedWidth(600)
        right.setObjectName("floor")
        right.setStyleSheet("#floor { background: #000; }")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(34, 26, 34, 22)
        top = QHBoxLayout()
        self.floor_name = QLabel("")
        self.floor_name.setStyleSheet("color:#f1f1ef; font-family:'Avenir Next Condensed'; font-size:46px; font-weight:600;")
        self.floor_area = QLabel("")
        self.floor_area.setStyleSheet("color:#f1f1ef; font-family:'Avenir Next Condensed'; font-size:46px; font-weight:500;")
        top.addWidget(self.floor_name)
        top.addStretch(1)
        top.addWidget(self.floor_area)
        sub = QHBoxLayout()
        self.floor_sub = QLabel("")
        self.floor_sub.setStyleSheet("color: rgba(241,241,239,0.55); font-family: 'Avenir Next'; font-size: 13px;")
        self.levelrow = QHBoxLayout()
        self.levelrow.setSpacing(16)
        sub.addWidget(self.floor_sub)
        sub.addStretch(1)
        sub.addLayout(self.levelrow)
        self.plan = PlanPane()
        self.plan.hovered.connect(self._hover)
        self.detail = QLabel(" ")
        self.detail.setStyleSheet("color:#f1f1ef; font-family: 'Avenir Next'; font-size: 14px;")
        self.checks = QLabel("")
        self.checks.setWordWrap(True)
        self.checks.setStyleSheet("color: rgba(241,241,239,0.55); font-family: Menlo; font-size: 10.5px;")
        tools = QHBoxLayout()
        tools.setSpacing(14)
        self.modebtns = {}
        for key, label in (("select", "Select"), ("drag", "Drag walls"), ("draw", "Draw")):
            b = self._link(label, checkable=True)
            b.clicked.connect(lambda _c=False, k=key: self._mode(k))
            tools.addWidget(b)
            self.modebtns[key] = b
        tools.addStretch(1)
        self.applydraw = self._link("Apply drawing")
        self.applydraw.clicked.connect(self._apply_drawing)
        self.cleardraw = self._link("Clear")
        self.cleardraw.clicked.connect(lambda: (self.plan.strokes.clear(), self.plan.update()))
        tools.addWidget(self.applydraw)
        tools.addWidget(self.cleardraw)
        self.selbar = QHBoxLayout()
        self.selbar.setSpacing(10)
        self.sel_label = QLabel("")
        self.sel_label.setStyleSheet("color:#9fc0ff; font-family: Menlo; font-size: 11px;")
        self.selbar.addWidget(self.sel_label)
        self.quick = {}
        for key, label in (("bigger", "Bigger"), ("smaller", "Smaller"), ("front", "To front"), ("back", "To back"),
                           ("remove", "Remove"), ("keep", "Keep"), ("swap", "Swap")):
            b = self._link(label)
            b.clicked.connect(lambda _c=False, k=key: self._quick(k))
            self.selbar.addWidget(b)
            self.quick[key] = b
        self.selbar.addStretch(1)
        self.plan.picked.connect(self._picked)
        self.plan.wall_moved.connect(self._wall_moved)
        rl.addLayout(top)
        rl.addLayout(sub)
        rl.addLayout(tools)
        rl.addWidget(self.plan, 1)
        rl.addLayout(self.selbar)
        rl.addWidget(self.detail)
        rl.addWidget(self.checks)
        body.addWidget(left, 1)
        body.addWidget(right)
        root.addLayout(body, 1)
        from .home_view import PromptBox
        bar = QHBoxLayout()
        bar.setContentsMargins(36, 10, 36, 18)
        self.ask = PromptBox("Ask for changes: \"make it 5 bed\", \"add a fireplace\", \"3,200 sq ft\"…", compact=True)
        self.ask.setMaximumWidth(860)
        self.ask.send.connect(lambda t, ph, ai: (self.refine.emit(t, ph, ai), self.ask.text.clear(),
                                                 self.ask.set_photo("")))
        bar.addStretch(1)
        bar.addWidget(self.ask, 4)
        bar.addStretch(1)
        root.addLayout(bar)

    def _link(self, text, checkable=False):
        b = QToolButton()
        b.setText(text)
        b.setCheckable(checkable)
        b.setStyleSheet(S.LINK)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    # -- data -------------------------------------------------------------------
    def load(self, data):
        self.data = data
        self.opt = 0
        self.level_idx = 0
        self.face = "S"
        self._faces_cache = {}
        while self.optrow.count():
            w = self.optrow.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.optbtns = []
        if len(data["options"]) > 1:
            lab = QLabel("OPTION")
            lab.setStyleSheet("color: rgba(241,241,239,0.4); font-family: Menlo; font-size: 10.5px; letter-spacing: 2px;")
            self.optrow.addWidget(lab)
            for i in range(len(data["options"])):
                b = self._link("ABCDEFGHIJ"[i], checkable=True)
                b.clicked.connect(lambda _c=False, i=i: self.set_option(i))
                self.optrow.addWidget(b)
                self.optbtns.append(b)
        for label, tip, fn in (("♥", "Like this one (Dream Built learns your taste)", lambda: self.react.emit(True)),
                               ("✕", "Pass on this one", lambda: self.react.emit(False)),
                               ("Breed", "Mix this option with another into new designs", self.breed.emit)):
            b = self._link(label)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            self.optrow.addWidget(b)
        self._mode("select")
        self._refresh()

    def house(self):
        return self.data["options"][self.opt].house

    def set_option(self, i):
        if self.data and 0 <= i < len(self.data["options"]):
            self.opt = i
            self.level_idx = min(self.level_idx, len(self.house().levels) - 1)
            self._refresh()

    def _refresh(self):
        h = self.house()
        for j, b in enumerate(self.optbtns):
            b.setChecked(j == self.opt)
        self.title.setText(h.name.upper())
        st = h.brief.style if h.brief else h.style
        self.stats.setText(f"{h.heated_area:,.0f} FT²   ·   {len(h.bedrooms)} BED   ·   {h.baths:g} BATH   ·   "
                           f"{h.stories} STOREY")
        lot = h.brief.lot if h.brief and h.brief.lot else ""
        self.kind.setText(f"{st.upper()}   {('·   LOT ' + lot.upper()) if lot else ''}")
        while self.levelrow.count():
            w = self.levelrow.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.levelbtns = []
        for i, lv in enumerate(h.all_levels):
            label = "B" if lv is h.basement else str(i + (0 if h.basement else 1))
            b = self._link(label, checkable=True)
            b.clicked.connect(lambda _c=False, i=i: self._level(i))
            self.levelrow.addWidget(b)
            self.levelbtns.append(b)
        found = checks.run(h)
        s = checks.summary(found)
        plan_ok = not any(f.status == "fail" and f.rule.startswith("P") for f in found)
        notes = [f"{f.rule.split(' ', 1)[1]} — {f.where}" for f in found if f.status == "warn"][:3]
        brief_line = ""
        b = self.data.get("brief")
        if b is not None:
            from ..design import missing
            lost = missing(h, b)
            brief_line = ("BRIEF ✓ everything asked for is drawn" if not lost else
                          "BRIEF · couldn't: " + ", ".join(lost[:4]))
            if getattr(b, "notes", None):
                brief_line += "   ·   not drawn yet: " + "; ".join(b.notes[:2])
            brief_line += "\n"
        self.checks.setText(brief_line + ("CIRCULATION ✓" if plan_ok else "CIRCULATION ✗") +
                            f"   CODE {s['fail']} FAIL · {s['warn']} NOTE" +
                            ("\n" + "   ·   ".join(notes) if notes else ""))
        self._face(self.face)
        self._level(self.level_idx)

    def _face(self, key):
        self.face = key
        for k, b in self.facebtns.items():
            b.setChecked(k == key)
        h = self.house()
        ck = (self.opt, key)
        if ck in self._faces_cache:
            self.elev.set_image(self._faces_cache[ck])
            return
        worker.run(lambda: elevation_image(h, key),
                   lambda img: (self._faces_cache.__setitem__(ck, img),
                                self.elev.set_image(img) if self.face == key else None))

    def _level(self, i):
        self.level_idx = i
        h = self.house()
        lv = h.all_levels[i]
        for j, b in enumerate(self.levelbtns):
            b.setChecked(j == i)
        self.floor_name.setText(lv.name.upper())
        self.floor_area.setText(f"{lv.heated_area:,.0f} FT²")
        beds = sum(r.kind == "bedroom" for r in lv.rooms)
        baths = sum(r.kind == "bath" for r in lv.rooms) + 0.5 * sum(r.kind == "powder" for r in lv.rooms)
        bits = [f"{len([r for r in lv.rooms if r.kind not in ('void', 'closet', 'hall')])} rooms"]
        if beds:
            bits.append(f"{beds} bedroom{'s' * (beds > 1)}")
        if baths:
            bits.append(f"{baths:g} bath")
        self.floor_sub.setText("  ·  ".join(bits))
        self.detail.setText(" ")
        from .. import edit
        self._picked([])
        worker.run(lambda: (plan_image(h, i), edit.walls(h, i)),
                   lambda res: self.plan.set_level(lv, res[0], res[1]) if self.level_idx == i else None)

    # -- editing --------------------------------------------------------------------
    def _mode(self, key):
        for k, b in self.modebtns.items():
            b.setChecked(k == key)
        self.plan.set_mode(key)
        self.applydraw.setVisible(key == "draw")
        self.cleardraw.setVisible(key == "draw")
        hints = {"select": "Click a room to pick it (shift-click for more), then a button or type what to change.",
                 "drag": "Grab a highlighted wall and slide it.",
                 "draw": "Loop: pick · room→room: swap · X: remove · along a wall: move it"}
        self.detail.setText(f"<span style='color:rgba(241,241,239,0.5)'>{hints[key]}</span>")

    def _picked(self, titles):
        self.selected = list(titles)
        self.sel_label.setText("  ·  ".join(t.upper() for t in titles) if titles else "")
        for k, b in self.quick.items():
            b.setVisible(bool(titles) and (k != "swap" or len(titles) == 2))
        if titles:
            self.ask.text.setPlainText(titles[0] + " ")

    def _quick(self, key):
        from .. import edit
        t = self.selected
        if not t:
            return
        ops = {"bigger": [edit.Op("resize", t[0], value=edit.GROW)],
               "smaller": [edit.Op("resize", t[0], value=edit.SHRINK)],
               "front": [edit.Op("move", t[0], side="front")], "back": [edit.Op("move", t[0], side="rear")],
               "remove": [edit.Op("remove", x) for x in t], "keep": [edit.Op("keep", x) for x in t],
               "swap": [edit.Op("swap", t[0], t[1])] if len(t) == 2 else []}[key]
        if ops:
            self.edit_ops.emit(ops)

    def _wall_moved(self, w):
        from .. import edit
        axis, line, lo, hi, to = w
        self.edit_ops.emit([edit.Op("wall", value=to, wall=(self.level_idx, axis, line, lo, hi))])

    def _apply_drawing(self):
        from .. import edit
        ops, selected = edit.strokes(self.house(), self.level_idx, self.plan.drawing_ft())
        self.plan.strokes = []
        self.plan.selected = selected
        self.plan.update()
        if selected and not ops:
            self._picked(selected)
            return
        if ops:
            self.edit_ops.emit(ops)
        else:
            self.detail.setText("<span style='color:rgba(241,241,239,0.5)'>Couldn't read that drawing. "
                                "Loop a room, draw room → room, an X, or a line along a wall.</span>")

    def _hover(self, r):
        if r is None:
            self.detail.setText(" ")
        else:
            self.detail.setText(f"{r.label}   <span style='color:rgba(241,241,239,0.55)'>"
                                f"{fmt_ft(r.w)} × {fmt_ft(r.h)}  ·  {r.area:,.0f} ft²</span>")

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), S.BG)
