"""Hand-made reference houses. M0 renders the full set from these."""
from __future__ import annotations

from .model import (Brief, Chimney, Fixture, House, InteriorDoor as D, Level, Lot,
                    Opening as O, Porch, RoofMass, Room, Steps)


def ashbury() -> House:
    """The Ashbury: a 48' x 32' one-story Craftsman bungalow with a gabled front porch."""
    rooms = [
        Room("Living", "living", 0, 0, 20, 16.5),
        Room("Dining", "dining", 20, 0, 12, 13),
        Room("Closet 2", "closet", 32, 0, 3, 13),
        Room("Bedroom 2", "bedroom", 35, 0, 13, 13),
        Room("Hall", "hall", 20, 13, 28, 3.5),
        Room("Kitchen", "kitchen", 0, 16.5, 13, 15.5),
        Room("Laundry", "laundry", 13, 16.5, 7, 7),
        Room("Mudroom", "mud", 13, 23.5, 7, 8.5),
        Room("Bedroom 3", "bedroom", 20, 16.5, 11, 15.5),
        Room("Bath 2", "bath", 31, 16.5, 6, 7.5),
        Room("Linen", "closet", 31, 24, 6, 2),
        Room("Primary Bath", "bath", 31, 26, 6, 6),
        Room("Primary Bedroom", "bedroom", 37, 16.5, 11, 15.5),
    ]
    win = dict(kind="window", height=4.5, sill=2.5)
    openings = [
        # South (front)
        O(start=2.5, width=2.5, face="S", **win), O(start=5.0, width=2.5, face="S", **win),
        O(start=7.5, width=2.5, face="S", **win),
        O("door", "S", 15.5, 3.0, 6.83, operation="swing"),
        O(start=22.5, width=2.5, face="S", **win), O(start=25.0, width=2.5, face="S", **win),
        O(start=35.0, width=3.0, face="S", **win), O(start=42.0, width=3.0, face="S", **win),
        # East
        O(start=5.0, width=3.0, face="E", **win),
        O(start=20.5, width=3.0, face="E", **win), O(start=26.0, width=3.0, face="E", **win),
        # North (rear)
        O("window", "N", 4.0, 2.5, 3.5, sill=3.5), O("window", "N", 6.5, 2.5, 3.5, sill=3.5),
        O("door", "N", 15.0, 2.67, 6.83, operation="swing"),
        O(start=24.0, width=3.0, face="N", **win),
        O("window", "N", 32.75, 2.5, 2.0, sill=5.0, operation="awning", grille="1/0"),
        O(start=41.0, width=3.0, face="N", **win),
        # West: windows flank the chimney
        O("window", "W", 2.5, 2.0, 2.5, sill=4.5, operation="casement", grille="2/0"),
        O("window", "W", 11.5, 2.0, 2.5, sill=4.5, operation="casement", grille="2/0"),
        O("window", "W", 24.0, 3.0, 3.5, sill=3.5),
    ]
    doors = [
        D(20, 6.5, "y", 6.0, kind="cased"),
        D(20, 14.75, "y", 3.0, kind="cased"),
        D(7, 16.5, "x", 4.0, kind="cased"),
        D(13, 20.0, "y", 2.5, swing="+"),
        D(13, 26.0, "y", 2.67, swing="+"),
        D(37.5, 13, "x", 2.67, swing="-", hinge="end"),
        D(35, 6.5, "y", 2.0, swing="-"),
        D(22.5, 16.5, "x", 2.67, swing="+"),
        D(34, 16.5, "x", 2.5, swing="+", hinge="end"),
        D(44, 16.5, "x", 2.67, swing="+"),
        D(37, 28.5, "y", 2.5, swing="-"),
        D(33.5, 24, "x", 2.0, swing="+"),
    ]
    fixtures = [
        Fixture("counter", 0.5, 29.5, 12.0, 2.0, "N"),
        Fixture("sink", 4.0, 29.5, 3.0, 2.0, "N"),
        Fixture("counter", 0.5, 19.5, 2.0, 10.0, "W"),
        Fixture("range", 0.5, 20.0, 2.0, 2.5, "W"),
        Fixture("fridge", 0.5, 17.0, 2.5, 2.5, "W"),
        Fixture("washer", 13.75, 20.75, 2.5, 2.5, "N"),
        Fixture("dryer", 16.5, 20.75, 2.5, 2.5, "N"),
        Fixture("tub", 31.5, 21.25, 5.0, 2.5, "N"),
        Fixture("toilet", 35.0, 18.0, 1.5, 2.5, "E"),
        Fixture("vanity", 31.25, 17.5, 1.75, 3.0, "W"),
        Fixture("vanity", 31.5, 26.25, 4.5, 1.75, "S"),
        Fixture("shower", 31.25, 28.75, 3.0, 3.0, "W"),
        Fixture("toilet", 34.75, 30.0, 1.5, 1.75, "N"),
        Fixture("closet", 40.5, 11.0, 7.0, 2.0, "N"),
        Fixture("closet", 29.0, 23.0, 2.0, 7.0, "E"),
        Fixture("closet", 37.25, 17.0, 2.0, 6.5, "W"),
    ]
    main = Level("First Floor", floor_z=2.0, ceiling=9.0, rooms=rooms, openings=openings,
                 doors=doors, fixtures=fixtures)
    return House(
        name="The Ashbury",
        style="craftsman",
        levels=[main],
        roofs=[
            RoofMass("Main", 0, 0, 48, 32, kind="gable", ridge="x", pitch=6, overhang=2.0,
                     plate_z=11.0),
            RoofMass("Porch", 10, -8, 20, 24, kind="gable", ridge="y", pitch=8, overhang=1.5,
                     plate_z=11.0, gable_ends=("S",)),
        ],
        porches=[Porch(10, -8, 20, 8, floor_z=2.0, columns=[(11.0, -7.0), (29.0, -7.0)],
                       steps=[Steps(17.0, 6.0, "S", risers=3)])],
        chimneys=[Chimney(-2.0, 6.0, 2.0, 4.0, top_z=21.0, hearth_wall="W")],
        lot=Lot(66, 130, front=25, rear=20, side=5, house_x=9, house_y=35,
                street="Ashbury Avenue"),
        brief=Brief("Craftsman", 1, 3, 2, 1550, lot="66' x 130'",
                    must_haves=["front porch", "fireplace", "mudroom"]),
        notes=["Exposed rafter tails and knee braces at gable ends.",
               "Tapered porch columns on brick piers."],
    )


