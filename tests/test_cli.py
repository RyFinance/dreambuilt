from dreambuilt.cli import main


def test_render_all_styles(tmp_path):
    main(["render", "--sample", "ashbury", "--all-styles", "-o", str(tmp_path), "--date", "2026-01-01"])
    assert len(list(tmp_path.glob("*.pdf"))) == 3
    main(["render", "--sample", "halsted", "--set", "full", "-o", str(tmp_path / "h.pdf")])
    assert (tmp_path / "h.pdf").exists()


def test_check_exits_zero(capsys):
    import pytest
    with pytest.raises(SystemExit) as e:
        main(["check", "--sample", "ashbury"])
    assert e.value.code == 0
    assert "pass" in capsys.readouterr().out
