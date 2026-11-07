from dreambuilt.model import from_dict, load, save, to_dict
from dreambuilt.samples import ashbury


def test_roundtrip_dict():
    h = ashbury()
    assert from_dict(to_dict(h)) == h


def test_roundtrip_files(tmp_path):
    h = ashbury()
    for name in ("h.json", "h.yaml"):
        save(h, tmp_path / name)
        assert load(tmp_path / name) == h


def test_program():
    h = ashbury()
    assert h.heated_area == 48 * 32
    assert len(h.bedrooms) == 3
    assert h.baths == 2
    # rooms tile the footprint exactly
    assert sum(r.area for r in h.levels[0].rooms) == h.heated_area


def test_unknown_field_rejected():
    import pytest
    d = to_dict(ashbury())
    d["levels"][0]["rooms"][0]["colour"] = "red"
    with pytest.raises(ValueError):
        from_dict(d)


def test_halsted_three_stories():
    from dreambuilt.samples import halsted
    h = halsted()
    assert h.stories == 3 and h.heated_area == 3 * 30 * 32
    for lv in h.levels:
        assert sum(r.area for r in lv.rooms) == lv.area
