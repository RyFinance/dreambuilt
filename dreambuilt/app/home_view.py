"""Home: one prompt box in the middle, like a chat."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QToolButton,
                               QVBoxLayout, QWidget)

from .. import brief as briefs
from . import style as S
from .widgets import animate

SUGGESTIONS = [
    ("⌂", "Surrey two-storey, 4 bed 3.5 bath, 3,800 sq ft, 66 x 140 lot, fireplace"),
    ("⌂", "Craftsman bungalow, 3 bed 2 bath, 1,600 sq ft, 60 x 130 lot, porch and fireplace"),
    ("⌂", "Two-storey colonial, 4 bed 2.5 bath, 2,400 sq ft, 70 x 140 lot, office"),
]
IMAGES = (".png", ".jpg", ".jpeg", ".heic", ".webp", ".gif", ".bmp", ".tif", ".tiff")
STATUS = ["Reading the brief", "Laying out the rooms", "Checking circulation", "Placing doors and windows",
          "Framing the roof", "Projecting elevations"]


def model_dir() -> Path:
    from .. import llm
    return Path(llm.DEFAULT_MODEL)  # (DREAMBUILT_MODEL picks another local model)


def has_model() -> bool:
    return model_dir().joinpath("model.safetensors").exists()


class PhotoChip(QWidget):
    """Thumbnail of the attached reference photo, with a remove button."""
    removed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pix = None
        self.name = ""
        self.setFixedHeight(64)
        self.hide()

    def set_photo(self, path: str):
        self.pix = QPixmap(path)
        self.name = Path(path).name
        self.setVisible(bool(path) and not self.pix.isNull())
        self.update()

    def mousePressEvent(self, e):
        if 44 < e.position().x() < 68 and e.position().y() < 22:  # the little x
            self.removed.emit()

    def paintEvent(self, e):
        if not self.pix:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(2, 4, 56, 56)
        pm = self.pix.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                             Qt.TransformationMode.SmoothTransformation)
        p.save()
        path = __import__("PySide6.QtGui", fromlist=["QPainterPath"]).QPainterPath()
        path.addRoundedRect(r, 10, 10)
        p.setClipPath(path)
        p.drawPixmap(int(r.center().x() - pm.width() / 2), int(r.center().y() - pm.height() / 2), pm)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawEllipse(QPointF(56, 9), 8, 8)
        p.setPen(QPen(S.WHITE, 1.4))
        p.drawLine(QPointF(53, 6), QPointF(59, 12))
        p.drawLine(QPointF(59, 6), QPointF(53, 12))
        p.setPen(S.MUTED)
        p.setFont(S.font(size=11))
        p.drawText(QRectF(68, 22, 400, 20), Qt.AlignmentFlag.AlignVCenter, self.name + "  ·  reference photo")


class PromptBox(QWidget):
    """Rounded prompt with + (attach photo), the text, a local-AI toggle and a send button.

    Drop an image anywhere on it to attach. Enter sends, Shift+Enter breaks a line.
    """
    send = Signal(str, str, bool)  # text, photo path, use local model

    def __init__(self, placeholder: str, compact: bool = False, parent=None):
        super().__init__(parent)
        self.photo = ""
        self.compact = compact
        self.drag = False
        self.setAcceptDrops(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 10, 12, 10)
        outer.setSpacing(4)
        self.chip = PhotoChip()
        self.chip.removed.connect(lambda: self.set_photo(""))
        outer.addWidget(self.chip)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.plus = self._icon("+", "Attach a reference photo")
        self.plus.clicked.connect(self._pick)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(placeholder)
        self.text.setFixedHeight(38 if compact else 46)
        self.text.setStyleSheet("""QPlainTextEdit { background: transparent; border: none; color: #f1f1ef;
            font-family: 'Avenir Next'; font-size: 16px; padding-top: 8px; }""")
        self.text.installEventFilter(self)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.textChanged.connect(self._grow)
        self.improve = self._icon("✦", "Improve: the local AI fills in what the brief leaves out")
        self.improve.setEnabled(has_model())
        self.ai = self._icon("AI", "Read with the local AI model (MiniCPM5-2B, offline)")
        self.ai.setCheckable(True)
        self.ai.setEnabled(has_model())
        self.ai.setChecked(has_model())
        self.go = self._icon("↑", "Draft")
        self.go.setFixedSize(36, 36)
        self.go.setStyleSheet("""QToolButton { background: #f1f1ef; color: #08090b; border-radius: 18px;
            font-size: 17px; font-weight: 700; } QToolButton:disabled { background: rgba(241,241,239,0.25); }""")
        self.go.clicked.connect(self._send)
        row.addWidget(self.plus, 0, Qt.AlignmentFlag.AlignBottom)
        self.plus.hide()  # (this build reads text only: no photo model)
        row.addWidget(self.text, 1)
        self.improve.hide()  # the AI fills in every brief on its own when you draft
        row.addWidget(self.ai, 0, Qt.AlignmentFlag.AlignBottom)
        row.addWidget(self.go, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(row)
        self.go.setEnabled(False)
        self.text.textChanged.connect(lambda: self.go.setEnabled(bool(self.text.toPlainText().strip())))

    def _icon(self, t, tip):
        b = QToolButton()
        b.setText(t)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(34, 34)
        b.setStyleSheet("""QToolButton { background: transparent; color: rgba(241,241,239,0.75); border: none;
            border-radius: 17px; font-family: 'Avenir Next'; font-size: 19px; }
            QToolButton:hover { background: rgba(241,241,239,0.1); color: #f1f1ef; }
            QToolButton:checked { background: rgba(241,241,239,0.18); color: #f1f1ef; }
            QToolButton:disabled { color: rgba(241,241,239,0.2); }""")
        if t == "AI":
            b.setStyleSheet(b.styleSheet().replace("font-size: 19px", "font-size: 11px; font-weight: 700"))
        return b

    def _grow(self):
        lines = self.text.document().size().height()
        h = max(38 if self.compact else 46, min(140, int(lines * 22 + 16)))
        self.text.setFixedHeight(h)

    def eventFilter(self, obj, e):
        if obj is self.text and e.type() == QEvent.Type.KeyPress:
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._send()
                return True
        return super().eventFilter(obj, e)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), "Reference photo", str(Path.home() / "Pictures"),
                                              "Images (*.png *.jpg *.jpeg *.heic *.webp *.gif *.bmp *.tif *.tiff)")
        if path:
            self.set_photo(path)

    def set_photo(self, path: str):
        self.photo = path
        self.chip.set_photo(path) if path else self.chip.hide()
        self.update()

    def dragEnterEvent(self, e):
        return  # (no photo model in this build)
        urls = e.mimeData().urls()
        if urls and urls[0].toLocalFile().lower().endswith(IMAGES):
            self.drag = True
            self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.drag = False
        self.update()

    def dropEvent(self, e):
        self.drag = False
        urls = e.mimeData().urls()
        if urls:
            self.set_photo(urls[0].toLocalFile())
        self.update()

    def _send(self):
        t = self.text.toPlainText().strip()
        if t:
            self.send.emit(t, self.photo, self.ai.isChecked())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(S.WHITE if self.drag else QColor(241, 241, 239, 30), 1.5 if self.drag else 1,
                      Qt.PenStyle.DashLine if self.drag else Qt.PenStyle.SolidLine))
        p.setBrush(QColor("#1a1b1e"))
        p.drawRoundedRect(r, 24, 24)
        if self.drag:
            p.setPen(S.WHITE)
            p.setFont(S.font(size=13))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Drop to use as the reference photo")


class HomeView(QWidget):
    """Empty state: a heading, the prompt box, a few suggestions."""
    draft = Signal(str, str, bool)
    details = Signal(str)
    cancel_revision = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._undo = ""
        lay = QVBoxLayout(self)
        lay.addStretch(3)
        self.banner = QLabel("")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.banner.setStyleSheet("color: rgba(241,241,239,0.6); font-family: Menlo; font-size: 11px; letter-spacing: 1px;")
        self.banner_cancel = QPushButton("Start a new design instead")
        self.banner_cancel.setStyleSheet("""QPushButton { color: rgba(241,241,239,0.45); background: transparent; border: none;
            font-family: 'Avenir Next'; font-size: 12px; text-decoration: underline; }""")
        self.banner_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.banner_cancel.clicked.connect(self.cancel_revision.emit)
        self.banner.hide()
        self.banner_cancel.hide()
        lay.addWidget(self.banner)
        lay.addWidget(self.banner_cancel, 0, Qt.AlignmentFlag.AlignHCenter)
        self.head = head = QLabel("What are we building?")
        head.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        head.setStyleSheet("color:#f1f1ef; font-family:'Avenir Next'; font-size:30px; font-weight:500;")
        lay.addWidget(head)
        lay.addSpacing(22)
        col = QWidget()
        col.setFixedWidth(780)
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        self.box = PromptBox("Describe your house…")
        self.box.send.connect(self.draft.emit)

        self.undo = QPushButton("Undo")
        self.undo.setStyleSheet("""QPushButton { color: #f1f1ef; background: transparent; border: none;
            font-family: 'Avenir Next'; font-size: 12px; text-decoration: underline; padding: 0 18px; }""")
        self.undo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo.clicked.connect(self._do_undo)
        self.undo.hide()
        self.reading = QLabel("")
        self.reading.setWordWrap(True)
        self.reading.setStyleSheet("color: rgba(241,241,239,0.45); font-family: Menlo; font-size: 11px; padding: 4px 18px;")
        cl.addWidget(self.box)
        cl.addWidget(self.reading)
        links = QHBoxLayout()
        links.addWidget(self.undo)
        self.more = QPushButton("Details…  set every part of the brief")
        self.more.setStyleSheet("""QPushButton { color: rgba(241,241,239,0.6); background: transparent; border: none;
            font-family: 'Avenir Next'; font-size: 12px; text-decoration: underline; padding: 0 18px; }
            QPushButton:hover { color: #f1f1ef; }""")
        self.more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more.clicked.connect(lambda: self.details.emit(self.box.text.toPlainText()))
        links.addWidget(self.more)
        links.addStretch(1)
        cl.addLayout(links)
        cl.addSpacing(10)
        for icon, s in SUGGESTIONS:
            b = QPushButton()
            b.setText(f"{icon}   {s}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""QPushButton { color: rgba(241,241,239,0.7); background: transparent; border: none;
                border-radius: 12px; text-align: left; padding: 10px 16px; font-family: 'Avenir Next'; font-size: 14px; }
                QPushButton:hover { background: rgba(241,241,239,0.06); color: #f1f1ef; }""")
            b.setMinimumWidth(780)
            b.clicked.connect(lambda _c=False, s=s: (self.box.text.setPlainText(s), self.box.text.setFocus()))
            cl.addWidget(b)
        lay.addWidget(col, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(4)
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.setInterval(250)
        self._t.timeout.connect(self._read)
        self.box.text.textChanged.connect(self._t.start)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        self.box.dragEnterEvent(e)

    def dropEvent(self, e):
        self.box.dropEvent(e)

    def _read(self):
        t = self.box.text.toPlainText().strip()
        if not t:
            self.reading.setText("")
            return
        b = briefs.parse_text(t)
        probs = [p for p in b.validate() if "style" in p]
        msg = ("⚠  " + probs[0]) if probs else b.summary().replace("; must-haves: none", "")
        if b.wishes:
            msg += f"\n·  {len(b.wishes)} small things kept for the notes (finishes, lighting…)"
        if b.notes:
            msg += "\n?  Not drawn yet: " + "; ".join(b.notes[:3])
        if has_model() and briefs.is_thin(t):
            msg += "\n✦  The local AI fills in the rest when you draft."
        self.reading.setText(msg)

    # -- the local model fills in a thin brief -------------------------------------------
    def _improve(self):
        t = self.box.text.toPlainText().strip()
        if not t or not has_model():
            return
        from . import worker
        from .. import llm
        self._undo = t
        self.box.improve.setEnabled(False)
        self.reading.setText("✦  Filling in the gaps…")

        def done(res):
            para, _b = res
            self.box.text.setPlainText(para)
            self.box.improve.setEnabled(True)
            self.undo.show()
            self._read()

        def failed(msg):
            self.box.improve.setEnabled(True)
            self.reading.setText("The local AI couldn't improve that one: " + msg.split("\n")[0])

        worker.run(lambda: llm.improve(t, str(model_dir())), done, failed)

    def _do_undo(self):
        if self._undo:
            self.box.text.setPlainText(self._undo)
        self.undo.hide()

    def set_revising(self, title: str | None, version: int = 0, text: str = ""):
        """Show (or clear) the "revising an old design" state."""
        if title:
            self.banner.setText(f"REVISING  ·  {title}  ·  this will be v{version}")
            self.head.setText("What should change?")
            self.box.text.setPlainText(text)
            self.banner.show()
            self.banner_cancel.show()
        else:
            self.banner.hide()
            self.banner_cancel.hide()
            self.head.setText("What are we building?")
        self.undo.hide()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), S.BG)


class DraftingView(QWidget):
    """The plan being drawn while the house is designed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self.segments = []
        self.status = ""
        self.text = ""

    def start(self, text: str):
        self.text = text
        self.segments = []
        self._a = animate(self, 0.0, 1.0, 2600, self._prog)

    def _prog(self, v):
        self.progress = v
        self.status = STATUS[min(int(v * len(STATUS)), len(STATUS) - 1)]
        self.update()

    def show_plan(self, house):
        lv = house.levels[0]
        x0, y0, x1, y1 = lv.footprint.bounds
        r = QRectF(self.rect()).adjusted(self.width() * 0.22, self.height() * 0.2, -self.width() * 0.22,
                                         -self.height() * 0.24)
        k = min(r.width() / (x1 - x0), r.height() / (y1 - y0))
        ox = r.center().x() - (x0 + x1) / 2 * k
        oy = r.center().y() + (y0 + y1) / 2 * k
        P = lambda x, y: QPointF(ox + x * k, oy - y * k)
        ring = list(lv.footprint.exterior.coords)
        segs = [(P(*a), P(*b), 3.0) for a, b in zip(ring, ring[1:])]
        for rm in lv.rooms:
            pts = [(rm.x, rm.y), (rm.x + rm.w, rm.y), (rm.x + rm.w, rm.y + rm.h), (rm.x, rm.y + rm.h)]
            segs += [(P(*a), P(*b), 1.1) for a, b in zip(pts, pts[1:] + pts[:1])]
        self.segments = segs

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), S.BG)
        p.setPen(QColor(241, 241, 239, 150))
        p.setFont(S.font(size=14))
        p.drawText(QRectF(0, 40, self.width(), 24), Qt.AlignmentFlag.AlignHCenter, self.text[:110])
        n = len(self.segments)
        drawn = self.progress * n * 1.15
        for i, (a, b, w) in enumerate(self.segments):
            if i > drawn:
                break
            p.setPen(QPen(QColor(241, 241, 239, 225), w))
            p.drawLine(a, a + (b - a) * min(1.0, drawn - i))
        p.setPen(S.MUTED)
        p.setFont(S.mono(11.5, 2))
        p.drawText(QRectF(0, self.height() - 90, self.width(), 24), Qt.AlignmentFlag.AlignHCenter,
                   self.status.upper() + "…")
