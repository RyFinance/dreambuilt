from dreambuilt.model import House, Level, RoofMass, Room
from dreambuilt.roof.analytic import build_roof, roof_area
from dreambuilt.samples import ashbury


def box_house(kind, ridge="x", w=40, h=24, pitch=6):
    lv = Level("L1", 0, 9, rooms=[Room("A", "living", 0, 0, w, h)])
    return House("t", "craftsman", [lv], roofs=[RoofMass("M", 0, 0, w, h, kind=kind, ridge=ridge,
                                                         pitch=pitch, overhang=0, plate_z=9)])


def test_gable_ridge_and_area():
    r = build_roof(box_house("gable"))
    assert len(r.faces) == 2 and len(r.gables) == 2
    assert abs(r.ridge_z() - (9 + 12 * 0.5)) < 1e-9
    slope = (12 ** 2 + 6 ** 2) ** 0.5
    assert abs(roof_area(r) - 2 * 40 * slope) < 1e-6


def test_hip_faces():
    r = build_roof(box_house("hip"))
    assert len(r.faces) == 4 and not r.gables
    assert abs(sum(f.plan.area for f in r.faces) - 40 * 24) < 1e-6


def test_cross_gable_valley():
    r = build_roof(ashbury())
    porch = [f for f in r.faces if f.mass == "Porch"]
    assert len(porch) == 2
    # the porch ridge dies into the main south slope where both reach 17.67'
    top = max(y for f in porch for _, y in f.plan.exterior.coords)
    assert abs(top - 13.333) < 0.01
    # main + porch faces cover the eave outline with no gaps or overlaps
    total = sum(f.plan.area for f in r.faces)
    assert abs(total - r.eave_outline.area) < 1e-6


def test_shed_single_plane():
    h = box_house("shed", w=20, h=8, pitch=4)
    h.roofs[0].low_side = "S"
    r = build_roof(h)
    assert len(r.faces) == 1 and not r.gables
    f = r.faces[0]
    assert abs(f.plane.z(0, 0) - 9) < 1e-9 and abs(f.plane.z(0, 8) - (9 + 8 * 4 / 12)) < 1e-9
