"""Snapshot tests: every sheet of the sample in every render style.

Regenerate after an intended drawing change with:
    DREAMBUILT_UPDATE_SNAPSHOTS=1 pytest tests/test_snapshots.py
"""
import os
from pathlib import Path

import pytest

from dreambuilt.render import themes
from dreambuilt.render.backends import sheet_to_svg
from dreambuilt.samples import SAMPLES
from dreambuilt.sheets.build import build_set

SNAP = Path(__file__).parent / "snapshots"
UPDATE = os.environ.get("DREAMBUILT_UPDATE_SNAPSHOTS") == "1"


CASES = [("ashbury", "full", 10), ("halsted", "rough", 10)]


@pytest.mark.parametrize("style", sorted(themes.THEMES))
@pytest.mark.parametrize("sample,mode,pages", CASES)
def test_sheets_match_snapshots(style, sample, mode, pages):
    theme = themes.get(style)
    sheets = build_set(SAMPLES[sample](), theme, date="2026-01-01", mode=mode)
    assert len(sheets) == pages
    folder = SNAP / f"{sample}-{mode}" / style
    for sh in sheets:
        svg = sheet_to_svg(sh, theme)
        path = folder / f"{sh.number.replace('.', '_')}.svg"
        if UPDATE or not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(svg)
            continue
        assert svg == path.read_text(), f"{style} {sh.number} changed; review and update snapshots"


def test_rough_set_is_brief_plans_roof_elevations():
    from dreambuilt.sheets.build import SetBuilder
    numbers = [n for n, _ in SetBuilder(SAMPLES["halsted"](), themes.get("modern")).index()]
    assert numbers == ["A0.0", "A1.1", "A2.1", "A2.2", "A2.3", "A3.1",
                       "A4.1", "A4.2", "A4.3", "A4.4"]


def test_pdf_written(tmp_path):
    from dreambuilt import render_pdf
    p = render_pdf(SAMPLES["halsted"](), tmp_path / "h.pdf", date="2026-01-01")
    assert p.read_bytes().startswith(b"%PDF")
