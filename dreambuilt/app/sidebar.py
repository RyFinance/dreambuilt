"""Left rail: new house, samples, and every previous build."""
from __future__ import annotations

import time

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QVBoxLayout, QWidget

from .. import samples
from . import history
from .home_view import has_model

ITEM = """QPushButton { color: #f1f1ef; background: transparent; border: none; border-radius: 8px;
    text-align: left; padding: 8px 10px; font-family: 'Avenir Next'; font-size: 13.5px; }
    QPushButton:hover { background: rgba(241,241,239,0.07); }"""
LIST = """QListWidget { background: transparent; border: none; color: rgba(241,241,239,0.85);
    font-family: 'Avenir Next'; font-size: 13.5px; outline: none; }
    QListWidget::item { padding: 7px 10px; border-radius: 8px; }
    QListWidget::item:hover { background: rgba(241,241,239,0.06); }
    QListWidget::item:selected { background: rgba(241,241,239,0.12); color: #f1f1ef; }
    QScrollBar:vertical { background: transparent; width: 6px; }
    QScrollBar::handle:vertical { background: rgba(241,241,239,0.2); border-radius: 3px; }
    QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"""


class Sidebar(QWidget):
    new_house = Signal()
    open_entry = Signal(object)
    open_sample = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(270)
        self.setObjectName("side")
        self.setStyleSheet("#side { background: #0e0f11; border-right: 1px solid rgba(241,241,239,0.06); }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 16, 12, 14)
        lay.setSpacing(2)
        title = QLabel("Dream Built")
        title.setStyleSheet("color:#f1f1ef; font-family:'Avenir Next'; font-size:17px; font-weight:600; padding: 2px 10px 12px 10px;")
        lay.addWidget(title)
        new = QPushButton()
        new.setText("✎   New house")
        new.setStyleSheet(ITEM.replace("background: transparent", "background: rgba(241,241,239,0.07)"))
        new.setCursor(Qt.CursorShape.PointingHandCursor)
        new.clicked.connect(self.new_house.emit)
        new.setMinimumWidth(246)
        lay.addWidget(new)
        lay.addSpacing(14)
        lay.addWidget(self._head("Samples"))
        for fn in samples.SAMPLES.values():
            h = fn()
            b = QPushButton()
            b.setText(f"{h.name}")
            b.setToolTip(f"{h.stories}-storey, {len(h.bedrooms)} bed — hand-drawn reference")
            b.setStyleSheet(ITEM)
            b.setMinimumWidth(246)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, fn=fn: self.open_sample.emit(fn()))
            lay.addWidget(b)
        lay.addSpacing(14)
        lay.addWidget(self._head("Recents"))
        self.list = QListWidget()
        self.list.setStyleSheet(LIST)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.itemClicked.connect(lambda it: self.open_entry.emit(it.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)
        foot = QLabel(("●  Local AI ready" if has_model() else "○  Local AI not installed") + "\n    Everything stays on this Mac")
        foot.setStyleSheet("color: rgba(241,241,239,0.45); font-family: 'Avenir Next'; font-size: 11.5px; padding: 8px 10px;")
        lay.addWidget(foot)
        self.refresh()

    def _head(self, s):
        l = QLabel(s)
        l.setStyleSheet("color: rgba(241,241,239,0.45); font-family: 'Avenir Next'; font-size: 12px; padding: 6px 10px 4px 10px;")
        return l

    def refresh(self, select_id: str | None = None):
        self.list.clear()
        for root, versions in history.grouped():
            latest = versions[0] if versions else root
            label = root.title + (f"   · v{latest.version}" if versions else "")
            self._add(label, latest, select_id, indent=False)
            for e in versions[1:] + ([root] if versions else []):
                self._add(f"      v{e.version}", e, select_id, indent=True)

    def _add(self, label, e, select_id, indent):
        it = QListWidgetItem(label)
        it.setToolTip(time.strftime("%b %d, %H:%M", time.localtime(e.created)) + "\n" + e.text)
        it.setData(Qt.ItemDataRole.UserRole, e)
        if indent:
            it.setForeground(__import__("PySide6.QtGui", fromlist=["QColor"]).QColor(241, 241, 239, 120))
        self.list.addItem(it)
        if select_id and e.id == select_id:
            self.list.setCurrentItem(it)

    def _menu(self, pos: QPoint):
        it = self.list.itemAt(pos)
        if not it:
            return
        m = QMenu(self)
        m.setStyleSheet("QMenu { background:#1a1b1e; color:#f1f1ef; border:1px solid rgba(241,241,239,0.12); padding:4px; }"
                        "QMenu::item { padding:6px 16px; border-radius:6px; } QMenu::item:selected { background: rgba(241,241,239,0.1); }")
        act = m.addAction("Delete")
        if m.exec(self.list.mapToGlobal(pos)) is act:
            history.delete(it.data(Qt.ItemDataRole.UserRole))
            self.refresh()
