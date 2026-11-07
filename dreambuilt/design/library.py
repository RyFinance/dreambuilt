"""Real floor plans as starting layouts (CubiCasa5K, built locally by
tools/build_plan_library.py; CC BY-NC-SA 4.0, never shipped). A brief picks plans with its
bedroom count and a similar size; each is scaled to the brief, its rooms named the way the
rest of the designer expects, and then goes through the same doors / windows / rules / roof
pipeline as a generated plan. Plans that break a rule simply lose."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ..model import Room

PATH = Path(__file__).resolve().parents[2] / "data" / "raw" / "cubicasa5k" / "library.json"


@lru_cache(maxsize=1)
def plans() -> list[dict]:
    if not PATH.exists():
        return []
    return json.loads(PATH.read_text())


def candidates(beds: int, sqft: float, stories: int, n: int = 3, seed: int = 0) -> list[dict]:
    """Single-floor plans (for a one-storey) with the brief's bedrooms, close in size."""
    if stories != 1:
        return []
    out = []
    for p in plans():
        if len(p["floors"]) != 1 or p["beds"] != beds or p["sqft"] < 300:
            continue
        kinds = {r[0] for r in p["floors"][0]}
        if not {"kitchen", "living", "bath", "entry"} <= kinds:
            continue
        s = math.sqrt(sqft / p["sqft"])
        if not 0.85 <= s <= 1.7:
            continue
        out.append((abs(math.log(s)), p))
    out.sort(key=lambda t: t[0])
    pool = [p for _, p in out[:max(n * 4, 12)]]
    # rotate through the closest plans so different briefs get different houses
    if not pool:
        return []
    k = seed % len(pool)
    return (pool[k:] + pool[:k])[:n]


def rooms_for(plan: dict, sqft: float, mirror: bool = False) -> Optional[list[Room]]:
    """The plan scaled to the brief's area and snapped to a 6" grid, with rooms named."""
    rects = plan["floors"][0]
    s = math.sqrt(sqft / plan["sqft"])
    W = max(r[3] for r in rects) * s
    snap = lambda v: round(v * 2) / 2
    rooms = []
    for k, x0, y0, x1, y1 in rects:
        a, b, c, d = snap(x0 * s), snap(y0 * s), snap(x1 * s), snap(y1 * s)
        if mirror:
            a, c = snap(W - c), snap(W - a)
        if c - a < 2.0 or d - b < 2.0:
            return None
        rooms.append([k, a, b, c, d])
    named = _name(rooms)
    named_pairs = [(named[i], named[j]) for i, j in plan.get("doors", [[]])[0]
                   if i < len(named) and j < len(named)]
    return named, named_pairs


KIND = {"room": "office", "mech": "closet", "hall": "hall", "entry": "entry"}


def _name(rects) -> list[Room]:
    beds = sorted([r for r in rects if r[0] == "bedroom"], key=lambda r: -(r[3] - r[1]) * (r[4] - r[2]))
    rooms: list[Room] = []
    counts: dict[str, int] = {}

    def area(r):
        return (r[3] - r[1]) * (r[4] - r[2])

    for r in rects:
        k = r[0]
        kind = KIND.get(k, k)
        if k == "bedroom":
            i = beds.index(r)
            name = "Primary Bedroom" if i == 0 else f"Bedroom {i + 1}"
        elif k == "living":
            counts["living"] = counts.get("living", 0) + 1
            name = "Living" if counts["living"] == 1 else ("Dining" if counts["living"] == 2 else "Family Room")
            kind = "living" if counts["living"] == 1 else ("dining" if counts["living"] == 2 else "family")
        elif k == "room":
            name = "Den" if area(r) >= 70 else "Storage"
            kind = "office" if area(r) >= 70 else "closet"
        elif k == "mech":
            name = "Mechanical"
        elif k == "entry":
            counts["entry"] = counts.get("entry", 0) + 1
            name = "Entry" if counts["entry"] == 1 else "Hall"
            kind = "entry" if counts["entry"] == 1 else "hall"
        else:
            counts[k] = counts.get(k, 0) + 1
            base = {"kitchen": "Kitchen", "bath": "Bath", "closet": "Closet", "laundry": "Laundry",
                    "dining": "Dining", "garage": "2-Car Garage", "office": "Office", "hall": "Hall",
                    "stair": "Stair"}.get(k, k.title())
            name = base if counts[k] == 1 else f"{base} {counts[k]}"
        rooms.append(Room(name, kind, r[1], r[2], r[3] - r[1], r[4] - r[2]))
    return _repair(rooms)


def _touch(a: Room, b: Room) -> bool:
    from .details import shared_edge
    e = shared_edge(a, b)
    return bool(e) and e[3] - e[2] >= 2.6


def _repair(rooms: list[Room]) -> list[Room]:
    """Bring a real plan up to the house rules: the primary gets an ensuite and a walk-in
    (the bath beside it, or carved from it), baths that only touch a bedroom become that
    bedroom's ensuite, wide corridors become galleries."""
    beds = [r for r in rooms if r.kind == "bedroom"]
    prim = next((r for r in beds if r.name == "Primary Bedroom"), None)
    baths = [r for r in rooms if r.kind == "bath"]
    circulation = {"hall", "entry", "living", "family", "dining", "stair"}
    if prim is not None:
        ens = next((r for r in baths if _touch(r, prim)), None)
        if ens is not None and len(baths) > 1:
            ens.name = "Primary Ensuite"
        elif max(prim.w, prim.h) >= 15 and min(prim.w, prim.h) >= 11:
            # carve an ensuite (and a walk-in) off the primary's far end
            long_x = prim.w >= prim.h
            t = 6.0
            if long_x:
                strip = Room("Primary Ensuite", "bath", prim.x + prim.w - t, prim.y, t, prim.h)
                prim.w -= t
            else:
                strip = Room("Primary Ensuite", "bath", prim.x, prim.y + prim.h - t, prim.w, t)
                prim.h -= t
            if max(strip.w, strip.h) >= 11:  # split it: ensuite and walk-in side by side
                if long_x:
                    half = round(strip.h * 0.55 * 2) / 2
                    wic = Room("Walk-in Closet", "closet", strip.x, strip.y + half, strip.w, strip.h - half)
                    strip.h = half
                else:
                    half = round(strip.w * 0.55 * 2) / 2
                    wic = Room("Walk-in Closet", "closet", strip.x + half, strip.y, strip.w - half, strip.h)
                    strip.w = half
                rooms.append(wic)
            rooms.append(strip)
        if not any(r.name == "Walk-in Closet" for r in rooms):
            wic = next((r for r in rooms if r.kind == "closet" and _touch(r, prim)), None)
            if wic is not None:
                wic.name = "Walk-in Closet"
    # a bath that touches no circulation, only a bedroom, is that bedroom's ensuite
    for bth in [r for r in rooms if r.kind == "bath" and not r.name.startswith("Primary")]:
        if any(_touch(bth, o) for o in rooms if o.kind in circulation):
            continue
        owner = next((b for b in beds if _touch(bth, b)), None)
        if owner is not None:
            bth.name = "Primary Ensuite" if owner is prim else f"Ensuite {owner.name.split()[-1]}"
    for r in rooms:
        if r.kind == "hall" and min(r.w, r.h) > 6.5:
            r.name = "Gallery"
    return rooms
