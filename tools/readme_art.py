"""The README's art, drawn from real designs the engine makes (so it never goes stale).

    .venv/bin/python tools/readme_art.py        # writes assets/banner.svg and assets/plan-*.svg

The look: an architect's drawing sheet at night. Charcoal paper, chalk-white walls, one
terracotta accent, a title block in the corner.
"""
from __future__ import annotations

import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dreambuilt.brief import parse_text  # noqa: E402
from dreambuilt.design import options  # noqa: E402

INK = "#14161a"      # paper
PAPER2 = "#1b1e23"
CHALK = "#ece7dc"    # walls and type
DIM = "#8a8578"      # secondary lines
ACCENT = "#e0703f"   # terracotta
GRID = "#22262c"
SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif"
MONO = "'SF Mono',Menlo,Consolas,monospace"
SANS = "'Avenir Next','Helvetica Neue',Helvetica,Arial,sans-serif"

FILL = {"bedroom": "#20242a", "bath": "#1d2a2c", "kitchen": "#2a231f", "living": "#23211d",
        "family": "#23211d", "dining": "#26221e", "hall": INK, "stair": INK, "closet": "#191b1f",
        "garage": "#17191c", "entry": "#1f1f22"}


def rooms_svg(rooms, ox, oy, k, label=True, wall=2.2, accent_room=None):
    out = []
    for r in rooms:
        if r.kind == "void":
            continue
        x, y, w, h = ox + r.x * k, oy + r.y * k, r.w * k, r.h * k
        fill = ACCENT if r is accent_room else FILL.get(r.kind, PAPER2)
        op = ' fill-opacity="0.16"' if r is accent_room else ""
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}"{op} '
                   f'stroke="{CHALK}" stroke-width="{wall}"/>')
        if r.kind == "stair":
            n = max(3, int(r.h // 1.0))
            for i in range(1, n):
                yy = y + h * i / n
                out.append(f'<line x1="{x + 2:.1f}" y1="{yy:.1f}" x2="{x + w - 2:.1f}" y2="{yy:.1f}" '
                           f'stroke="{DIM}" stroke-width="0.8"/>')
        if label and min(w, h) > 26 and r.kind not in ("closet", "hall", "stair"):
            name = r.name.replace("Primary Bedroom", "Primary").replace(" Room", "")
            fs = max(8.5, min(12.5, w / max(len(name), 4) * 1.5))
            out.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2:.1f}" fill="{CHALK}" font-family="{SANS}" '
                       f'font-size="{fs:.1f}" letter-spacing="0.6" text-anchor="middle">{escape(name.upper())}</text>')
            out.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + fs + 2:.1f}" fill="{DIM}" font-family="{MONO}" '
                       f'font-size="{fs * 0.78:.1f}" text-anchor="middle">{r.w:g}′ × {r.h:g}′</text>')
    return "\n".join(out)


def dims(x0, y0, x1, label, k_off=-14):
    """A dimension line with ticks above a span."""
    y = y0 + k_off
    return (f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x1:.1f}" y2="{y:.1f}" stroke="{DIM}" stroke-width="0.8"/>'
            f'<line x1="{x0 - 4:.1f}" y1="{y + 4:.1f}" x2="{x0 + 4:.1f}" y2="{y - 4:.1f}" stroke="{DIM}" stroke-width="1"/>'
            f'<line x1="{x1 - 4:.1f}" y1="{y + 4:.1f}" x2="{x1 + 4:.1f}" y2="{y - 4:.1f}" stroke="{DIM}" stroke-width="1"/>'
            f'<text x="{(x0 + x1) / 2:.1f}" y="{y - 5:.1f}" fill="{DIM}" font-family="{MONO}" font-size="10" '
            f'text-anchor="middle">{escape(label)}</text>')


def house(text):
    return options(parse_text(text), 1)[0].house