def halsted() -> House:
    """The Halsted: a 30' x 32' three-story Foursquare under a hipped roof, full-width porch."""
    win = dict(kind="window", width=3.0, height=5.0, sill=2.5)
    small = dict(kind="window", width=2.0, height=3.0, sill=4.5)

    def windows(face, starts, **kw):
        return [O(face=face, start=x, **{**win, **kw}) for x in starts]

    l1 = Level("First Floor", floor_z=2.5, ceiling=9.0, rooms=[
        Room("Living", "living", 0, 0, 18, 14),
        Room("Dining", "dining", 0, 14, 18, 9),
        Room("Kitchen", "kitchen", 0, 23, 18, 9),
        Room("Entry", "hall", 18, 0, 12, 8),
        Room("Powder", "powder", 18, 8, 8, 6),
        Room("Pantry", "closet", 18, 14, 8, 8),
        Room("Stair", "stair", 26, 8, 4, 14),
        Room("Mudroom", "mud", 18, 22, 12, 10),
    ], openings=[
        *windows("S", [3.5, 10.5]), O("door", "S", 20.0, 3.0, 6.83, operation="swing"),
        O("window", "S", 25.5, 2.5, 5.0, sill=2.5),
        *windows("W", [3.5, 9.5, 16.5]), O("window", "W", 26.0, 3.0, 3.5, sill=3.5),
        O("window", "N", 3.5, 3.0, 3.5, sill=3.5), O("window", "N", 9.5, 3.0, 3.5, sill=3.5),
        O("door", "N", 21.0, 2.67, 6.83, operation="swing"), O(face="N", start=26.0, **small),
        O(face="E", start=3.0, **win), O(face="E", start=13.5, **small),
        O(face="E", start=26.0, **win),
    ], doors=[
        D(18, 7, "y", 6.0, kind="cased"),
        D(9, 14, "x", 8.0, kind="cased"),
        D(9, 23, "x", 5.0, kind="cased"),
        D(22, 8, "x", 2.33, swing="+"),
        D(22, 22, "x", 2.33, swing="-", hinge="end"),
        D(28, 8, "x", 3.0, kind="cased"),
        D(18, 27, "y", 3.0, kind="cased"),
    ], fixtures=[
        Fixture("stair", 26.25, 8.5, 3.5, 12.5, "N"),
        Fixture("counter", 0.5, 29.5, 17.0, 2.0, "N"),
        Fixture("sink", 5.0, 29.5, 3.0, 2.0, "N"),
        Fixture("range", 12.0, 29.5, 2.5, 2.0, "N"),
        Fixture("fridge", 15.0, 29.5, 2.75, 2.25, "N"),
        Fixture("counter", 5.0, 24.5, 8.0, 3.0, "S"),
        Fixture("toilet", 23.5, 11.25, 1.5, 2.5, "N"),
        Fixture("vanity", 19.0, 11.5, 2.0, 2.0, "N"),
        Fixture("washer", 26.5, 29.25, 2.5, 2.5, "N"),
        Fixture("closet", 18.5, 14.5, 7.0, 2.0, "S"),
    ])
    l2 = Level("Second Floor", floor_z=12.5, ceiling=9.0, rooms=[
        Room("Bedroom 2", "bedroom", 0, 0, 15, 13),
        Room("Linen", "closet", 0, 13, 6, 4),
        Room("Hall", "hall", 6, 13, 20, 4),
        Room("Bedroom 3", "bedroom", 0, 17, 15, 15),
        Room("Bedroom 4", "bedroom", 15, 0, 11, 13),
        Room("Closet", "closet", 26, 0, 4, 8),
        Room("Stair", "stair", 26, 8, 4, 14),
        Room("Bath 2", "bath", 15, 17, 11, 5),
        Room("Bath 3", "bath", 15, 22, 8, 10),
        Room("Laundry", "laundry", 23, 22, 7, 10),
    ], openings=[
        *windows("S", [3.5, 9.5, 19.0]),
        *windows("W", [3.5, 9.5, 21.0, 27.0]),
        *windows("N", [3.5, 9.5]), O(face="N", start=18.0, **small), O(face="N", start=26.0, **small),
        O(face="E", start=3.0, **win), O(face="E", start=13.5, **small), O(face="E", start=26.0, **small),
    ], doors=[
        D(10, 13, "x", 2.67, swing="-"),
        D(20, 13, "x", 2.67, swing="-", hinge="end"),
        D(10, 17, "x", 2.67, swing="+"),
        D(20, 17, "x", 2.5, swing="+"),
        D(6, 15, "y", 2.0, swing="-"),
        D(26, 15, "y", 3.0, kind="cased"),
        D(15, 27, "y", 2.5, swing="+"),
        D(28, 22, "x", 2.67, swing="+"),
        D(26, 4, "y", 2.33, swing="+"),
    ], fixtures=[
        Fixture("stair-down", 26.25, 8.5, 3.5, 12.5, "N"),
        Fixture("tub", 15.5, 19.25, 5.0, 2.5, "N"),
        Fixture("toilet", 21.0, 19.5, 1.5, 2.25, "N"),
        Fixture("vanity", 23.0, 19.75, 2.75, 2.0, "N"),
        Fixture("shower", 15.25, 28.75, 3.0, 3.0, "W"),
        Fixture("vanity", 19.5, 29.75, 3.25, 2.0, "N"),
        Fixture("toilet", 15.5, 22.5, 1.5, 2.25, "S"),
        Fixture("washer", 24.0, 29.25, 2.5, 2.5, "N"),
        Fixture("dryer", 26.75, 29.25, 2.5, 2.5, "N"),
        Fixture("closet", 1.0, 11.0, 7.0, 2.0, "N"),
        Fixture("closet", 1.0, 17.25, 7.0, 2.0, "S"),
    ])
    l3 = Level("Third Floor", floor_z=22.5, ceiling=9.0, rooms=[
        Room("Primary Bedroom", "bedroom", 0, 0, 18, 15),
        Room("Primary Bath", "bath", 0, 15, 11, 9),
        Room("Closet", "closet", 11, 15, 7, 9),
        Room("Office", "office", 0, 24, 18, 8),
        Room("Studio", "office", 18, 0, 12, 8),
        Room("Landing", "hall", 18, 8, 8, 14),
        Room("Stair", "stair", 26, 8, 4, 14),
        Room("Bonus Room", "family", 18, 22, 12, 10),
    ], openings=[
        *windows("S", [3.5, 10.5, 19.0, 24.5]),
        *windows("W", [3.5, 9.5]), O(face="W", start=19.0, **small), *windows("W", [27.0]),
        *windows("N", [3.5, 9.5, 19.0, 24.5]),
        O(face="E", start=3.0, **win), O(face="E", start=13.5, **small), O(face="E", start=26.0, **win),
    ], doors=[
        D(18, 11, "y", 2.67, swing="-"),
        D(22, 8, "x", 2.67, swing="-"),
        D(22, 22, "x", 2.67, swing="+"),
        D(18, 28, "y", 2.67, swing="-"),
        D(5, 15, "x", 2.5, swing="+"),
        D(14.5, 15, "x", 2.33, swing="+", hinge="end"),
        D(26, 15, "y", 3.0, kind="cased"),
    ], fixtures=[
        Fixture("stair-down", 26.25, 8.5, 3.5, 12.5, "N"),
        Fixture("tub", 0.5, 21.0, 5.5, 2.75, "N"),
        Fixture("shower", 7.5, 20.5, 3.25, 3.25, "N"),
        Fixture("vanity", 0.5, 15.25, 6.0, 2.0, "S"),
        Fixture("toilet", 8.75, 15.5, 1.5, 2.25, "S"),
        Fixture("closet", 11.25, 15.5, 2.0, 8.0, "W"),
        Fixture("closet", 15.75, 15.5, 2.0, 8.0, "E"),
    ])
    return House(
        name="The Halsted",
        style="foursquare",
        levels=[l1, l2, l3],
        roofs=[
            RoofMass("Main", 0, 0, 30, 32, kind="hip", ridge="y", pitch=7, overhang=1.75,
                     plate_z=31.5),
            RoofMass("Porch", 0, -7, 30, 7, kind="shed", pitch=4, overhang=1.0, plate_z=11.5,
                     low_side="S"),
        ],
        porches=[Porch(0, -7, 30, 7, floor_z=2.5, column="square", pier_height=3.0,
                       columns=[(1.0, -6.0), (10.0, -6.0), (20.0, -6.0), (29.0, -6.0)],
                       steps=[Steps(18.5, 6.0, "S", risers=4)])],
        lot=Lot(50, 120, front=25, rear=20, side=5, house_x=10, house_y=34,
                street="Halsted Street"),
        brief=Brief("Foursquare", 3, 4, 3.5, 2900, lot="50' x 120'",
                    must_haves=["full-width front porch", "third-floor primary suite",
                                "upstairs laundry", "mudroom"]),
        notes=["Hipped roof with deep eaves; belt course at each floor line.",
               "Square porch columns on brick piers."],
    )


SAMPLES = {"ashbury": ashbury, "halsted": halsted}
