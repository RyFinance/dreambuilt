"""App look: quiet, dark, architectural. One accent (white), condensed display type."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QRadialGradient

BG = QColor("#08090b")
PANEL = QColor("#000000")
NAVY = QColor("#0a1626")
GRID_MINOR = QColor(70, 120, 190, 30)
GRID_MAJOR = QColor(70, 120, 190, 62)
WHITE = QColor("#f1f1ef")
MUTED = QColor(241, 241, 239, 120)
FAINT = QColor(241, 241, 239, 40)
OK = QColor("#7fb77e")
WARN = QColor("#d8b45a")
FAIL = QColor("#e0705c")

DISPLAY = "Avenir Next Condensed"
BODY = "Avenir Next"
MONO = "Menlo"


def font(family=BODY, size=12.0, weight=QFont.Weight.Normal, spacing=0.0) -> QFont:
    f = QFont(family)
    f.setPointSizeF(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


def display(size=40.0) -> QFont:
    return font(DISPLAY, size, QFont.Weight.DemiBold, 0.5)


def mono(size=10.5, spacing=1.2) -> QFont:
    return font(MONO, size, QFont.Weight.Normal, spacing)


def blueprint_grid(p: QPainter, r: QRectF, minor: float = 22.0, major_every: int = 5) -> None:
    p.fillRect(r, NAVY)
    g = QRadialGradient(r.center(), max(r.width(), r.height()) * 0.75)
    g.setColorAt(0, QColor(30, 70, 130, 60))
    g.setColorAt(1, QColor(0, 0, 0, 120))
    p.fillRect(r, QBrush(g))
    i = 0
    x = r.left()
    while x <= r.right():
        p.setPen(QPen(GRID_MAJOR if i % major_every == 0 else GRID_MINOR, 1))
        p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        x += minor
        i += 1
    j = 0
    y = r.top()
    while y <= r.bottom():
        p.setPen(QPen(GRID_MAJOR if j % major_every == 0 else GRID_MINOR, 1))
        p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        y += minor
        j += 1


LINK = """QToolButton { color: rgba(241,241,239,0.65); background: transparent; border: none;
    font-family: 'Avenir Next'; font-size: 13px; padding: 4px 2px; }
    QToolButton:hover { color: #f1f1ef; }
    QToolButton:checked { color: #f1f1ef; border-bottom: 1px solid #f1f1ef; }"""

PRIMARY = """QPushButton { background: #f1f1ef; color: #08090b; border: none; border-radius: 4px;
    font-family: 'Avenir Next'; font-size: 14px; font-weight: 600; padding: 12px 26px; }
    QPushButton:hover { background: #ffffff; }
    QPushButton:disabled { background: rgba(241,241,239,0.25); color: rgba(8,9,11,0.6); }"""

SCROLL = """
    QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
    QScrollBar::handle:vertical { background: rgba(241,241,239,0.25); border-radius: 4px; min-height: 30px; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"""
