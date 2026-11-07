"""Turn the CubiCasa5K drawings into a library of clean, rectangular layouts the designer can
start from (data/raw/cubicasa5k/library.json, local only: CC BY-NC-SA 4.0).

    python tools/build_plan_library.py data/raw/cubicasa5k/svg data/raw/cubicasa5k/library.json

Per floor: rooms squared up to their bounding boxes (only plans whose rooms are near-rectangular),
walls snapped together so rooms share edges, turned so the entry faces the street (y = 0),
in feet at the plan's own scale (calibrated on its doors)."""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from statistics import median

from shapely.geometry import box
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(__file__))
from mine_cubicasa import KIND, parse  # noqa: E402

FT = 3.2808


def stairs_of(svg_part: str):
    from mine_cubicasa import _poly
    svg_part = re.sub(r"<defs>.*?</defs>", "", svg_part, flags=re.S)  # arrow markers sit at 0,0
    out = []
    for m in re.finditer(r'class="Stairs[^"]*"[^>]*>(.*?)</g>', svg_part, re.S):
        polys = [_poly(x) for x in re.findall(r'points="([^"]+)"', m.group(1))]
        polys = [p for p in polys if p is not None and not p.is_empty and p.area > 1]
        if polys:
            out.append(unary_union(polys).envelope)
    return out


def door_centres(svg_part: str, px_per_ft: float):
    from mine_cubicasa import _poly
    out = []
    for m in re.finditer(r'class="Door[^"]*"[^>]*>\s*<polygon[^>]*points="([^"]+)"', svg_part):
        p = _poly(m.group(1))
        if p is not None and not p.is_empty:
            c = p.centroid
            out.append((c.x / px_per_ft, c.y / px_per_ft))
    return out


def door_pairs(rects, doors):
    """Which two rooms each real door joins (indices into rects)."""
    from shapely.geometry import Point
    pairs = set()
    for x, y in doors:
        pt = Point(x, y)
        near = sorted((box(r[1], r[2], r[3], r[4]).distance(pt), i) for i, r in enumerate(rects))
        near = [i for d, i in near if d < 1.6][:2]
        if len(near) == 2:
            pairs.add(tuple(sorted(near)))
    return sorted(pairs)


def cluster(vals, tol):
    """Map each value to the mean of its cluster (values within tol of a neighbour)."""
    vs = sorted(set(round(v, 3) for v in vals))
    groups, cur = [], [vs[0]]
    for v in vs[1:]:
        if v - cur[-1] <= tol:
            cur.append(v)
        else:
            groups.append(cur)
            cur = [v]
    groups.append(cur)
    m = {}
    for g in groups:
        c = sum(g) / len(g)
        for v in g:
            m[v] = c
    return lambda v: m[round(v, 3)]


def _rects_of(p, tol=0.86):
    """A room polygon as one or two axis-aligned rectangles (an L splits at its inner corner).
    Small notches (columns, chases) are ignored."""
    env = p.envelope
    if p.area / max(env.area, 1e-6) >= 0.8:
        return [env]
    p = p.simplify(max(env.bounds[2] - env.bounds[0], env.bounds[3] - env.bounds[1]) * 0.03)
    if p.geom_type != "Polygon":
        return None
    x0, y0, x1, y1 = env.bounds
    xs = sorted({round(c[0], 2) for c in p.exterior.coords})
    ys = sorted({round(c[1], 2) for c in p.exterior.coords})
    best = None
    for cx in xs[1:-1]:
        parts = [p.intersection(box(x0, y0, cx, y1)), p.intersection(box(cx, y0, x1, y1))]
        if all(q.area > 0 and q.area / q.envelope.area >= tol for q in parts):
            best = [q.envelope for q in parts]
            break
    if best is None:
        for cy in ys[1:-1]:
            parts = [p.intersection(box(x0, y0, x1, cy)), p.intersection(box(x0, cy, x1, y1))]
            if all(q.area > 0 and q.area / q.envelope.area >= tol for q in parts):
                best = [q.envelope for q in parts]
                break
    if best is None:
        best = _strips(p)
    return best


