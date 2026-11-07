"""Run slow work (design, rendering, the local model) off the UI thread."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class Task(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any], parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as e:  # surfaced in the UI
            self.failed.emit(f"{e}\n\n{traceback.format_exc(limit=3)}")


_live: set[Task] = set()


def run(fn: Callable[[], Any], on_done: Callable[[Any], None],
        on_fail: Callable[[str], None] | None = None) -> Task:
    t = Task(fn)
    _live.add(t)
    t.done.connect(on_done)
    if on_fail:
        t.failed.connect(on_fail)
    t.finished.connect(lambda: _live.discard(t))
    t.start()
    return t
