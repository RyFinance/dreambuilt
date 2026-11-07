from dreambuilt.views.hlr import elevation
from dreambuilt.views.scene import Face3D, box_faces


def test_front_box_hides_back_box():
    front = box_faces(0, 0, 0, 10, 2, 10, "wall")
    back = box_faces(2, 5, 0, 8, 7, 5, "wall")  # entirely behind and smaller
    items = elevation(front + back, "S")
    hidden = [it for it in items if it.face in back]
    assert all(not it.visible_edges for it in hidden)


def test_taller_back_box_shows_above():
    front = box_faces(0, 0, 0, 10, 2, 5, "wall")
    back = box_faces(2, 5, 0, 8, 7, 9, "wall")
    items = elevation(front + back, "S")
    vis = [e for it in items if it.face in back for e in it.visible_edges]
    assert vis and min(min(y for _, y in e.coords) for e in vis) >= 5 - 1e-6


def test_window_in_front_of_wall_visible():
    wall = Face3D([(0, 0, 0), (10, 0, 0), (10, 0, 8), (0, 0, 8)], "wall")
    win = Face3D([(3, -0.04, 2), (6, -0.04, 2), (6, -0.04, 6), (3, -0.04, 6)], "window")
    items = elevation([wall, win], "S")
    assert len([it for it in items if it.face is win][0].visible_edges) == 4