def _strips(p, max_parts: int = 5):
    """Any near-rectilinear shape (a T-shaped entry, a U-shaped stair hall) as up to five
    rectangles: slice at its corners, keep the well-filled slices, merge equal neighbours."""
    x0, y0, x1, y1 = p.envelope.bounds
    xs = sorted({round(c[0], 1) for c in p.exterior.coords} | {round(x0, 1), round(x1, 1)})
    cols = []
    for a, b in zip(xs, xs[1:]):
        if b - a < (x1 - x0) * 0.04:
            continue
        sl = p.intersection(box(a, y0, b, y1))
        for g in getattr(sl, "geoms", [sl]):
            if g.is_empty or g.area <= 0:
                continue
            e = g.envelope
            if g.area / e.area < 0.85:
                return None
            cols.append(list(e.bounds))
    # merge side-by-side slices with the same top and bottom
    cols.sort()
    merged = []
    for c in cols:
        if merged and abs(merged[-1][2] - c[0]) < 1e-6 and abs(merged[-1][1] - c[1]) < (y1 - y0) * 0.03 \
                and abs(merged[-1][3] - c[3]) < (y1 - y0) * 0.03:
            merged[-1][2] = c[2]
        else:
            merged.append(c)
    if not merged or len(merged) > max_parts:
        return None
    return [box(*m) for m in merged]


def _indoor_stairs(rooms, stairs):
    """Stairs inside the house only (not the steps outside), touching pieces of one stair
    (a flight and its winders) merged into one outline."""
    if not stairs or not rooms:
        return []
    from shapely.geometry import Polygon
    u = unary_union([p for _, p in rooms])
    d = max(u.bounds[2] - u.bounds[0], u.bounds[3] - u.bounds[1]) * 0.05
    u = u.buffer(d).buffer(-d * 0.8)  # the house outline, stairwells closed in
    inside = unary_union([Polygon(g.exterior) for g in getattr(u, "geoms", [u])])
    keep = [st for st in stairs if st.intersection(inside).area >= 0.6 * st.area]
    merged = unary_union([st.buffer(d * 0.15) for st in keep])
    out = []
    for g in getattr(merged, "geoms", [merged]):
        if g.is_empty:
            continue
        parts = [st for st in keep if st.intersects(g)]
        out.append(unary_union(parts).envelope)
    return out


def _carve(rooms, stairs):
    """Stairs are drawn inside a hall or entry: cut each out of the rooms it overlaps."""
    stairs = _indoor_stairs(rooms, stairs)
    out = list(rooms)
    for st in stairs:
        nxt = []
        for k, p in out:
            if p.intersection(st).area > 0.05 * st.area:
                rest = p.difference(st)
                for g in getattr(rest, "geoms", [rest]):
                    if g.area > 0.04 * p.area:
                        nxt.append((k, g))
            else:
                nxt.append((k, p))
        out = nxt + [("stair", st)]
    return out


MAJOR = {"bedroom", "living", "kitchen", "bath", "dining", "entry", "stair", "garage"}


def _resolve_overlaps(rects, rounds: int = 20):
    """Rooms squared up from slightly odd shapes overlap their neighbours a little: pull the
    edge of one back to the other's, along the thin side of the overlap."""
    rects = [list(r) for r in rects]
    for _ in range(rounds):
        changed = False
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                ox0, oy0 = max(a[1], b[1]), max(a[2], b[2])
                ox1, oy1 = min(a[3], b[3]), min(a[4], b[4])
                if ox1 - ox0 <= 1e-6 or oy1 - oy0 <= 1e-6:
                    continue
                changed = True
                # shrink the smaller room (the bigger one keeps its walls)
                small, big = (a, b) if (a[3] - a[1]) * (a[4] - a[2]) <= (b[3] - b[1]) * (b[4] - b[2]) else (b, a)
                if ox1 - ox0 <= oy1 - oy0:
                    if small[1] < big[1]:
                        small[3] = big[1]
                    else:
                        small[1] = big[3]
                else:
                    if small[2] < big[2]:
                        small[4] = big[2]
                    else:
                        small[2] = big[4]
                if small[3] - small[1] < 2.0 or small[4] - small[2] < 2.0:
                    if small[0] in MAJOR:
                        return None
                    small[0] = "_gone"  # a squeezed-out closet: drop it
        rects = [r for r in rects if r[0] != "_gone"]
        if not changed:
            return rects
    return None


