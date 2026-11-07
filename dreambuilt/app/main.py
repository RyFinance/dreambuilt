"""Dream Built desktop app.

Opens on the brief. Draft -> the concept view (exterior + interactive plans).
The full drawing set, exports and samples live in the menu bar.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QGraphicsOpacityEffect, QHBoxLayout,
                               QMainWindow, QMessageBox, QStackedWidget, QWidget)

from .. import samples
from . import style as S
from . import worker
from . import history
from .concept_view import ConceptView
from .home_view import DraftingView, HomeView, model_dir
from .sidebar import Sidebar
from .results import Results
from .widgets import animate


def app_icon() -> QIcon:
    pm = QPixmap(256, 256)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(S.NAVY)
    p.drawRoundedRect(QRectF(8, 8, 240, 240), 52, 52)
    p.setPen(QPen(S.GRID_MAJOR, 2))
    for i in range(1, 6):
        p.drawLine(int(8 + i * 40), 20, int(8 + i * 40), 236)
        p.drawLine(20, int(8 + i * 40), 236, int(8 + i * 40))
    p.setPen(QPen(S.WHITE, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
    p.drawPolyline([QPointF(60, 120), QPointF(128, 62), QPointF(196, 120)])
    p.drawRect(QRectF(78, 118, 100, 78))
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dream Built")
        self.setWindowIcon(app_icon())
        self.resize(1480, 920)
        self.setMinimumSize(1200, 760)
        self.render_style = "modern"
        self.sheet_set = "rough"
        self.data = None
        central = QWidget()
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.side = Sidebar()
        self.stack = QStackedWidget()
        row.addWidget(self.side)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.brief = HomeView()
        self.drafting = DraftingView()
        self.concept = ConceptView()
        self.sheets = Results()
        for w in (self.brief, self.drafting, self.concept, self.sheets):
            self.stack.addWidget(w)
        self.text = ""
        self.current_brief = None
        self.current_entry = None
        self.revising = None
        self.brief.draft.connect(lambda t, ph, ai: self._draft(t, ph, ai))
        self.brief.details.connect(self._details)
        self.concept.refine.connect(self._refine)
        self.concept.edit_ops.connect(self._apply_edits)
        self.concept.react.connect(self._react)
        self.concept.breed.connect(self._breed)
        self.concept.show_brief.connect(lambda: self.show_view(self.brief))
        self.concept.show_set.connect(self._show_set)
        self.concept.edit_brief.connect(self._edit_brief)
        self.brief.cancel_revision.connect(self._new)
        self.side.new_house.connect(self._new)
        self.side.open_entry.connect(self._open_entry)
        self.side.open_sample.connect(self._show_house)
        self.sheets.back.connect(lambda: self.show_view(self.concept))
        self._menus()
        self.setStyleSheet("QMainWindow { background: #08090b; }")

    # -- menus ------------------------------------------------------------------
    def _menus(self):
        mb = self.menuBar()

        def act(menu, text, fn, key=None, checkable=False):
            a = QAction(text, self)
            if key:
                a.setShortcut(QKeySequence(key))
            a.setCheckable(checkable)
            a.triggered.connect(fn)
            menu.addAction(a)
            return a

        f = mb.addMenu("File")
        act(f, "New Brief", self._new, "Ctrl+N")
        act(f, "Open…", self._open, "Ctrl+O")
        sm = f.addMenu("Open Sample")
        for key, fn in samples.SAMPLES.items():
            h = fn()
            act(sm, f"{h.name} — {h.stories}-storey, {len(h.bedrooms)} bed", lambda _c=False, fn=fn: self._show_house(fn()))
        f.addSeparator()
        self.a_save = act(f, "Save House Model…", self._save, "Ctrl+S")
        self.a_pdf = act(f, "Export PDF…", self._export_pdf, "Ctrl+E")
        self.a_svg = act(f, "Export Sheets as SVG…", self._export_svg, "Ctrl+Shift+E")

        v = mb.addMenu("View")
        act(v, "Brief", lambda: self.show_view(self.brief), "Ctrl+B")
        self.a_concept = act(v, "Concept", lambda: self.show_view(self.concept), "Ctrl+1")
        self.a_set = act(v, "Drawing Set", self._show_set, "Ctrl+2")
        v.addSeparator()
        rs = v.addMenu("Render Style")
        g = QActionGroup(self)
        for key, label in (("modern", "Modern Lines"), ("blueprint", "Blueprint"), ("patternbook", "1920s Pattern Book")):
            a = act(rs, label, lambda _c=False, k=key: self._style(k), checkable=True)
            a.setChecked(key == self.render_style)
            g.addAction(a)
        ss = v.addMenu("Sheet Set")
        g2 = QActionGroup(self)
        for key, label in (("rough", "Rough (plans, roof, elevations)"), ("full", "Full (adds notes and schedules)")):
            a = act(ss, label, lambda _c=False, k=key: self._set_mode(k), checkable=True)
            a.setChecked(key == self.sheet_set)
            g2.addAction(a)

        d = mb.addMenu("Design")
        act(d, "Draft", self.brief.box._send, "Ctrl+Return")
        act(d, "Improve Brief with AI", self.brief._improve, "Ctrl+I")
        self.a_edit = act(d, "Edit Brief…", self._edit_brief, "Ctrl+K")
        self.a_next = act(d, "Next Option", lambda: self._option(+1), "Ctrl+]")
        self.a_prev = act(d, "Previous Option", lambda: self._option(-1), "Ctrl+[")

        hm = mb.addMenu("Help")
        act(hm, "About Dream Built", self._about)
        self._enable()

    def _enable(self):
        has = self.data is not None
        for a in (self.a_save, self.a_pdf, self.a_svg, self.a_concept, self.a_set, self.a_next, self.a_prev):
            a.setEnabled(has)

    # -- navigation -------------------------------------------------------------
    def show_view(self, w):
        if self.stack.currentWidget() is w:
            return
        self.stack.setCurrentWidget(w)
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        animate(w, 0.0, 1.0, 280, eff.setOpacity, on_done=lambda: w.setGraphicsEffect(None))

    def _new(self):
        self.revising = None
        self.brief.set_revising(None)
        self.brief.box.text.clear()
        self.brief.box.set_photo("")
        self.side.list.clearSelection()
        self.show_view(self.brief)
        self.brief.box.text.setFocus()

    def _show_set(self):
        if not self.data:
            return
        self.sheets.load(self.data, self.render_style, self.concept.opt, self.sheet_set)
        self.show_view(self.sheets)

    # -- drafting ---------------------------------------------------------------
    def _draft(self, text, photo, use_model, base=None, parent=None):
        """Design from a brief. `base` is the brief being changed; `parent` the saved design
        this becomes a new version of."""
        from .. import brief as briefs
        from .. import llm
        parent = parent or self.revising
        ai = use_model and llm.available(str(model_dir()))
        b = briefs.parse_text(text, base)
        probs = [p for p in b.validate() if "style" in p]  # sizes adapt; only nonsense stops
        if probs and not ai and base is None:
            QMessageBox.information(self, "Not quite enough to build", probs[0])
            return
        self.drafting.start(text)
        self.show_view(self.drafting)
        mpath = str(model_dir())

        def job():
            from ..design import options
            notes = []
            if ai and base is not None:
                bb = llm.revise_brief(base, text, mpath)
            elif ai:
                para, bb = llm.improve(text, mpath)
                notes.append(para)
            else:
                bb = b
            briefs.make_sane(bb)
            return {"brief": bb, "options": options(bb, 3), "notes": notes}

        def done(res):
            self.drafting.show_plan(res["options"][0].house)
            from PySide6.QtCore import QTimer
            label = text if base is None else ((parent.text if parent else self.text) + "\n→ " + text)
            QTimer.singleShot(1600, lambda: self._open_concept(res, save=True, text=label, parent=parent))

        def failed(msg):
            self.show_view(self.brief if base is None else self.concept)
            QMessageBox.warning(self, "Couldn't draft that", msg.split("\n")[0])

        worker.run(job, done, failed)

    def _refine(self, text, photo, use_model):
        """A change request on the open design: a new version of it. Requests that name rooms
        ("make Bedroom 3 bigger", "swap the Office and the Dining") edit this design directly;
        anything else goes through the brief."""
        if self.current_brief is None:
            self._draft(text, photo, use_model)
            return
        if self.data and not photo:
            from .. import edit
            ops = edit.parse(text, self.concept.house())
            if ops:
                self._apply_edits(ops, said=text)
                return
            from .. import llm
            if use_model and llm.available(str(model_dir())) and not llm.is_vision(llm.DEFAULT_MODEL):
                # the words didn't name a room: the model picks one of this design's rooms and
                # an action by likelihood; if it isn't sure, the request goes to the brief
                house = self.concept.house()

                def pick():
                    return llm.edit_ops(text, house)

                def picked(found):
                    if found:
                        self._apply_edits(found, said=text)
                    else:
                        import copy
                        self._draft(text, photo, use_model, base=copy.deepcopy(self.current_brief),
                                    parent=self.current_entry)

                worker.run(pick, picked, lambda _m: picked([]))
                return
        import copy
        self._draft(text, photo, use_model, base=copy.deepcopy(self.current_brief), parent=self.current_entry)

    def _apply_edits(self, ops, said: str = ""):
        """Edits on the open option: the same design with those changes, saved as its next version."""
        from .. import edit
        from ..design import Option
        house, brief = self.concept.house(), self.current_brief
        if brief is None:
            return
        parent = self.current_entry
        label = (parent.text if parent else self.text) + "\n→ " + (said or "; ".join(o.describe() for o in ops))

        def job():
            res = edit.apply(house, brief, ops)
            note = ("Done: " + "; ".join(res.done) if res.done else "") + \
                ("   Couldn't: " + "; ".join(res.couldnt) if res.couldnt else "")
            return {"brief": res.brief, "options": [Option(res.house, 0.0, [note])], "notes": [note]}, note

        def done(out):
            data, note = out
            self._open_concept(data, save=True, text=label, parent=parent)
            self.concept.detail.setText(f"<span style='color:#9fc0ff'>{note}</span>")

        worker.run(job, done, lambda msg: QMessageBox.warning(self, "Couldn't make that change", msg.split("\n")[0]))

    def _react(self, liked: bool):
        from ..design import candidates
        from ..design.signature import signature
        candidates.react(signature(self.concept.house()), liked)
        self.concept.detail.setText("<span style='color:#9fc0ff'>" +
                                    ("Liked: new designs will lean this way." if liked else
                                     "Passed: new designs will lean away from this.") + "</span>")

    def _breed(self):
        """Mix the open option with another (the next one, or the only other) into new designs."""
        from ..design import offspring
        opts = self.data["options"] if self.data else []
        if len(opts) < 2 or self.current_brief is None:
            QMessageBox.information(self, "Breed", "Breeding needs two options of the same design.")
            return
        a = self.concept.opt
        c = (a + 1) % len(opts)
        brief, ha, hc = self.current_brief, opts[a].house, opts[c].house
        parent = self.current_entry
        label = (parent.text if parent else self.text) + f"\n→ bred {'ABCDEFGHIJ'[a]} × {'ABCDEFGHIJ'[c]}"
        self.drafting.start(f"Breeding {'ABCDEFGHIJ'[a]} × {'ABCDEFGHIJ'[c]}")
        self.show_view(self.drafting)

        def job():
            kids = offspring(brief, ha, hc, 3)
            if not kids:
                raise RuntimeError("those two are too alike to mix: try two more different options")
            return {"brief": brief, "options": kids, "notes": []}

        def done(res):
            self._open_concept(res, save=True, text=label, parent=parent)

        def failed(msg):
            self.show_view(self.concept)
            QMessageBox.information(self, "Breed", msg.split("\n")[0])

        worker.run(job, done, failed)

    def _edit_brief(self):
        """Revise the open design from its brief, in words: the next draft saves as its next
        version. (The full form is under Details… on the home screen.)"""
        e = self.current_entry
        if e is None:
            self.show_view(self.brief)
            return
        from .. import brief as briefs
        self.revising = e
        nxt = max((x.version for x in history.all_entries() if x.family == e.family), default=1) + 1
        self.brief.set_revising(e.title, nxt, briefs.describe(self.current_brief or e.load_brief()))
        self.show_view(self.brief)
        self.brief.box.text.setFocus()

    def _details(self, text: str):
        """The home screen's "Details…": the brief so far, as a form, before drafting."""
        from .. import brief as briefs
        from .brief_form import BriefForm
        b = briefs.parse_text(text) if text.strip() else briefs.DesignBrief()
        form = BriefForm(b, title="Brief details", action="Draft", parent=self)
        if form.exec():
            nb = form.brief()
            self._draft_brief(nb, text.strip() or briefs.describe(nb))

    def _draft_brief(self, b, label: str, parent=None):
        """Draft straight from a brief (the form): no reading, no model."""
        self.drafting.start(label)
        self.show_view(self.drafting)

        def job():
            from ..design import options
            return {"brief": b, "options": options(b, 3), "notes": []}

        def done(res):
            self.drafting.show_plan(res["options"][0].house)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1200, lambda: self._open_concept(res, save=True, text=label, parent=parent))

        def failed(msg):
            self.show_view(self.concept if parent else self.brief)
            QMessageBox.warning(self, "Couldn't draft that", msg.split("\n")[0])

        worker.run(job, done, failed)

    def _open_concept(self, res, save=False, text=None, parent=None):
        self.data = res
        self.current_brief = res.get("brief")
        self._enable()
        self.concept.load(res)
        if save:
            self.text = text or self.text
            entry = history.save(self.text, res["options"], brief=self.current_brief, parent=parent)
            self.current_entry = entry
            self.revising = None
            self.brief.set_revising(None)
            self.side.refresh(entry.id)
        self.show_view(self.concept)

    def _open_entry(self, entry):
        try:
            opts = entry.load_options()
        except Exception as e:  # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, "Couldn't open that build", str(e))
            return
        self.text = entry.text
        self.current_entry = entry
        self.revising = None
        self.brief.set_revising(None)
        self._open_concept({"options": opts, "brief": entry.load_brief()})

    def _show_house(self, house):
        from ..design import Option
        self.current_entry = None
        self._open_concept({"options": [Option(house, 0, [])]})

    def _option(self, d):
        if self.data:
            self.concept.set_option((self.concept.opt + d) % len(self.data["options"]))

    def _style(self, key):
        self.render_style = key
        if self.stack.currentWidget() is self.sheets:
            self._show_set()

    def _set_mode(self, key):
        self.sheet_set = key
        if self.stack.currentWidget() is self.sheets:
            self._show_set()

    # -- files ------------------------------------------------------------------
    def _house(self):
        return self.data["options"][self.concept.opt].house

    def _slug(self):
        return "".join(c if c.isalnum() else "-" for c in self._house().name.lower()).strip("-")

    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open a house or brief", str(Path.home()),
                                              "House or brief (*.json *.yaml *.yml)")
        if not path:
            return
        import yaml
        from .. import brief as briefs
        from ..model import from_dict
        try:
            data = yaml.safe_load(open(path))
            if briefs.is_brief(data):
                b = briefs.from_dict(data)
                self.brief.box.text.setPlainText(b.summary().replace("; must-haves:", ", with").replace("none", ""))
                self.show_view(self.brief)
            else:
                self._show_house(from_dict(data))
        except Exception as e:  # noqa: BLE001 - shown to the user
            QMessageBox.warning(self, "Couldn't open that file", str(e))

    def _save(self):
        from ..model import save
        path, _ = QFileDialog.getSaveFileName(self, "Save house model", f"{self._slug()}.json",
                                              "House model (*.json *.yaml)")
        if path:
            save(self._house(), path)

    def _export_pdf(self):
        from .. import render_pdf
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", f"{self._slug()}-{self.render_style}.pdf", "PDF (*.pdf)")
        if path:
            h, st, mode = self._house(), self.render_style, self.sheet_set
            worker.run(lambda: render_pdf(h, path, style=st, mode=mode), lambda _p: None)

    def _export_svg(self):
        from .. import render_svgs
        folder = QFileDialog.getExistingDirectory(self, "Export sheets to folder")
        if folder:
            h, st, mode = self._house(), self.render_style, self.sheet_set
            worker.run(lambda: render_svgs(h, folder, style=st, mode=mode), lambda _p: None)

    def _about(self):
        QMessageBox.about(self, "Dream Built", "Dream Built — offline house concepts.\n"
                          "Describe a house; get plans, roof and elevations.\n"
                          "Concept drawings only, not for construction.")


def run(argv=None) -> int:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("Dream Built")
    app.setApplicationDisplayName("Dream Built")
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
