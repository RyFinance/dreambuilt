"""The whole brief as a form: everything the designer reads, editable before drafting or when
revising a design. Opened from the home screen ("Details…") and from "Edit brief"."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import brief as briefs
from .. import styles

QSS = """
QDialog, QWidget#body { background: #0c0d10; }
QLabel { color: rgba(241,241,239,0.75); font-family: 'Avenir Next'; font-size: 13px; }
QLabel#head { color: #f1f1ef; font-size: 22px; font-weight: 500; }
QLabel#section { color: rgba(241,241,239,0.45); font-family: Menlo; font-size: 10.5px; letter-spacing: 2px; padding-top: 14px; }
QLabel#hint { color: rgba(241,241,239,0.4); font-size: 11.5px; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit {
    color: #f1f1ef; background: #16181d; border: 1px solid rgba(241,241,239,0.12); border-radius: 8px;
    padding: 5px 8px; font-family: 'Avenir Next'; font-size: 13px; selection-background-color: #2b3a52; }
QCheckBox { color: rgba(241,241,239,0.8); font-family: 'Avenir Next'; font-size: 13px; spacing: 7px; }
QPushButton { color: #0c0d10; background: #f1f1ef; border: none; border-radius: 15px; padding: 7px 20px;
    font-family: 'Avenir Next'; font-size: 13px; font-weight: 600; }
