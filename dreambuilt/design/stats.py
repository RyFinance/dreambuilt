"""What real floor plans look like, mined from CubiCasa5K (aggregate numbers only; see
tools/mine_cubicasa.py). Used to score layouts: rooms shaped and sized like real ones, next
to the rooms they usually sit beside, win."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "data" / "plan_stats.json"

# our room kinds -> the dataset's
ALIAS = {"family": "living", "spice": "kitchen", "powder": "bath", "mud": "entry", "pantry": "closet",
         "laundry": "laundry", "stair": None, "void": None, "garage": "garage"}


@lru_cache(maxsize=1)
def load() -> dict:
    if not PATH.exists():
        return {}
    return json.loads(PATH.read_text())


def kind(k: str):
    return ALIAS.get(k, k)


def aspect_limit(k: str, default: float) -> float:
    """The 90th-percentile long:short ratio real rooms of this kind have."""
    r = load().get("rooms", {}).get(kind(k) or "", {})
    return r.get("aspect", {}).get("p90", default)


def adjacency(a: str, b: str):
    """How often two kinds of room touch in real plans that have both (None: unknown)."""
    ka, kb = kind(a), kind(b)
    if not ka or not kb:
        return None
    key = "|".join(sorted((ka, kb)))
    return load().get("adjacency", {}).get(key)


def layout_penalty(levels) -> tuple[float, list[str]]:
    """Points against a plan for rooms proportioned unlike real ones, and for neighbours
    real plans rarely have (a kitchen against a bedroom, a bath opening to the living)."""
    from .details import shared_edge
    data = load()
    if not data:
        return 0.0, []
    s, notes = 0.0, []
    for lv in levels:
        rooms = [r for r in lv.rooms if not r.unit and r.kind not in ("void", "stair", "hall")]
        for r in rooms:
            if r.kind in ("closet",):
                continue
            lim = aspect_limit(r.kind, 0)
            if lim:
                lo, hi = sorted((r.w, r.h))
                ratio = hi / max(lo, 0.1)
                if ratio > lim * 1.1:
                    s += 6 * (ratio - lim)
        for i, a in enumerate(rooms):
            for b in rooms[i + 1:]:
                e = shared_edge(a, b)
                if not e or e[3] - e[2] < 2.5:
                    continue
                if "closet" in (a.kind, b.kind) or kind(a.kind) == kind(b.kind) and a.kind != b.kind:
                    continue  # pantries, linens and spice kitchens sit where they're meant to
                if "garage" in (a.kind, b.kind):
                    continue  # (the plans behind these numbers are apartments: no garages to learn from)
                f = adjacency(a.kind, b.kind)
                if f is not None and f < 0.2:
                    s += 4
                    notes.append(f"{a.name} next to {b.name} is unusual in real plans")
    return s, notes
