"""Dream Built: offline house concept generator.

    import dreambuilt
    house = dreambuilt.samples.ashbury()
    dreambuilt.render_pdf(house, "ashbury.pdf", style="patternbook")
"""
from __future__ import annotations

from pathlib import Path

from . import checks, samples, styles
from .model import House, load, save
from .render import themes
from .render.backends import write_pdf, write_svgs
from .sheets.build import build_set

__version__ = "0.1.0"


def render_pdf(house: House, path: str | Path, style: str = "modern",
               date: str | None = None, mode: str = "rough") -> Path:
    """Write the concept set as one 11x17 PDF.

    mode "rough": cover & brief, site, one plan per story, roof, four elevations.
    mode "full": adds legend & notes and schedules.
    """
    theme = themes.get(style)
    return write_pdf(build_set(house, theme, date, mode), theme, path, title=house.name)


def render_svgs(house: House, folder: str | Path, style: str = "modern",
                date: str | None = None, mode: str = "rough") -> list[Path]:
    """Write one SVG per sheet into `folder`."""
    theme = themes.get(style)
    return write_svgs(build_set(house, theme, date, mode), theme, folder)


__all__ = ["House", "checks", "load", "render_pdf", "render_svgs", "samples", "save", "styles",
           "themes", "__version__"]
