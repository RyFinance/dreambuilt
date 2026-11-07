"""SVG and ReportLab PDF writers for sheets."""
from __future__ import annotations

from pathlib import Path as FsPath
from xml.sax.saxutils import escape

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas

from .canvas import Arc, Circle, Path, Sheet, Text
from .themes import Theme

PT = 72.0

SVG_FONTS = {
    "Helvetica": ("Helvetica, Arial, sans-serif", "normal", "normal"),
    "Helvetica-Bold": ("Helvetica, Arial, sans-serif", "bold", "normal"),
    "Helvetica-Oblique": ("Helvetica, Arial, sans-serif", "normal", "italic"),
    "Helvetica-BoldOblique": ("Helvetica, Arial, sans-serif", "bold", "italic"),
    "Times-Roman": ("'Times New Roman', Times, serif", "normal", "normal"),
    "Times-Bold": ("'Times New Roman', Times, serif", "bold", "normal"),
    "Times-Italic": ("'Times New Roman', Times, serif", "normal", "italic"),
    "Courier": ("Courier, monospace", "normal", "normal"),
}


def text_width(s: str, font: str, size: float, spacing: float = 0.0) -> float:
    """Width in inches."""
    return (stringWidth(s, font, size) + spacing * max(len(s) - 1, 0)) / PT


def _f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# -- SVG --------------------------------------------------------------------

def sheet_to_svg(sheet: Sheet, theme: Theme) -> str:
    W, H = sheet.width * PT, sheet.height * PT
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(sheet.width)}in" '
           f'height="{_f(sheet.height)}in" viewBox="0 0 {_f(W)} {_f(H)}">',
           f'<rect width="{_f(W)}" height="{_f(H)}" fill="{theme.bg}"/>',
           '<g fill="none" stroke-linecap="round" stroke-linejoin="round">']
    Y = lambda y: H - y * PT
    for it in sheet.items:
        if isinstance(it, Path):
            d = []
            for ring in it.rings:
                d.append("M" + " L".join(f"{_f(x * PT)} {_f(Y(y))}" for x, y in ring))
                if it.closed:
                    d[-1] += " Z"
            attrs = _svg_paint(theme, it.role if it.stroke else None, it.fill)
            out.append(f'<path d="{" ".join(d)}"{attrs}/>')
        elif isinstance(it, Circle):
            attrs = _svg_paint(theme, it.role, it.fill)
            out.append(f'<circle cx="{_f(it.x * PT)}" cy="{_f(Y(it.y))}" r="{_f(it.r * PT)}"{attrs}/>')
        elif isinstance(it, Arc):
            from .canvas import arc_points
            pts = arc_points(it.x, it.y, it.r, it.a0, it.a1)
            d = "M" + " L".join(f"{_f(x * PT)} {_f(Y(y))}" for x, y in pts)
            out.append(f'<path d="{d}"{_svg_paint(theme, it.role, None)}/>')
        elif isinstance(it, Text):
            fontname = theme.fonts.get(it.font, theme.fonts["body"])
            fam, weight, style = SVG_FONTS.get(fontname, SVG_FONTS["Helvetica"])
            anchor = {"start": "start", "middle": "middle", "end": "end"}[it.anchor]
            x, y = it.x * PT, Y(it.y)
            rot = f' transform="rotate({_f(-it.rotate)} {_f(x)} {_f(y)})"' if it.rotate else ""
            sp = f' letter-spacing="{_f(it.spacing)}"' if it.spacing else ""
            out.append(f'<text x="{_f(x)}" y="{_f(y)}" font-family="{fam}" font-size="{_f(it.size)}" '
                       f'font-weight="{weight}" font-style="{style}" text-anchor="{anchor}" '
                       f'fill="{theme.fill(it.role) if it.role != "text" else theme.ink}" '
                       f'stroke="none"{sp}{rot}>{escape(it.text)}</text>')
    out.append("</g></svg>")
    return "\n".join(out) + "\n"


