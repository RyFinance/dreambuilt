"""Smoke test the desktop app offscreen: every screen builds and paints."""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_screens_paint(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAMBUILT_HISTORY", str(tmp_path / "history"))
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from dreambuilt.app import history
    from dreambuilt.app.main import MainWindow
    from dreambuilt.app.render_views import elevation_image, plan_image
    from dreambuilt.design import Option
    from dreambuilt.samples import halsted
    w = MainWindow()
    w.resize(1280, 800)
    w.brief.setGeometry(w.stack.rect())
    w.brief.box.text.setPlainText("craftsman 3 bed 2 bath 1600 sqft 60x130")
    assert w.brief.box.go.isEnabled()
    w.brief.box.set_photo(__file__)  # not an image: the chip stays hidden, nothing breaks
    assert not w.brief.grab().isNull()
    h = halsted()
    history.save("test build", [Option(h, 0, [])])
    w.side.refresh()
    assert w.side.list.count() == 1
    w.concept.setGeometry(w.stack.rect())
    w.concept.load({"options": [Option(h, 0, [])]})
    w.concept.plan.set_level(h.levels[0], plan_image(h, 0))
    w.concept.elev.set_image(elevation_image(h))
    assert not w.concept.grab().isNull()
    assert w.menuBar().actions()[0].text() == "File"
    _ = app