def floor_rooms(rooms, px_per_ft, stairs=()):
    got = _floor_rooms(rooms, px_per_ft, stairs, 1.8)
    return got if got is not None else _floor_rooms(rooms, px_per_ft, stairs, 2.6)


def _floor_rooms(rooms, px_per_ft, stairs, tol):
    rects = []
    rooms = _carve(rooms, stairs)
    for k, p in rooms:
        if k == "garage" and p.area / px_per_ft ** 2 < 150:
            continue
        parts = _rects_of(p)
        if parts is None:
            return None  # an odd-shaped room: skip this floor
        for b in parts:
            x0, y0, x1, y1 = (v / px_per_ft for v in b.bounds)
            rects.append([k, x0, y0, x1, y1])
    if len(rects) < 4:
        return None
    fx = cluster([r[1] for r in rects] + [r[3] for r in rects], tol)
    fy = cluster([r[2] for r in rects] + [r[4] for r in rects], tol)
    out = []
    for k, x0, y0, x1, y1 in rects:
        x0, x1, y0, y1 = fx(x0), fx(x1), fy(y0), fy(y1)
        if x1 - x0 < 2.0 or y1 - y0 < 2.0:
            continue
        out.append([k, x0, y0, x1, y1])
    out = _resolve_overlaps(out)
    if out is None:
        return None
    boxes = [box(r[1], r[2], r[3], r[4]) for r in out]
    u = unary_union(boxes)
    if u.geom_type != "Polygon":
        return None
    if abs(sum(b.area for b in boxes) - u.area) > 0.002 * u.area:
        return None  # still overlapping
    # unlabelled gaps inside (corridors, shafts): halls if usable, closets if small
    for hole in u.interiors:
        from shapely.geometry import Polygon
        h = Polygon(hole)
        e = h.envelope
        if h.area / max(e.area, 1e-6) < 0.8:
            return None
        x0, y0, x1, y1 = e.bounds
        if min(x1 - x0, y1 - y0) >= 3.0 and h.area >= 20:
            out.append(["hall", x0, y0, x1, y1])
        else:
            out.append(["closet", x0, y0, x1, y1])
    u = unary_union([box(r[1], r[2], r[3], r[4]) for r in out])
    if len(getattr(u, "interiors", [])):
        return None
    return out, u


def orient(rects, u, pts=()):
    """Rotate/flip so the entry is on the south (y = 0) edge; origin at the corner."""
    x0, y0, x1, y1 = u.bounds
    orient.pts = []
    entry = next((r for r in rects if r[0] == "entry"), None)
    if entry is None:
        return None
    # which outside edge does the entry touch?
    sides = {"S": abs(entry[2] - y0) < 0.1, "N": abs(entry[4] - y1) < 0.1,
             "W": abs(entry[1] - x0) < 0.1, "E": abs(entry[3] - x1) < 0.1}
    side = next((s for s in ("S", "N", "W", "E") if sides[s]), None)
    if side is None:
        # an entry lobby inside: the street is the outside wall nearest to it
        cx, cy = (entry[1] + entry[3]) / 2, (entry[2] + entry[4]) / 2
        side = min({"S": cy - y0, "N": y1 - cy, "W": cx - x0, "E": x1 - cx}.items(), key=lambda kv: kv[1])[0]
    W, D = x1 - x0, y1 - y0
    out = []
    for k, a, b, c, d in rects:
        a, b, c, d = a - x0, b - y0, c - x0, d - y0
        # svg y grows downward: "S" in the drawing is the top edge (y0); make that the street
        if side == "S":
            r = (a, b, c, d)
        elif side == "N":
            r = (a, D - d, c, D - b)
        elif side == "W":
            r = (b, a, d, c)
        else:
            r = (b, W - c, d, W - a)
        out.append([k] + [round(v, 2) for v in r])
    for px, py in pts:
        a, b = px - x0, py - y0
        orient.pts.append({"S": (a, b), "N": (a, D - b), "W": (b, a), "E": (b, W - a)}[side])
    return out