QPushButton#ghost { color: rgba(241,241,239,0.7); background: transparent; border: 1px solid rgba(241,241,239,0.18); }
QScrollArea { border: none; background: transparent; }
"""

GARAGE = [("auto", "Whatever suits the house"), ("front", "Out front"), ("side", "On the side"), ("none", "No garage")]
PRIMARY = [("auto", "Wherever it fits best"), ("main", "Main floor"), ("upper", "Upstairs")]


class BriefForm(QDialog):
    def __init__(self, b: briefs.DesignBrief, title: str = "Brief", action: str = "Draft", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setStyleSheet(QSS)
        self.resize(720, 820)
        self.b = copy.deepcopy(b)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 22, 26, 18)
        head = QLabel(title)
        head.setObjectName("head")
        outer.addWidget(head)
        hint = QLabel("Everything the designer reads. Change anything; what isn't drawable yet stays in the notes.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName("body")
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 8, 0)

        def section(text):
            s = QLabel(text.upper())
            s.setObjectName("section")
            lay.addWidget(s)
            f = QFormLayout()
            f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            f.setHorizontalSpacing(18)
            f.setVerticalSpacing(8)
            lay.addLayout(f)
            return f

        # the house
        f = section("The house")
        self.style_ = QComboBox()
        for key in styles.available():
            self.style_.addItem(styles.get(key)["name"], key)
        self.style_.setCurrentIndex(max(0, self.style_.findData(b.style)))
        f.addRow("Style", self.style_)
        self.stories = self._spin(1, 3, b.stories)
        f.addRow("Storeys above ground", self.stories)
        self.beds = self._spin(1, 7, b.beds)
        f.addRow("Bedrooms", self.beds)
        self.baths = QDoubleSpinBox()
        self.baths.setRange(1, 8)
        self.baths.setSingleStep(0.5)
        self.baths.setDecimals(1)
        self.baths.setValue(b.baths)
        f.addRow("Bathrooms (.5 = powder)", self.baths)
        self.sqft = self._spin(300, 8000, b.sqft, step=50, suffix=" sq ft")
        f.addRow("Total size", self.sqft)
        self.ceiling = QDoubleSpinBox()
        self.ceiling.setRange(0, 20)
        self.ceiling.setSingleStep(0.5)
        self.ceiling.setSpecialValueText("The style's")
        self.ceiling.setValue(b.ceiling)
        self.ceiling.setSuffix(" ft")
        f.addRow("Main-floor ceilings", self.ceiling)

        # the lot
        f = section("The lot")
        row = QHBoxLayout()
        self.lot_w = self._spin(10, 400, int(b.lot_width), suffix=" ft wide")
        self.lot_d = self._spin(10, 600, int(b.lot_depth), suffix=" ft deep")
        row.addWidget(self.lot_w)
        row.addWidget(self.lot_d)
        f.addRow("Lot", row)
        self.strict = QCheckBox("Keep the lot exactly as given (never assume more land)")
        self.strict.setChecked("strict lot" in b.features)
        f.addRow("", self.strict)
        self.town = QCheckBox("Townhouse / infill (zero side setbacks)")
        self.town.setChecked("townhouse" in b.features)
        f.addRow("", self.town)

        # layout
        f = section("Layout")
        self.primary = self._combo(PRIMARY, b.primary_floor)
        f.addRow("Primary bedroom", self.primary)
        self.garage = self._combo(GARAGE, b.garage)
        f.addRow("Garage", self.garage)
        self.cars = self._spin(0, 3, b.cars, special="As many as fit")
        f.addRow("Garage spaces", self.cars)
        self.basement = QCheckBox("Basement")
        self.basement.setChecked(b.basement)
        f.addRow("", self.basement)
        self.suites = QLineEdit(", ".join(str(n) for n in b.suites))
        self.suites.setPlaceholderText("bedrooms in each rental suite, e.g. 2, 1")
        f.addRow("Rental suites", self.suites)
        self.places = QLineEdit(", ".join(p.replace(":", " at the ") for p in b.places))
        self.places.setPlaceholderText("e.g. kitchen at the rear, office at the front")
        f.addRow("Where rooms go", self.places)

        # rooms and features
        s = QLabel("ROOMS AND FEATURES")
        s.setObjectName("section")
        lay.addWidget(s)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        self.checks = {}
        keys = [("must", k) for k in briefs.MUST_HAVES] + \
            [("feat", k) for k in briefs.FEATURES if k not in ("no garage", "3-car garage", "strict lot", "townhouse")]
        for i, (kind, k) in enumerate(keys):
            c = QCheckBox(k)
            c.setChecked(k in (b.must_haves if kind == "must" else b.features))
            grid.addWidget(c, i // 3, i % 3)
            self.checks[(kind, k)] = c
        lay.addLayout(grid)

        # the small things and anything else
        f = section("The small things")
        self.wishes = QPlainTextEdit("\n".join(b.wishes))
        self.wishes.setPlaceholderText("Finishes, colours, lighting, built-ins… one per line. They go on the drawings' notes.")
        self.wishes.setFixedHeight(110)
        f.addRow(self.wishes)
        f = section("Not drawn yet")
        self.notes = QPlainTextEdit("\n".join(b.notes))
        self.notes.setPlaceholderText("Asks the designer can't draw yet are listed here so nothing is lost.")
        self.notes.setFixedHeight(80)
        f.addRow(self.notes)
        lay.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(action)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        outer.addLayout(btns)

    def _spin(self, lo, hi, v, step=1, suffix="", special=""):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(int(v))
        if suffix:
            s.setSuffix(suffix)
        if special:
            s.setSpecialValueText(special)
        return s

    def _combo(self, items, current):
        c = QComboBox()
        for key, label in items:
            c.addItem(label, key)
        c.setCurrentIndex(max(0, c.findData(current)))
        return c

    def brief(self) -> briefs.DesignBrief:
        b = self.b
        b.style = self.style_.currentData()
        b.stories = self.stories.value()
        b.beds = self.beds.value()
        b.baths = self.baths.value()
        b.sqft = self.sqft.value()
        b.ceiling = self.ceiling.value()
        b.lot_width, b.lot_depth = float(self.lot_w.value()), float(self.lot_d.value())
        b.primary_floor = self.primary.currentData()
        b.garage = self.garage.currentData()
        b.cars = self.cars.value()
        b.basement = self.basement.isChecked()
        b.suites = [int(x) for x in self.suites.text().replace(" ", "").split(",") if x.isdigit()][:2]
        b.basement = b.basement or bool(b.suites)
        b.must_haves = sorted(k for (kind, k), c in self.checks.items() if kind == "must" and c.isChecked())
        feats = {k for (kind, k), c in self.checks.items() if kind == "feat" and c.isChecked()}
        if self.strict.isChecked():
            feats.add("strict lot")
        if self.town.isChecked():
            feats.add("townhouse")
        b.features = sorted(feats)
        b.places = briefs.read_places(" " + self.places.text().lower() + " ")
        b.wishes = [x.strip() for x in self.wishes.toPlainText().splitlines() if x.strip()]
        b.notes = [x.strip() for x in self.notes.toPlainText().splitlines() if x.strip()]
        return briefs.sync_garage(b)
