"""Drafting table: the finished set. Sheets on the left, the big sheet in the middle,
house facts and the code pre-check on the right; style and option toggles on top."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QScrollArea, QToolButton, QVBoxLayout, QWidget)

from .. import checks
from ..model import save
from ..render import themes
from ..render.backends import sheet_to_svg
from ..sheets.build import build_set
from ..views.common import fmt_area, fmt_ft
from . import style as S
from . import worker
from .widgets import Segmented, animate

STYLE_OPTS = [("modern", "Modern lines"), ("blueprint", "Blueprint"), ("patternbook", "1920s book")]

BTN = S.LINK


SCROLL = """
    QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
    QScrollBar::handle:vertical { background: rgba(201,165,74,0.45); border-radius: 4px; min-height: 30px; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"""


class SheetView(QWidget):
    """One sheet, fitted to the view; scroll to zoom, drag to pan, double-click to fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer: QSvgRenderer | None = None
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self._drag = None
        self.fade = 1.0
        self.setMinimumSize(500, 360)

    def set_svg(self, svg: str):
        self.renderer = QSvgRenderer(QByteArray(svg.encode()))
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        animate(self, 0.25, 1.0, 260, lambda v: (setattr(self, "fade", v), self.update()))

    def wheelEvent(self, e):
        f = 1.0015 ** e.angleDelta().y()
        self.zoom = max(1.0, min(8.0, self.zoom * f))
        if self.zoom == 1.0:
            self.pan = QPointF(0, 0)
        self.update()

    def mousePressEvent(self, e):
        self._drag = e.position()

    def mouseMoveEvent(self, e):
        if self._drag is not None and self.zoom > 1:
            self.pan += e.position() - self._drag
            self._drag = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        self.zoom, self.pan = 1.0, QPointF(0, 0)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(24, 18, -24, -24)
        if not self.renderer:
            return
        ar = 17 / 11
        w = min(r.width(), r.height() * ar)
        h = w / ar
        sheet = QRectF(r.center().x() - w / 2, r.center().y() - h / 2, w, h)
        p.setPen(Qt.PenStyle.NoPen)
        for i, a in enumerate((50, 32, 18)):
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRect(sheet.translated(4 + 3 * i, 7 + 4 * i))
        p.save()
        p.setClipRect(sheet)
        p.translate(sheet.center() + self.pan)
        p.scale(self.zoom, self.zoom)
        p.translate(-sheet.center())
        p.setOpacity(self.fade)
        self.renderer.render(p, sheet)
        p.restore()


class Results(QWidget):
    back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None  # {"options": [...], "sheets": {(opt, theme): [(num, title, svg)]}}
        self.opt = 0
        self.theme = "modern"
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(10)
        top = QHBoxLayout()
        self.backbtn = QToolButton()
        self.backbtn.setText("←  Concept")
        self.backbtn.setStyleSheet(BTN)
        self.backbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.backbtn.clicked.connect(self.back.emit)
        self.title = QLabel("")
        self.title.setStyleSheet("color:#f1f1ef; font-family:'Avenir Next Condensed'; font-size:22px; font-weight:600;")
        self.sub = QLabel("")
        self.sub.setStyleSheet("color:#9aa0a8; font-family: 'Avenir Next'; font-size: 12px;")
        tbox = QVBoxLayout()
        tbox.setSpacing(0)
        tbox.addWidget(self.title)
        tbox.addWidget(self.sub)
        self.styles = Segmented(STYLE_OPTS)
        self.styles.changed.connect(self._style)
        self.optbox = QHBoxLayout()
        self.optbox.setSpacing(6)
        self.export = QToolButton()
        self.export.setText("EXPORT PDF")
        self.saveb = QToolButton()
        self.saveb.setText("SAVE MODEL")
        for b in (self.export, self.saveb):
            b.setStyleSheet(BTN)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export.clicked.connect(self._export)
        self.saveb.clicked.connect(self._save)
        top.addWidget(self.backbtn)
        top.addSpacing(14)
        top.addLayout(tbox)
        top.addStretch(1)
        top.addWidget(self.styles)
        root.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(14)
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setFlow(QListWidget.Flow.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setIconSize(QSize(176, 114))
        self.thumbs.setGridSize(QSize(196, 146))
        self.thumbs.setFixedWidth(214)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.setStyleSheet("""QListWidget { background: transparent; border: none; color: #c9cdd2;
            font-family: 'Avenir Next'; font-size: 11px; }
            QListWidget::item { padding: 6px; border-radius: 8px; }
            QListWidget::item:selected { background: rgba(241,241,239,0.12); color: #f1f1ef; }
            QListWidget::item:hover { background: rgba(255,255,255,0.06); }""" + SCROLL)
        self.thumbs.currentRowChanged.connect(self._show)
        self.view = SheetView()
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.info.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.info.setStyleSheet("color:#c9cdd2; font-family: 'Avenir Next'; font-size: 12px;")
        scroll = QScrollArea()
        scroll.setWidget(self.info)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(290)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }" + SCROLL)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body.addWidget(self.thumbs)
        body.addWidget(self.view, 1)
        body.addWidget(scroll)
        root.addLayout(body, 1)
        self.busy = ""

    # -- data -----------------------------------------------------------------
    def load(self, data: dict, theme: str = "modern", opt: int = 0, mode: str = "rough"):
        self.data = data
        self.opt = opt
        self.theme = theme
        self.mode = mode
        self.styles.set_current(theme)
        while self.optbox.count():
            w = self.optbox.takeAt(0).widget()
            if w:
                w.deleteLater()
        opts = data["options"]
        if False and len(opts) > 1:
            lab = QLabel("OPTION")
            lab.setStyleSheet("color:#9aa0a8; font-family: Futura; font-size: 10px; letter-spacing: 2px;")
            self.optbox.addWidget(lab)
            self.optbtns = []
            for i in range(len(opts)):
                b = QToolButton()
                b.setText("ABC"[i])
                b.setCheckable(True)
                b.setChecked(i == 0)
                b.setStyleSheet(BTN)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _c, i=i: self._option(i))
                self.optbox.addWidget(b)
                self.optbtns.append(b)
        self._refresh()

    def house(self):
        return self.data["options"][self.opt].house

    def _sheets(self, cb):
        key = (self.opt, self.theme, getattr(self, "mode", "rough"))
        cache = self.data.setdefault("sheets", {})
        if key in cache:
            cb(cache[key])
            return
        house, th, mode = self.house(), themes.get(self.theme), getattr(self, "mode", "rough")
        self.busy = "Inking…"
        self._info()

        def job():
            return [(s.number, s.title, sheet_to_svg(s, th)) for s in build_set(house, th, mode=mode)]

        def got(sheets):
            cache[key] = sheets
            self.busy = ""
            self._info()
            cb(sheets)

        worker.run(job, got)

    def _refresh(self):
        h = self.house()
        self.title.setText(h.name.upper())
        st = h.brief.style if h.brief else h.style
        self.sub.setText(f"{st} · {h.stories}-story · {fmt_area(h.heated_area)} · "
                         f"{len(h.bedrooms)} bed / {h.baths:g} bath")
        self._info()

        def show(sheets):
            row = max(self.thumbs.currentRow(), 0)
            self.thumbs.blockSignals(True)
            self.thumbs.clear()
            for num, title, svg in sheets:
                it = QListWidgetItem(QIcon(self._thumb(svg)), f"{num}  {title}")
                self.thumbs.addItem(it)
            self.thumbs.blockSignals(False)
            self.thumbs.setCurrentRow(min(row, len(sheets) - 1))
            self._show(self.thumbs.currentRow())

        self._sheets(show)

    def _thumb(self, svg: str) -> QPixmap:
        pm = QPixmap(176, 114)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, 176, 114))
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawRect(QRectF(0.5, 0.5, 175, 113))
        p.end()
        return pm

    def _show(self, row):
        key = (self.opt, self.theme, getattr(self, "mode", "rough"))
        sheets = self.data["sheets"].get(key) if self.data else None
        if sheets and 0 <= row < len(sheets):
            self.view.set_svg(sheets[row][2])

    def _style(self, key):
        self.theme = key
        self._refresh()

    def _option(self, i):
        self.opt = i
        self._refresh()

    def _info(self):
        h = self.house()
        lv0 = h.levels[0].footprint.bounds
        found = checks.run(h)
        s = checks.summary(found)
        dot = {"pass": "#6fa56b", "warn": "#d6a23a", "fail": "#d0533f"}
        rows = "".join(
            f"<tr><td style='color:{dot[f.status]}; padding-right:6px'>●</td>"
            f"<td><b>{f.rule.split(' ', 1)[1]}</b> · {f.where}<br>"
            f"<span style='color:#8a9098'>{f.detail}</span></td></tr>"
            for f in sorted(found, key=lambda f: ("fail", "warn", "pass").index(f.status)))
        rooms = "".join(
            f"<p style='margin:6px 0 2px 0; color:#f1f1ef; letter-spacing:2px; font-family:Futura; "
            f"font-size:10px'>{lv.name.upper()}</p>"
            + "<br>".join(f"{r.name} <span style='color:#8a9098'>{fmt_ft(r.w)} × {fmt_ft(r.h)}</span>"
                          for r in lv.rooms if r.kind not in ("hall",))
            for lv in h.levels)
        busy = f"<p style='color:#f1f1ef'>{self.busy}</p>" if self.busy else ""
        brief = h.brief
        musts = ", ".join(brief.must_haves) if brief and brief.must_haves else "—"
        self.info.setText(f"""
            {busy}
            <p style='font-family:Futura; letter-spacing:3px; font-size:11px; color:#f1f1ef'>THE HOUSE</p>
            <table cellspacing=3>
            <tr><td style='color:#8a9098'>Heated area</td><td><b>{fmt_area(h.heated_area)}</b></td></tr>
            <tr><td style='color:#8a9098'>Footprint</td><td>{fmt_ft(lv0[2] - lv0[0])} × {fmt_ft(lv0[3] - lv0[1])}</td></tr>
            <tr><td style='color:#8a9098'>Bed / bath</td><td>{len(h.bedrooms)} / {h.baths:g}</td></tr>
            <tr><td style='color:#8a9098'>Stories</td><td>{h.stories}</td></tr>
            <tr><td style='color:#8a9098'>Lot</td><td>{brief.lot if brief else '—'}</td></tr>
            <tr><td style='color:#8a9098'>Must-haves</td><td>{musts}</td></tr>
            </table>
            <p style='font-family:Futura; letter-spacing:3px; font-size:11px; color:#f1f1ef; margin-top:14px'>
            CODE PRE-CHECK</p>
            <p>{s['pass']} pass · {s['warn']} warn · {s['fail']} fail
            <span style='color:#8a9098'>(informal, after the 2021 IRC)</span></p>
            <table cellspacing=4>{rows}</table>
            <p style='font-family:Futura; letter-spacing:3px; font-size:11px; color:#f1f1ef; margin-top:14px'>
            ROOMS</p>{rooms}""")

    # -- actions --------------------------------------------------------------
    def _export(self):
        h = self.house()
        slug = "".join(c if c.isalnum() else "-" for c in h.name.lower()).strip("-")
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{slug}-{self.theme}.pdf",
                                              "PDF (*.pdf)")
        if path:
            from .. import render_pdf
            worker.run(lambda: render_pdf(h, path, style=self.theme), lambda _p: None)

    def _save(self):
        h = self.house()
        slug = "".join(c if c.isalnum() else "-" for c in h.name.lower()).strip("-")
        path, _ = QFileDialog.getSaveFileName(self, "Save house model", f"{slug}.json",
                                              "House model (*.json *.yaml)")
        if path:
            save(h, path)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), S.BG)
