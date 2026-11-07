"""Orthographic projection with exact hidden-line removal for planar faces.

Depth over a projected planar face is linear in screen (u, v), so the part of
face Q that is nearer than face P is Q's outline cut by a half-plane. Hiding
is the union of those pieces; shapely does the polygon and line algebra.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

from ..geometry import halfplane, lines_of
from .scene import Face3D

EPS = 0.01


def project(p, view: str) -> tuple[float, float, float]:
    x, y, z = p
    if view == "S":
        return (x, z, y)
    if view == "N":
        return (-x, z, -y)
    if view == "E":
        return (y, z, -x)
    if view == "W":
        return (-y, z, x)
    raise ValueError(view)


@dataclass
class Projected:
    face: Face3D
    poly: Polygon
    depth: tuple[float, float, float]  # depth = a*u + b*v + c
    edges: list[LineString]
    details: list[LineString]
    visible: object = None
    visible_edges: list[LineString] = field(default_factory=list)
    visible_details: list[LineString] = field(default_factory=list)


def _depth_plane(pts):
    n = len(pts)
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                (u1, v1, d1), (u2, v2, d2), (u3, v3, d3) = pts[i], pts[j], pts[k]
                det = (u2 - u1) * (v3 - v1) - (u3 - u1) * (v2 - v1)
                if abs(det) > 1e-9:
                    a = ((d2 - d1) * (v3 - v1) - (d3 - d1) * (v2 - v1)) / det
                    b = ((u2 - u1) * (d3 - d1) - (u3 - u1) * (d2 - d1)) / det
                    return (a, b, d1 - a * u1 - b * v1)
    return None


def project_faces(faces: list[Face3D], view: str) -> list[Projected]:
    out = []
    for f in faces:
        pts = [project(p, view) for p in f.pts]
        poly = Polygon([(u, v) for u, v, _ in pts])
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area < 1e-4:
            continue
        plane = _depth_plane(pts)
        if plane is None:
            continue
        ring = [(u, v) for u, v, _ in pts] + [(pts[0][0], pts[0][1])]
        edges = [LineString([a, b]) for a, b in zip(ring, ring[1:]) if a != b]
        details = []
        for line in f.lines:
            q = [project(p, view)[:2] for p in line]
            if len(q) >= 2:
                details.append(LineString(q))
        out.append(Projected(f, poly, plane, edges, details))
    return out


def remove_hidden(items: list[Projected]) -> list[Projected]:
    bounds = [it.poly.bounds for it in items]
    for i, p in enumerate(items):
        px0, py0, px1, py1 = bounds[i]
        pieces = []
        for j, q in enumerate(items):
            if i == j:
                continue
            qx0, qy0, qx1, qy1 = bounds[j]
            if qx0 >= px1 or qx1 <= px0 or qy0 >= py1 or qy1 <= py0:
                continue
            if not p.poly.intersects(q.poly):
                continue
            a = p.depth[0] - q.depth[0]
            b = p.depth[1] - q.depth[1]
            c = p.depth[2] - q.depth[2] - EPS
            # q is nearer where depth_q < depth_p - EPS, i.e. a*u + b*v + c > 0
            hp = halfplane(a, b, c, bounds[i], pad=1.0)
            piece = q.poly.intersection(hp)
            if not piece.is_empty and piece.area > 1e-8:
                pieces.append(piece)
        hidden = unary_union(pieces) if pieces else None
        if hidden is None or hidden.is_empty:
            p.visible = p.poly
            p.visible_edges = list(p.edges)
            p.visible_details = list(p.details)
            continue
        p.visible = p.poly.difference(hidden)
        ph = prep(hidden)
        p.visible_edges = _clip_lines(p.edges, hidden, ph)
        p.visible_details = _clip_lines(p.details, hidden, ph)
    return items


def _clip_lines(lines, hidden, ph):
    out = []
    for ln in lines:
        if not ph.intersects(ln):
            out.append(ln)
            continue
        out += [s for s in lines_of(ln.difference(hidden)) if s.length > 1e-3]
    return out


def elevation(faces: list[Face3D], view: str) -> list[Projected]:
    return remove_hidden(project_faces(faces, view))
