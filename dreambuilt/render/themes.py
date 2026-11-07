"""Render styles: the same drawing items, three looks.

modern      - crisp black linework on white, sans-serif
blueprint   - white lines on cyanotype blue, hatched walls, block capitals
patternbook - sepia ink on cream stock, serif type, ornamental borders (1920s catalogue)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stroke:
    color: str
    width: float  # points
    dash: tuple[float, ...] = ()


@dataclass
class Theme:
    name: str
    label: str
    bg: str
    ink: str
    strokes: dict[str, Stroke]
    fills: dict[str, str]
    fonts: dict[str, str]  # role -> ReportLab base-14 font name
    wall_fill: str = "solid"  # solid | hatch
    hatches: dict[str, bool] = field(default_factory=dict)  # which elevation hatches to draw
    border: str = "single"  # single | double | ornate
    upper: bool = False  # set titles in capitals
    title_spacing: float = 0.0
    grid: str = ""  # faint sheet grid colour, "" for none

    def stroke(self, role: str) -> Stroke:
        if role == "grid":
            return Stroke(self.grid or self.bg, 0.25)
        return self.strokes.get(role) or self.strokes["outline"]

    def fill(self, role: str) -> str:
        return self.fills.get(role, self.ink)


def _strokes(ink: str, soft: str, faint: str, scale: float = 1.0) -> dict[str, Stroke]:
    s = scale
    return {
        "outline": Stroke(ink, 0.7 * s),
        "heavy": Stroke(ink, 1.6 * s),
        "grade": Stroke(ink, 2.2 * s),
        "cut": Stroke(ink, 1.1 * s),
        "thin": Stroke(ink, 0.45 * s),
        "fixture": Stroke(ink, 0.45 * s),
        "detail": Stroke(soft, 0.35 * s),
        "hatch": Stroke(faint, 0.3 * s),
        "dim": Stroke(ink, 0.35 * s),
        "hidden": Stroke(ink, 0.45 * s, (3, 2)),
        "eave": Stroke(soft, 0.45 * s, (5, 3)),
        "lot": Stroke(ink, 0.9 * s, (12, 3, 2, 3)),
        "setback": Stroke(soft, 0.5 * s, (4, 3)),
        "frame": Stroke(ink, 1.4 * s),
        "rule": Stroke(ink, 0.5 * s),
        "glass": Stroke(ink, 0.35 * s),
        "ridge": Stroke(ink, 0.9 * s),
        "text": Stroke(ink, 0.0),
        "none": Stroke(ink, 0.0),
    }


MODERN = Theme(
    name="modern", label="Modern lines", bg="#ffffff", ink="#1b1b1b",
    strokes=_strokes("#1b1b1b", "#555555", "#9b9b9b"),
    fills={"poche": "#2d2d2d", "footprint": "#d9d9d9", "tone": "#efefef", "paper": "#ffffff",
           "ink": "#1b1b1b", "accent": "#c8553d", "glass": "#e8eef2", "roof": "#f2f2f2"},
    fonts={"title": "Helvetica-Bold", "body": "Helvetica", "label": "Helvetica",
           "italic": "Helvetica-Oblique"},
    wall_fill="solid",
    hatches={"lap": True, "shingle": True, "brick": True, "lattice": True, "roofing": False,
             "clapboard": True, "board-and-batten": True, "wood": True, "seam": True, "tile": True, "timber": True},
    border="single",
)

BLUEPRINT = Theme(
    name="blueprint", label="Blueprint", bg="#174a8b", ink="#eef4ff",
    strokes=_strokes("#eef4ff", "#c4d7f5", "#8fb0e0", 1.05),
    fills={"poche": "#eef4ff", "footprint": "#2d63a8", "tone": "#1f5699", "paper": "#174a8b",
           "ink": "#eef4ff", "accent": "#ffffff", "glass": "#2a5f9f", "roof": "#1d5294"},
    fonts={"title": "Helvetica-Bold", "body": "Helvetica-Bold", "label": "Helvetica-Bold",
           "italic": "Helvetica-BoldOblique"},
    wall_fill="hatch",
    hatches={"lap": True, "shingle": True, "brick": True, "lattice": True, "roofing": True,
             "clapboard": True, "board-and-batten": True, "wood": True, "seam": True, "tile": True, "timber": True},
    border="double", upper=True, title_spacing=1.5, grid="#21579a",
)

PATTERNBOOK = Theme(
    name="patternbook", label="1920s pattern book", bg="#f2e8cf", ink="#3b2816",
    strokes=_strokes("#3b2816", "#5c4630", "#8a7354", 0.95),
    fills={"poche": "#3b2816", "footprint": "#d8c7a0", "tone": "#e8dbbb", "paper": "#f2e8cf",
           "ink": "#3b2816", "accent": "#8c2f1b", "glass": "#e3d6b4", "roof": "#e6d8b6"},
    fonts={"title": "Times-Bold", "body": "Times-Roman", "label": "Times-Italic",
           "italic": "Times-Italic"},
    wall_fill="solid",
    hatches={"lap": True, "shingle": True, "brick": True, "lattice": True, "roofing": True,
             "clapboard": True, "board-and-batten": True, "wood": True, "seam": True, "tile": True, "timber": True},
    border="ornate", upper=True, title_spacing=2.5,
)

NOIR = Theme(
    name="noir", label="Noir (app)", bg="#000000", ink="#f1f1ef",
    strokes=_strokes("#f1f1ef", "#a9abad", "#4a4c4f"),
    fills={"poche": "#f1f1ef", "footprint": "#1c1c1c", "tone": "#151515", "paper": "#000000",
           "ink": "#f1f1ef", "accent": "#f1f1ef", "glass": "#1f3346", "roof": "#141414"},
    fonts={"title": "Helvetica-Bold", "body": "Helvetica", "label": "Helvetica",
           "italic": "Helvetica-Oblique"},
    wall_fill="solid",
    hatches={"lap": True, "shingle": True, "brick": True, "lattice": True, "roofing": False,
             "clapboard": True, "board-and-batten": True, "wood": True, "seam": True, "tile": True, "timber": True},
    border="single",
)

THEMES = {t.name: t for t in (MODERN, BLUEPRINT, PATTERNBOOK)}
APP_THEMES = {"noir": NOIR}


def get(name: str) -> Theme:
    key = name.lower().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {"modernlines": "modern", "1920s": "patternbook", "pattern": "patternbook"}
    key = aliases.get(key, key)
    if key in APP_THEMES:
        return APP_THEMES[key]
    if key not in THEMES:
        raise KeyError(f"unknown render style {name!r}; have {sorted(THEMES)}")
    return THEMES[key]
