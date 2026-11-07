"""Build "Dream Built.app": a double-clickable Mac app for this checkout.

    .venv/bin/python tools/make_app.py            # -> dist/Dream Built.app
    .venv/bin/python tools/make_app.py --install  # also copies it to ~/Applications

The app runs this project's own environment (.venv) and model folder, so nothing is
downloaded or duplicated: move the project and run this again.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Dream Built"
BUNDLE_ID = "com.ryfinance.dreambuilt"


def draw_icon(path: Path, size: int = 1024) -> None:
    """The icon: a house outline (gable, door, two windows) in warm white on deep blue."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.22
    d.rounded_rectangle([size * 0.06, size * 0.06, size * 0.94, size * 0.94], radius=r, fill=(18, 28, 48, 255))
    ink = (241, 236, 222, 255)
    w = max(6, size // 36)
    cx, base = size / 2, size * 0.74
    left, right, eave, ridge = size * 0.26, size * 0.74, size * 0.48, size * 0.24
    d.line([(size * 0.2, eave + size * 0.02), (cx, ridge), (size * 0.8, eave + size * 0.02)], fill=ink, width=w,
           joint="curve")
    d.line([(left, eave), (left, base), (right, base), (right, eave)], fill=ink, width=w, joint="curve")
    dw, dh = size * 0.1, size * 0.17
    d.rectangle([cx - dw / 2, base - dh, cx + dw / 2, base], outline=ink, width=w)
    for x in (left + size * 0.07, right - size * 0.07 - size * 0.1):
        d.rectangle([x, eave + size * 0.06, x + size * 0.1, eave + size * 0.14], outline=ink, width=w)
    d.line([(size * 0.18, base), (size * 0.82, base)], fill=ink, width=w)
    img.save(path)


def make_icns(png: Path, out: Path) -> bool:
    """macOS .icns from the 1024 px icon (sips + iconutil ship with macOS)."""
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for s in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = s * scale
                name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-z", str(px), str(px), str(png), "--out", str(iconset / name)],
                               check=True, capture_output=True)
        r = subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], capture_output=True)
        return r.returncode == 0


def build(dest: Path) -> Path:
    app = dest / f"{NAME}.app"
    if app.exists():
        shutil.rmtree(app)
    macos = app / "Contents" / "MacOS"
    res = app / "Contents" / "Resources"
    macos.mkdir(parents=True)
    res.mkdir(parents=True)
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        sys.exit(f"no environment at {python}: create it first (see README)")
    launcher = macos / "dreambuilt"
    launcher.write_text(f"""#!/bin/bash
# Dream Built launcher: runs the desktop app from the project's own environment.
cd "{ROOT}" || exit 1
mkdir -p "$HOME/.dreambuilt"
exec "{python}" -m dreambuilt.cli app "$@" >> "$HOME/.dreambuilt/app.log" 2>&1
""")
    launcher.chmod(0o755)
    png = res / "icon.png"
    draw_icon(png)
    has_icns = make_icns(png, res / "icon.icns")
    info = {
        "CFBundleName": NAME,
        "CFBundleDisplayName": NAME,
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": "0.5.0",
        "CFBundleShortVersionString": "0.5",
        "CFBundleExecutable": "dreambuilt",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.graphics-design",
    }
    if has_icns:
        info["CFBundleIconFile"] = "icon"
    with open(app / "Contents" / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    return app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--install", action="store_true", help="also copy the app to ~/Applications")
    args = ap.parse_args()
    app = build(ROOT / "dist")
    print(f"built {app}")
    if args.install:
        target = Path.home() / "Applications" / app.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(app, target, symlinks=True)
        os.utime(target)
        print(f"installed {target}")


if __name__ == "__main__":
    main()