def _svg_paint(theme: Theme, role, fill) -> str:
    parts = []
    if fill:
        parts.append(f' fill="{theme.fill(fill)}" fill-rule="evenodd"')
    if role and role != "none":
        s = theme.stroke(role)
        parts.append(f' stroke="{s.color}" stroke-width="{_f(s.width)}"')
        if s.dash:
            parts.append(f' stroke-dasharray="{" ".join(_f(d) for d in s.dash)}"')
    else:
        parts.append(' stroke="none"')
    return "".join(parts)


def write_svgs(sheets: list[Sheet], theme: Theme, folder: str | FsPath) -> list[FsPath]:
    folder = FsPath(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for s in sheets:
        p = folder / f"{s.number.replace('.', '_')}.svg"
        p.write_text(sheet_to_svg(s, theme))
        paths.append(p)
    return paths


# -- PDF --------------------------------------------------------------------

def write_pdf(sheets: list[Sheet], theme: Theme, path: str | FsPath, title: str = "") -> FsPath:
    path = FsPath(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = rl_canvas.Canvas(str(path), pagesize=(sheets[0].width * PT, sheets[0].height * PT),
                         invariant=1, pageCompression=1)
    c.setTitle(title)
    c.setAuthor("Dream Built")
    c.setCreator("Dream Built (dreambuilt)")
    for s in sheets:
        c.setPageSize((s.width * PT, s.height * PT))
        c.setFillColor(theme.bg)
        c.rect(0, 0, s.width * PT, s.height * PT, stroke=0, fill=1)
        c.setLineCap(1)
        c.setLineJoin(1)
        for it in s.items:
            _pdf_item(c, it, theme)
        c.showPage()
    c.save()
    return path


def _pdf_stroke(c, theme: Theme, role) -> bool:
    if not role or role == "none":
        return False
    st = theme.stroke(role)
    if st.width <= 0:
        return False
    c.setStrokeColor(st.color)
    c.setLineWidth(st.width)
    c.setDash(list(st.dash) if st.dash else [])
    return True


def _pdf_item(c, it, theme: Theme) -> None:
    if isinstance(it, Path):
        stroke = _pdf_stroke(c, theme, it.role if it.stroke else None)
        fill = bool(it.fill)
        if fill:
            c.setFillColor(theme.fill(it.fill))
        if not (stroke or fill):
            return
        p = c.beginPath()
        for ring in it.rings:
            p.moveTo(ring[0][0] * PT, ring[0][1] * PT)
            for x, y in ring[1:]:
                p.lineTo(x * PT, y * PT)
            if it.closed:
                p.close()
        c.drawPath(p, stroke=int(stroke), fill=int(fill), fillMode=0)
    elif isinstance(it, Circle):
        stroke = _pdf_stroke(c, theme, it.role)
        if it.fill:
            c.setFillColor(theme.fill(it.fill))
        c.circle(it.x * PT, it.y * PT, it.r * PT, stroke=int(stroke), fill=int(bool(it.fill)))
    elif isinstance(it, Arc):
        if _pdf_stroke(c, theme, it.role):
            r = it.r * PT
            c.arc(it.x * PT - r, it.y * PT - r, it.x * PT + r, it.y * PT + r,
                  startAng=it.a0, extent=it.a1 - it.a0)
    elif isinstance(it, Text):
        font = theme.fonts.get(it.font, theme.fonts["body"])
        c.setFillColor(theme.fill(it.role) if it.role != "text" else theme.ink)
        w = text_width(it.text, font, it.size, it.spacing) * PT
        dx = {"start": 0, "middle": -w / 2, "end": -w}[it.anchor]
        c.saveState()
        c.translate(it.x * PT, it.y * PT)
        if it.rotate:
            c.rotate(it.rotate)
        t = c.beginText(dx, 0)
        t.setFont(font, it.size)
        if it.spacing:
            t.setCharSpace(it.spacing)
        t.textOut(it.text)
        c.drawText(t)
        c.restoreState()