def _align_upper(rects, st, gst, ground):
    """Turn and move an upper floor so its stair sits on the ground floor's stair; it must
    then sit inside (or nearly inside) the ground floor's outline."""
    from shapely.geometry import box as _b
    g = unary_union([_b(r[1], r[2], r[3], r[4]) for r in ground])
    sw, sh = st[3] - st[1], st[4] - st[2]
    gw, gh = gst[3] - gst[1], gst[4] - gst[2]
    best = None
    for rot in range(8):
        def tf(x, y):
            if rot >= 4:
                x = -x
            for _ in range(rot % 4):
                x, y = -y, x
            return x, y
        rr = []
        for k, a, b, c, d in rects:
            (p, q), (r_, s_) = tf(a, b), tf(c, d)
            rr.append([k, min(p, r_), min(q, s_), max(p, r_), max(q, s_)])
        s2 = max((r for r in rr if r[0] == "stair"), key=lambda r: (r[3] - r[1]) * (r[4] - r[2]))
        if abs((s2[3] - s2[1]) - gw) > 1.5 or abs((s2[4] - s2[2]) - gh) > 1.5:
            continue
        dx, dy = gst[1] - s2[1], gst[2] - s2[2]
        moved = [[k, a + dx, b + dy, c + dx, d + dy] for k, a, b, c, d in rr]
        u = unary_union([_b(r[1], r[2], r[3], r[4]) for r in moved])
        inside = u.intersection(g).area / u.area
        if inside > 0.88 and (best is None or inside > best[0]):
            best = (inside, [[k] + [round(v, 2) for v in (a, b, c, d)] for k, a, b, c, d in moved])
    return best[1] if best else None


def main(src: str, dst: str):
    plans = []
    files = sorted(glob.glob(os.path.join(src, "*.svg")))
    for n, f in enumerate(files):
        svg = open(f).read()
        floors = parse(svg)
        doors = [d for _, ds in floors for d in ds]
        if len(doors) < 3:
            continue
        px_per_ft = median(doors) / (0.85 * FT)
        parts = re.split(r'<g[^>]*class="Floorplan Floor-\d+"[^>]*>', svg)[1:] or [svg]
        out_floors = []
        ground_stair = None
        order = sorted(range(len(floors)), key=lambda i: (
            -(any(k == "kitchen" for k, _ in floors[i][0]) + any(k == "entry" for k, _ in floors[i][0])),
            sum(k == "bedroom" for k, _ in floors[i][0])))
        floors = [floors[i] for i in order]
        parts = [parts[i] for i in order] if len(parts) == len(order) else parts
        for i, ((rooms, _), part) in enumerate(zip(floors, parts)):
            got = floor_rooms(rooms, px_per_ft, stairs_of(part))
            if got is None:
                if i == 0:
                    out_floors = None
                break
            rects, u = got
            if i == 0:
                o = orient(rects, u, door_centres(part, px_per_ft))
                if o is None:
                    out_floors = None
                    break
                ground_stair = max((r for r in o if r[0] == "stair"),
                                   key=lambda r: (r[3] - r[1]) * (r[4] - r[2]), default=None)
                out_floors.append(o)
                ground_doors = door_pairs(o, orient.pts)
            else:
                # an upper floor joins the plan only if it lines up over the ground floor's stair
                st = max((r for r in rects if r[0] == "stair"),
                         key=lambda r: (r[3] - r[1]) * (r[4] - r[2]), default=None)
                if ground_stair is None or st is None:
                    break
                o = _align_upper(rects, st, ground_stair, out_floors[0])
                if o is None:
                    break
                out_floors.append(o)
        if not out_floors:
            continue
        kinds = [r[0] for r in out_floors[0]]
        area = sum((r[3] - r[1]) * (r[4] - r[2]) for fl in out_floors for r in fl if r[0] != "garage")
        plans.append({"id": os.path.basename(f)[:-4], "floors": out_floors, "sqft": round(area),
                      "doors": [ground_doors],
                      "beds": sum(r[0] == "bedroom" for fl in out_floors for r in fl),
                      "baths": sum(r[0] == "bath" for fl in out_floors for r in fl),
                      "garage": any(r[0] == "garage" for fl in out_floors for r in fl)})
        if n % 500 == 0:
            print(n, len(plans), flush=True)
    with open(dst, "w") as fo:
        json.dump(plans, fo)
    from collections import Counter
    print(len(plans), "plans;", Counter(len(p["floors"]) for p in plans), Counter(p["beds"] for p in plans))


if __name__ == "__main__":
    main(*sys.argv[1:3])
