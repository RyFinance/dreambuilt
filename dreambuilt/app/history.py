"""Every build is kept on this Mac so the sidebar can bring it back."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from ..model import from_dict, to_dict


def folder() -> Path:
    import os
    if os.environ.get("DREAMBUILT_HISTORY"):
        p = Path(os.environ["DREAMBUILT_HISTORY"])
        p.mkdir(parents=True, exist_ok=True)
        return p
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    p = Path(base or Path.home() / ".dreambuilt") / "history"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Entry:
    id: str
    title: str
    text: str
    created: float
    path: Path
    root: str = ""  # the first version's id; "" means this entry is the first
    version: int = 1
    brief: dict | None = None  # the exact brief the design was made from

    def load_options(self):
        from ..design import Option
        from .. import edit
        data = json.loads(self.path.read_text())
        houses = [from_dict(h) for h in data["houses"]]
        for h in houses:
            if not any(r.title for lv in h.all_levels for r in lv.rooms):
                edit.assign_titles(h)  # (saved before rooms had titles)
        return [Option(h, 0.0, []) for h in houses]

    def load_brief(self):
        from .. import brief as briefs
        if self.brief:
            b = briefs.DesignBrief()
            for k, v in self.brief.items():
                if hasattr(b, k):
                    setattr(b, k, v)
            return b
        return briefs.parse_text(self.text)

    @property
    def family(self) -> str:
        return self.root or self.id


def save(text: str, options, brief=None, parent: "Entry | None" = None) -> Entry:
    """Save a build. With `parent`, it's the next version of that design."""
    from dataclasses import asdict
    eid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    h = options[0].house
    root = parent.family if parent else ""
    version = (max((e.version for e in all_entries() if e.family == root), default=1) + 1) if parent else 1
    title = parent.title if parent else (text.strip().split("\n")[0][:60] or h.name)
    path = folder() / f"{eid}.json"
    bd = asdict(brief) if brief is not None else None
    path.write_text(json.dumps({"id": eid, "title": title, "text": text, "created": time.time(),
                                "root": root, "version": version, "brief": bd,
                                "houses": [to_dict(o.house) for o in options]}))
    return Entry(eid, title, text, time.time(), path, root, version, bd)


def all_entries() -> list[Entry]:
    out = []
    for p in sorted(folder().glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text())
            out.append(Entry(d["id"], d["title"], d.get("text", ""), d.get("created", 0), p,
                             d.get("root", ""), d.get("version", 1), d.get("brief")))
        except (OSError, ValueError, KeyError):
            continue
    return out


def grouped() -> list[tuple[Entry, list[Entry]]]:
    """Designs newest-first, each with its later versions (newest first)."""
    entries = all_entries()
    roots = [e for e in entries if not e.root]
    out = []
    for r in roots:
        kids = sorted([e for e in entries if e.root == r.id], key=lambda e: -e.version)
        out.append((r, kids))
    # a design's position follows its newest version
    out.sort(key=lambda rk: -max([rk[0].created] + [k.created for k in rk[1]]))
    return out


def delete(entry: Entry) -> None:
    entry.path.unlink(missing_ok=True)
