"""Interactive pieces: animated tool tiles, chips, steppers, segmented toggle, stamp button."""
from __future__ import annotations

import math
from typing import Callable

from PySide6.QtCore import (QEasingCurve, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLayout, QSizePolicy, QToolButton, QWidget

from . import style as S
T = S


def animate(owner, start, end, ms, on_value: Callable, curve=QEasingCurve.Type.OutCubic,
            on_done: Callable | None = None) -> QVariantAnimation:
    a = QVariantAnimation(owner)
    a.setStartValue(float(start))
    a.setEndValue(float(end))
    a.setDuration(ms)
    a.setEasingCurve(curve)
    a.valueChanged.connect(on_value)
    if on_done:
        a.finished.connect(on_done)
    a.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return a


class Segmented(QWidget):
    """Pill toggle with a sliding brass thumb."""
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.options = options
        self.index = 0
        self.thumb = 0.0
        self.setFixedHeight(34)
        self.setMinimumWidth(130 * len(options))
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def current(self) -> str:
        return self.options[self.index][0]

    def set_current(self, key: str):
        for i, (k, _) in enumerate(self.options):
            if k == key:
                self.index = i
                self.thumb = float(i)
                self.update()

    def mousePressEvent(self, e):
        i = int(e.position().x() / (self.width() / len(self.options)))
        i = max(0, min(i, len(self.options) - 1))
        if i != self.index:
            self.index = i
            animate(self, self.thumb, float(i), 260, lambda v: (setattr(self, "thumb", v), self.update()))
            self.changed.emit(self.options[i][0])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        w = r.width() / len(self.options)
        th = QRectF(r.left() + self.thumb * w + 2, r.top() + 2, w - 4, r.height() - 4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(S.WHITE)
        p.drawRoundedRect(th, th.height() / 2, th.height() / 2)
        p.setFont(S.mono(9.5, 1.5))
        for i, (_, label) in enumerate(self.options):
            p.setPen(QColor("#08090b") if i == self.index else S.WHITE)
            p.drawText(QRectF(r.left() + i * w, r.top(), w, r.height()),
                       Qt.AlignmentFlag.AlignCenter, label.upper())


class FlowLayout(QLayout):
    """Lays widgets left to right and wraps onto new lines (the Qt flow-layout recipe)."""

    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self._items = []
        self._sp = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s

    def _do(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            nx = x + hint.width() + self._sp
            if nx - self._sp > rect.right() and line > 0:
                x, y = rect.x(), y + line + self._sp
                nx = x + hint.width() + self._sp
                line = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line = max(line, hint.height())
        return y + line - rect.y()


__all__ = ["FlowLayout", "Segmented", "animate"]
