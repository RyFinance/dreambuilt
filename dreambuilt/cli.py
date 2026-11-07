"""dreambuilt command line.

    dreambuilt render --text "2 story colonial 4 bed 2.5 bath 2400 sqft 70x140" -o out/
    dreambuilt render brief.yaml --options 3 -o out/
    dreambuilt render ashbury.json -o ashbury.pdf --style blueprint
    dreambuilt render --sample ashbury --all-styles -o out/
    dreambuilt check ashbury.json
    dreambuilt sample ashbury > ashbury.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import brief as briefs
from . import checks, render_pdf, render_svgs, samples, styles
from .model import dumps, from_dict, save
from .render import themes


def _brief(args):
    """A DesignBrief from --text / a brief file, optionally refined by the local model."""
    if getattr(args, "text", None):
        if args.llm:
            # the same reading the app does: rules first, the local model fills the gaps
            from . import llm
            _, b = llm.improve(args.text, args.model_path)
        else:
            b = briefs.parse_text(args.text)
    else:
        b = briefs.from_dict(yaml.safe_load(open(args.model)))
    return b


def _houses(args):
    """One or more houses: a sample, a saved model, or designs from a brief."""
    if args.sample:
        return [samples.SAMPLES[args.sample]()]
    if not args.model and not getattr(args, "text", None):
        sys.exit("give a model or brief file, --text \"...\", or --sample NAME")
    if args.model and not getattr(args, "text", None):
        data = yaml.safe_load(open(args.model))
        if not briefs.is_brief(data):
            return [from_dict(data)]
    from .design import BriefError, options
    b = _brief(args)
    print(f"brief: {b.summary()}")
    try:
        opts = options(b, getattr(args, "options", 1) or 1)
    except BriefError as e:
        sys.exit(f"can't design this brief: {e}")
    for o in opts:
        for n in o.notes[:3]:
            print(f"  note ({o.house.name}): {n}")
    return [o.house for o in opts]


def _house(args):
    return _houses(args)[0]


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-").replace("--", "-")


def cmd_render(args) -> None:
    houses = _houses(args)
    names = sorted(themes.THEMES) if args.all_styles else [args.style]
    many = args.all_styles or len(houses) > 1
    out = Path(args.output or (f"{_slug(houses[0].name)}.pdf" if not many else "out"))
    for house in houses:
        for name in names:
            path = out
            if many or out.suffix != ".pdf":
                base = out if out.suffix != ".pdf" else out.parent
                base.mkdir(parents=True, exist_ok=True)
                path = base / f"{_slug(house.name)}-{name}.pdf"
            render_pdf(house, path, style=name, date=args.date, mode=args.set)
            print(f"wrote {path}")
            if args.svg:
                folder = Path(args.svg) / _slug(house.name) / name
                render_svgs(house, folder, style=name, date=args.date, mode=args.set)
                print(f"wrote {folder}/")
        if args.save_model:
            p = Path(args.save_model)
            if len(houses) > 1:
                p = p.with_name(f"{p.stem}-{_slug(house.name)}{p.suffix or '.json'}")
            save(house, p)
            print(f"wrote {p}")


def cmd_design(args) -> None:
    """Show what the brief turns into without rendering."""
    for h in _houses(args):
        print(f"\n{h.name}: {h.heated_area:,.0f} sq ft, {len(h.bedrooms)} bed, {h.baths:g} bath")
        for lv in h.levels:
            print(f"  {lv.name}: " + ", ".join(f"{r.name} {r.w:g}x{r.h:g}" for r in lv.rooms))
        s = checks.summary(checks.run(h))
        print(f"  code pre-check: {s['pass']} pass, {s['warn']} warn, {s['fail']} fail")


def cmd_check(args) -> None:
    house = _house(args)
    found = checks.run(house)
    for f in found:
        print(f"{f.status.upper():5} {f.rule:28} {f.where:18} {f.detail}")
    s = checks.summary(found)
    print(f"\n{s['pass']} pass, {s['warn']} warn, {s['fail']} fail")
    sys.exit(1 if s["fail"] else 0)


def cmd_sample(args) -> None:
    print(dumps(samples.SAMPLES[args.name]()))


def cmd_styles(_args) -> None:
    print("Era styles:")
    for key in styles.available():
        st = styles.get(key)
        print(f"  {key:12} {st['name']} ({st['era']})")
    print("Render styles:")
    for t in themes.THEMES.values():
        print(f"  {t.name:12} {t.label}")


def cmd_get_model(args) -> None:
    from . import llm
    if llm.available():
        print(f"model already in {llm.DEFAULT_MODEL}")
        return
    print(f"downloading {llm.MODEL_REPO} (about 1.4 GB) ...")
    print("saved to", llm.get_model())


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="dreambuilt", description="Offline house concept sets.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def brief_args(p):
        p.add_argument("model", nargs="?", help="brief (.yaml) or house model (.json / .yaml)")
        p.add_argument("--sample", choices=sorted(samples.SAMPLES))
        p.add_argument("--text", help='one-line brief, e.g. "craftsman 3 bed 2 bath 1600 sqft 60x130"')
        p.add_argument("--llm", action="store_true", help="read --text with the local model")
        p.add_argument("--model-path", default=briefs.DEFAULT_MODEL, help="local MLX model folder")
        p.add_argument("--options", type=int, default=1, help="how many layout options to produce")

    r = sub.add_parser("render", help="render the concept PDF")
    brief_args(r)
    r.add_argument("-o", "--output", help="PDF path, or a folder with --all-styles")
    r.add_argument("--style", default="modern", help="modern | blueprint | patternbook")
    r.add_argument("--all-styles", action="store_true")
    r.add_argument("--svg", help="also write one SVG per sheet into this folder")
    r.add_argument("--date", help="date for the title block (default today)")
    r.add_argument("--set", choices=["rough", "full"], default="rough",
                   help="rough: brief, site, plans, roof, elevations; full adds notes + schedules")
    r.add_argument("--save-model", help="also save the generated house model (.json/.yaml)")
    r.set_defaults(fn=cmd_render)

    g = sub.add_parser("get-model", help="download the local AI model (MiniCPM5-2B, about 1.4 GB)")
    g.set_defaults(fn=cmd_get_model)

    d = sub.add_parser("design", help="design houses from a brief and list their rooms")
    brief_args(d)
    d.set_defaults(fn=cmd_design)

    c = sub.add_parser("check", help="run the informal code pre-check")
    brief_args(c)
    c.set_defaults(fn=cmd_check)

    s = sub.add_parser("sample", help="print a sample house model as JSON")
    s.add_argument("name", choices=sorted(samples.SAMPLES))
    s.set_defaults(fn=cmd_sample)

    ap_ = sub.add_parser("app", help="open the Dream Built desktop app")
    ap_.set_defaults(fn=lambda _a: sys.exit(__import__("dreambuilt.app.main", fromlist=["run"]).run([])))

    st = sub.add_parser("styles", help="list era and render styles")
    st.set_defaults(fn=cmd_styles)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
