"""Mine room statistics from CubiCasa5K (read straight from the zip, never unpacked).

    python tools/mine_cubicasa.py data/raw/cubicasa5k/svg dreambuilt/data/plan_stats.json

The raw data is CC BY-NC-SA 4.0 (Kalervo et al., CubiCasa5K, 2019) and stays out of the
repository; only aggregate numbers (size and proportion percentiles, how often room types
sit next to each other, how the biggest bedroom compares) are written out.

Scale: plans have no stated scale, so each one is calibrated on its own doors (a typical
interior door is 0.85 m)."""
from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from statistics import median

from shapely.geometry import Polygon
from shapely.ops import unary_union

KIND = {
    "Bedroom": "bedroom", "LivingRoom": "living", "Kitchen": "kitchen", "Bath": "bath",
    "Sauna": "bath", "Entry": "entry", "Lobby": "entry", "Hall": "hall", "Corridor": "hall",
    "Storage": "closet", "Closet": "closet", "Garage": "garage", "DraughtLobby": "entry",
    "Dining": "dining", "Utility": "laundry", "Laundry": "laundry", "Room": "room",
    "Office": "office", "TechnicalRoom": "mech",
}
SQFT = 10.7639
PT = re.compile(r"-?\d+(?:\.\d+)?")


def _poly(points: str):
    nums = [float(v) for v in PT.findall(points)]
    pts = list(zip(nums[0::2], nums[1::2]))
    if len(pts) < 3:
        return None
    p = Polygon(pts)
    return p if p.is_valid and p.area > 1 else p.buffer(0)


def parse(svg: str):
    """Floors of one plan: [(rooms [(kind, polygon)], door widths px)]."""
    floors = []
    parts = re.split(r'<g[^>]*class="Floorplan Floor-\d+"[^>]*>', svg)[1:] or [svg]
    for part in parts:
        rooms, doors = [], []
        for m in re.finditer(r'class="Space ([A-Za-z]+)[^"]*"[^>]*>\s*<polygon[^>]*points="([^"]+)"', part):
            kind = KIND.get(m.group(1))
            if kind:
                p = _poly(m.group(2))
                if p is not None and not p.is_empty and p.area > 1:
                    rooms.append((kind, p))
        for m in re.finditer(r'class="Door[^"]*"[^>]*>\s*<polygon[^>]*points="([^"]+)"', part):
            p = _poly(m.group(1))
            if p is not None and not p.is_empty:
                minx, miny, maxx, maxy = p.bounds
                doors.append(max(maxx - minx, maxy - miny))
        floors.append((rooms, doors))
    return floors


def aspect(p) -> float:
    r = p.minimum_rotated_rectangle
    xs = list(r.exterior.coords)
    a = ((xs[0][0] - xs[1][0]) ** 2 + (xs[0][1] - xs[1][1]) ** 2) ** 0.5
    b = ((xs[1][0] - xs[2][0]) ** 2 + (xs[1][1] - xs[2][1]) ** 2) ** 0.5
    return max(a, b) / max(min(a, b), 1e-6), min(a, b)


def pct(vals, qs=(10, 25, 50, 75, 90)):
    v = sorted(vals)
    if not v:
        return {}
    return {f"p{q}": round(v[min(len(v) - 1, int(len(v) * q / 100))], 2) for q in qs}


def main(zip_path: str, out_path: str):
    import glob
    import os
    if zip_path.endswith(".zip"):
        z = zipfile.ZipFile(zip_path)
        svgs = [n for n in z.namelist() if n.endswith("model.svg")]
    else:
        z = None
        svgs = sorted(glob.glob(os.path.join(zip_path, "*.svg")))
    area = defaultdict(list)
    ratio = defaultdict(list)
    width = defaultdict(list)
    share = defaultdict(list)
    adj = Counter()
    pair_seen = Counter()
    kinds_seen = Counter()
    plans = 0
    homes_big = 0
    primary_biggest_ratio = []
    bed_counts = Counter()
    files = svgs
    for n in files:
        try:
            floors = parse(open(n).read() if not zip_path.endswith(".zip") else z.read(n).decode("utf-8", "ignore"))
        except Exception:
            continue
        doors = [d for _, ds in floors for d in ds]
        rooms_all = [r for rs, _ in floors for r in rs]
        if len(rooms_all) < 4 or len(doors) < 3:
            continue
        px_per_m = median(doors) / 0.85
        if not 20 < px_per_m < 400:
            continue
        m2 = lambda p: p.area / px_per_m ** 2
        total = sum(m2(p) for k, p in rooms_all if k != "garage")
        if not 25 < total < 600:
            continue
        plans += 1
        present = Counter(k for k, _ in rooms_all)
        for k in present:
            kinds_seen[k] += 1
        beds = []
        for k, p in rooms_all:
            a = m2(p) * SQFT
            r, w = aspect(p)
            area[k].append(a)
            ratio[k].append(r)
            width[k].append(w / px_per_m * 3.2808)
            if k != "garage":
                share[k].append(m2(p) / total)
            if k == "bedroom":
                beds.append(a)
        bed_counts[len(beds)] += 1
        if len(beds) >= 2:
            beds.sort(reverse=True)
            primary_biggest_ratio.append(beds[0] / beds[1])
        # adjacency within each floor: outlines that touch along at least ~0.9 m of wall
        tol = 0.25 * px_per_m
        seen = set()
        for rooms, _ in floors:
            grown = [(k, p.buffer(tol)) for k, p in rooms]
            for i, (ka, pa) in enumerate(grown):
                for kb, pb in grown[i + 1:]:
                    if pa.intersection(pb).area > (tol * 2) * (0.9 * px_per_m):
                        key = tuple(sorted((ka, kb)))
                        if key not in seen:
                            seen.add(key)
                            adj[key] += 1
        for a_k in present:
            for b_k in present:
                if a_k <= b_k:
                    pair_seen[(a_k, b_k)] += 1
    out = {
        "source": "CubiCasa5K (Kalervo et al. 2019), CC BY-NC-SA 4.0; aggregate statistics only",
        "plans": plans,
        "rooms": {k: {"sqft": pct(area[k]), "aspect": pct(ratio[k]), "short_side_ft": pct(width[k]),
                      "share_of_home": pct(share[k]), "found_in_plans": round(kinds_seen[k] / max(plans, 1), 3)}
                  for k in area},
        # how often two room types touch, given both are in the plan
        "adjacency": {f"{a}|{b}": round(c / max(pair_seen[(a, b)], 1), 3)
                      for (a, b), c in adj.items() if pair_seen[(a, b)] >= 30},
        "biggest_bedroom_vs_next": pct(primary_biggest_ratio),
        "bedrooms_per_plan": dict(sorted(bed_counts.items())),
    }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"{plans} plans -> {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
