"""Small plane-geometry helpers shared by the roof, views and checks."""
from __future__ import annotations

from shapely.geometry import (GeometryCollection, LineString, MultiLineString, MultiPolygon,
                              Polygon)


def halfplane(a: float, b: float, c: float, bounds, pad: float = 10.0) -> Polygon:
    """Region of `bounds` (padded) where a*x + b*y + c >= 0."""
    x0, y0, x1, y1 = bounds
    rect = [(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)]
    return clip_polygon(rect, a, b, c)


def clip_polygon(pts, a: float, b: float, c: float) -> Polygon:
    """Sutherland-Hodgman clip of a convex ring to a*x + b*y + c >= 0."""
    f = lambda p: a * p[0] + b * p[1] + c
    out = []
    n = len(pts)
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        fp, fq = f(p), f(q)
        if fp >= 0:
            out.append(p)
        if (fp >= 0) != (fq >= 0):
            t = fp / (fp - fq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    if len(out) < 3:
        return Polygon()
    return Polygon(out)


def polygons_of(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, (MultiPolygon, GeometryCollection)):
        return [g for part in geom.geoms for g in polygons_of(part)]
    return []


def lines_of(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, (MultiLineString, GeometryCollection)):
        return [g for part in geom.geoms for g in lines_of(part)]
    return []


def rings_of(poly: Polygon) -> list[list[tuple[float, float]]]:
    return [list(poly.exterior.coords)] + [list(r.coords) for r in poly.interiors]


def hatch_lines(region, angle_deg: float, spacing: float, offset: float = 0.0) -> list[LineString]:
    """Parallel lines at `angle_deg`, anchored to the origin so adjacent regions line up."""
    import math
    if region is None or region.is_empty:
        return []
    x0, y0, x1, y1 = region.bounds
    t = math.radians(angle_deg)
    dx, dy = math.cos(t), math.sin(t)
    nx, ny = -dy, dx
    ds = [nx * x + ny * y for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    ts = [dx * x + dy * y for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    tmin, tmax = min(ts) - 1, max(ts) + 1
    out = []
    k = math.floor((min(ds) - offset) / spacing)
    while k * spacing + offset <= max(ds):
        d = k * spacing + offset
        seg = LineString([(nx * d + dx * tmin, ny * d + dy * tmin),
                          (nx * d + dx * tmax, ny * d + dy * tmax)])
        out.extend(lines_of(seg.intersection(region)))
        k += 1
    return out