def banner(h, path: Path):
    W, H = 1280, 520
    main, up = h.levels[0], h.levels[1]
    fw = max(r.x + r.w for r in main.rooms) - min(r.x for r in main.rooms)
    fd = max(r.y + r.h for r in main.rooms)
    k = min(330 / fd, 300 / fw)
    minx = min(r.x for r in main.rooms)
    # the two floors side by side on the right, drawn north-up as on a sheet
    ox1, oy = 640 - minx * k, 120
    ox2 = ox1 + fw * k + 40
    acc = next((r for r in up.rooms if r.name.startswith("Primary Bedroom")), None)
    g = []
    g.append(f'<rect width="{W}" height="{H}" fill="{INK}"/>')
    # drafting grid
    for x in range(0, W, 32):
        g.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="{GRID}" stroke-width="1"/>')
    for y in range(0, H, 32):
        g.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{GRID}" stroke-width="1"/>')
    # sheet border + title block
    g.append(f'<rect x="18" y="18" width="{W - 36}" height="{H - 36}" fill="none" stroke="{DIM}" stroke-width="1"/>')
    g.append(f'<rect x="24" y="24" width="{W - 48}" height="{H - 48}" fill="none" stroke="{CHALK}" stroke-width="1.6"/>')
    g.append(rooms_svg(main.rooms, ox1, oy, k, label=False, wall=1.8))
    g.append(rooms_svg(up.rooms, ox2, oy, k, label=False, wall=1.8, accent_room=acc))
    g.append(dims(ox1 + minx * k, oy, ox1 + (minx + fw) * k, f"{fw:g}′-0″"))
    g.append(f'<text x="{ox1 + (minx + fw / 2) * k:.1f}" y="{oy + fd * k + 26:.1f}" fill="{DIM}" font-family="{MONO}" '
             f'font-size="10.5" letter-spacing="2" text-anchor="middle">01 — MAIN FLOOR</text>')
    g.append(f'<text x="{ox2 + (minx + fw / 2) * k:.1f}" y="{oy + fd * k + 26:.1f}" fill="{DIM}" font-family="{MONO}" '
             f'font-size="10.5" letter-spacing="2" text-anchor="middle">02 — UPPER FLOOR</text>')
    # title
    g.append(f'<text x="70" y="168" fill="{ACCENT}" font-family="{MONO}" font-size="13" letter-spacing="4">'
             f'OFFLINE · ON-DEVICE · APPLE SILICON</text>')
    g.append(f'<text x="64" y="262" fill="{CHALK}" font-family="{SERIF}" font-size="104" font-style="italic" '
             f'letter-spacing="-2">Dream</text>')
    g.append(f'<text x="64" y="356" fill="{CHALK}" font-family="{SERIF}" font-size="104" letter-spacing="-1">Built'
             f'<tspan fill="{ACCENT}">.</tspan></text>')
    g.append(f'<text x="70" y="404" fill="{DIM}" font-family="{SANS}" font-size="17" letter-spacing="0.4">'
             f'Describe a house. Get the plans.</text>')
    # north arrow
    nx, ny = W - 92, 82
    g.append(f'<circle cx="{nx}" cy="{ny}" r="20" fill="none" stroke="{CHALK}" stroke-width="1.2"/>'
             f'<path d="M{nx} {ny - 16} L{nx + 7} {ny + 8} L{nx} {ny + 3} L{nx - 7} {ny + 8} Z" fill="{ACCENT}"/>'
             f'<text x="{nx}" y="{ny - 26}" fill="{CHALK}" font-family="{MONO}" font-size="11" text-anchor="middle">N</text>')
    # title block, bottom right
    tx, ty, tw, th = W - 344, H - 98, 320, 74
    g.append(f'<rect x="{tx}" y="{ty}" width="{tw}" height="{th}" fill="{INK}" stroke="{CHALK}" stroke-width="1.2"/>')
    g.append(f'<line x1="{tx + 236}" y1="{ty}" x2="{tx + 236}" y2="{ty + th}" stroke="{CHALK}" stroke-width="1"/>')
    g.append(f'<line x1="{tx}" y1="{ty + 38}" x2="{tx + 236}" y2="{ty + 38}" stroke="{DIM}" stroke-width="0.8"/>')
    g.append(f'<text x="{tx + 12}" y="{ty + 16}" fill="{DIM}" font-family="{MONO}" font-size="8.5" letter-spacing="1.5">PROJECT</text>')
    g.append(f'<text x="{tx + 12}" y="{ty + 31}" fill="{CHALK}" font-family="{SANS}" font-size="12">'
             f'{escape(h.name)} · {h.heated_area:,.0f} sq ft</text>')
    g.append(f'<text x="{tx + 12}" y="{ty + 54}" fill="{DIM}" font-family="{MONO}" font-size="8.5" letter-spacing="1.5">SCALE</text>')
    g.append(f'<text x="{tx + 12}" y="{ty + 67}" fill="{CHALK}" font-family="{MONO}" font-size="10.5">1/8″ = 1′-0″ · concept only</text>')
    g.append(f'<text x="{tx + 278}" y="{ty + 46}" fill="{ACCENT}" font-family="{SERIF}" font-size="26" '
             f'text-anchor="middle">A0.1</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">' + \
        "".join(g) + "</svg>"
    path.write_text(svg)


def plan_card(h, level, title, path: Path):
    lv = h.levels[level]
    rooms = [r for r in lv.rooms if r.kind != "void"]
    minx = min(r.x for r in rooms)
    fw = max(r.x + r.w for r in rooms) - minx
    fd = max(r.y + r.h for r in rooms)
    W = 620
    k = (W - 80) / fw
    H = int(fd * k + 130)
    g = [f'<rect width="{W}" height="{H}" rx="14" fill="{INK}"/>']
    for x in range(0, W, 24):
        g.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="{GRID}" stroke-width="0.8"/>')
    for y in range(0, H, 24):
        g.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{GRID}" stroke-width="0.8"/>')
    ox, oy = 40 - minx * k, 70
    g.append(rooms_svg(rooms, ox, oy, k, label=True, wall=2.0))
    g.append(dims(40, oy, 40 + fw * k, f"{fw:g}′-0″"))
    g.append(f'<text x="40" y="34" fill="{ACCENT}" font-family="{MONO}" font-size="11" letter-spacing="3">'
             f'{escape(title.upper())}</text>')
    g.append(f'<text x="40" y="{H - 22}" fill="{DIM}" font-family="{MONO}" font-size="10.5">'
             f'{escape(lv.name)} · generated by Dream Built, unedited</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">' + \
        "".join(g) + "</svg>"
    path.write_text(svg)


def main():
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    hero = house("craftsman 4 bed 3.5 bath 3000 sqft 2 storey 65x135 with garage and mudroom")
    banner(hero, out / "banner.svg")
    a = house("modern 4 bed 3.5 bath 3400 sqft 2 storey 70x140 2 car garage")
    plan_card(a, 0, "Modern · main floor", out / "plan-modern-main.svg")
    plan_card(a, 1, "Modern · upper floor", out / "plan-modern-upper.svg")
    c = house("japanese 3 bed 2 bath 2000 sqft one storey 90x130 2 car garage")
    plan_card(c, 0, "Japanese · courtyard bungalow", out / "plan-japanese.svg")
    print("wrote", ", ".join(p.name for p in sorted(out.glob("*.svg"))))


if __name__ == "__main__":
    main()
