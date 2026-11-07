"""The single house model: every sheet, check and export reads from this.

Units are feet. Plan axes: +x east, +y north, z up from finished grade.
The street is to the south, so the south face is the front.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

FACES = ("S", "E", "N", "W")
UNHEATED = {"garage", "void"}
FACE_NAMES = {"S": "South", "E": "East", "N": "North", "W": "West"}


@dataclass
class Room:
    name: str
    kind: str  # living, dining, kitchen, bedroom, bath, hall, laundry, mud, closet, ...
    x: float
    y: float
    w: float
    h: float
    unit: str = ""  # "" is the main house; rental suites get their own id ("Suite 1")
    title: str = ""  # the room's fixed, unique name in this design ("Closet 2"): what edits target

    @property
    def label(self) -> str:
        return self.title or self.name

    @property
    def rect(self) -> Polygon:
        return box(self.x, self.y, self.x + self.w, self.y + self.h)

    @property
    def area(self) -> float:
        return self.w * self.h

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


@dataclass
class Opening:
    """A window or door in an exterior wall.

    `start` runs along the wall: x for S/N faces, y for E/W faces.
    `line` pins the wall's plan coordinate when a face has several edges.
    """
    kind: str  # window | door
    face: str
    start: float
    width: float
    height: float
    sill: float = 0.0  # above finished floor
    grille: Optional[str] = None  # e.g. "3/1"; None uses the style default
    operation: str = "double-hung"  # double-hung | casement | fixed | awning | swing
    mark: Optional[str] = None
    line: Optional[float] = None


@dataclass
class InteriorDoor:
    """A door or cased opening centred at (x, y) on a wall running along `axis`."""
    x: float
    y: float
    axis: str  # "x": wall runs east-west, "y": wall runs north-south
    width: float
    kind: str = "swing"  # swing | cased | pocket | bifold
    swing: str = "+"  # leaf opens toward + or - of the wall normal
    hinge: str = "start"  # start | end (low or high coordinate along the wall)
    height: float = 6.67
    mark: Optional[str] = None


@dataclass
class Fixture:
    kind: str  # tub, shower, toilet, lav, vanity, counter, sink, range, fridge, washer, dryer, closet
    x: float
    y: float
    w: float
    h: float
    back: str = "N"  # which side sits against the wall


@dataclass
class Level:
    name: str
    floor_z: float
    ceiling: float
    rooms: list[Room] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    doors: list[InteriorDoor] = field(default_factory=list)
    fixtures: list[Fixture] = field(default_factory=list)
    floor_depth: float = 1.0  # framing between this level's ceiling and the next floor

    @property
    def footprint(self) -> Polygon:
        shape = unary_union([r.rect for r in self.rooms])
        return shape.buffer(0).simplify(1e-3)

    @property
    def area(self) -> float:
        return self.footprint.area

    @property
    def heated_area(self) -> float:
        """Floor area that counts: no garage, no open-to-below."""
        return sum(r.area for r in self.rooms if r.kind not in UNHEATED)

    @property
    def plate_z(self) -> float:
        return self.floor_z + self.ceiling

    def room_at(self, x: float, y: float) -> Optional[Room]:
        p = Point(x, y)
        for r in self.rooms:
            if r.rect.covers(p):
                return r
        return None


@dataclass
class RoofMass:
    """One analytic roof over a rectangle of wall lines: gable, hip or shed."""
    name: str
    x: float
    y: float
    w: float
    h: float
    kind: str = "gable"  # gable | hip | shed
    ridge: str = "x"  # ridge runs along x or y
    pitch: float = 6.0  # rise per 12 run
    overhang: float = 1.5
    plate_z: float = 9.0
    gable_ends: tuple[str, ...] = ()  # faces that get a gable wall; () means both ends
    low_side: str = "S"  # shed only: the face the roof drains toward
    cladding: str = ""  # gable-end finish, e.g. "stone"; "" uses the style's gable siding


@dataclass
class Porch:
    x: float
    y: float
    w: float
    h: float
    floor_z: float
    columns: list[tuple[float, float]] = field(default_factory=list)
    column: str = "tapered"  # tapered | square | round | none
    pier_height: float = 3.0
    beam_z: float = 0.0  # top of beam; 0 means the floor plate above
    steps: list["Steps"] = field(default_factory=list)


@dataclass
class Steps:
    x: float  # left edge along the face
    width: float
    face: str  # face of the porch they come off
    risers: int = 3


@dataclass
class Chimney:
    x: float
    y: float
    w: float
    h: float
    top_z: float
    hearth_wall: Optional[str] = None  # face of the house the firebox sits against
    flue: float = 0.0  # metal flue pipe above a short chase; 0 for a full masonry chimney
    base_z: float = 0.0  # a fireplace box that floats off the ground starts here


@dataclass
class Dormer:
    """A gabled dormer on a roof slope: its front wall stands at y (facing south) from the
    roof surface (base_z) up to its own plate; its roof is a RoofMass in House.roofs."""
    x: float
    y: float
    w: float
    base_z: float
    plate_z: float
    face: str = "S"


@dataclass
class Balcony:
    """An upper-floor deck with a railing, sitting on a lower roof or cantilevered."""
    x: float
    y: float
    w: float
    h: float
    level: int = 1  # index of the level it opens from
    rail: str = "glass"  # glass | picket


@dataclass
class Lot:
    width: float
    depth: float
    front: float = 25.0
    rear: float = 20.0
    side: float = 5.0
    house_x: float = 10.0  # where model (0, 0) sits on the lot, from its south-west corner
    house_y: float = 30.0
    street: str = "Street"


@dataclass
class Brief:
    style: str
    stories: int
    beds: int
    baths: float
    sqft: int
    lot: str = ""
    must_haves: list[str] = field(default_factory=list)


@dataclass
class Cladding:
    """A finish on part of the outside walls: the wall faces of `level` (index into
    House.levels) on `face` whose middle falls between a and b (x for S/N, y for E/W)."""
    level: int
    face: str
    a: float
    b: float
    hatch: str  # stone | wood | board-and-batten | brick | stucco | lap ...


@dataclass
class House:
    name: str
    style: str
    levels: list[Level]
    roofs: list[RoofMass] = field(default_factory=list)
    porches: list[Porch] = field(default_factory=list)
    chimneys: list[Chimney] = field(default_factory=list)
    balconies: list[Balcony] = field(default_factory=list)
    basement: Optional[Level] = None
    lot: Optional[Lot] = None
    brief: Optional[Brief] = None
    notes: list[str] = field(default_factory=list)
    claddings: list[Cladding] = field(default_factory=list)
    dormers: list[Dormer] = field(default_factory=list)
    genome: dict = field(default_factory=dict)  # the design decisions it was built from (edits keep them)

    @property
    def heated_area(self) -> float:
        return sum(lv.heated_area for lv in self.all_levels)

    @property
    def all_levels(self) -> list[Level]:
        """Basement (if any) first, then the floors above grade."""
        return ([self.basement] if self.basement else []) + list(self.levels)

    @property
    def bedrooms(self) -> list[Room]:
        """The main house's bedrooms (rental suites are counted separately)."""
        return [r for lv in self.all_levels for r in lv.rooms if r.kind == "bedroom" and not r.unit]

    @property
    def suites(self) -> dict[str, list[Room]]:
        out: dict[str, list[Room]] = {}
        for lv in self.all_levels:
            for r in lv.rooms:
                if r.unit:
                    out.setdefault(r.unit, []).append(r)
        return out

    @property
    def baths(self) -> float:
        n = 0.0
        for lv in self.levels:
            for r in [q for q in lv.rooms if not q.unit]:
                if r.kind == "bath":
                    n += 1.0
                elif r.kind == "powder":
                    n += 0.5
        return n

    @property
    def stories(self) -> int:
        return len(self.levels)

    def outline(self) -> Polygon:
        """Plan outline of every enclosed level, porch and chimney."""
        parts = [lv.footprint for lv in self.levels]
        parts += [box(p.x, p.y, p.x + p.w, p.y + p.h) for p in self.porches]
        parts += [box(c.x, c.y, c.x + c.w, c.y + c.h) for c in self.chimneys]
        parts += [box(b.x, b.y, b.x + b.w, b.y + b.h) for b in self.balconies]
        return unary_union(parts)
