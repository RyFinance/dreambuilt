"""Custom rules: requirements written in a small rule language, never code.

A rule is a short string `op:arg[:arg]`. Every op is something the generators can be asked
to do *and* the checker can verify on the drawing, so a rule added from a client's words
(by the phrase library or the local model) is enforced, then shown as kept or not kept.

    ensuite_each                every bedroom has its own ensuite; no shared full bath
    entry:center|left|right     where the front door sits on the facade
    open:on|off                 kitchen, family / living and dining flow into each other
    no_bath_row                 no bathrooms in a row (side by side, or only a closet apart)
    floor:ROOM:main|upper       which floor a room is on (primary, office, laundry)
    side:ROOM:front|rear        which side of the house a room faces
    near:ROOM:ROOM              two rooms share a wall or open into each other
    scale:ROOM:F                a room bigger or smaller than usual (0.7-1.6)
    exclude:FEATURE             basement, garage, porch, fireplace, office, pantry

`validate()` turns model output into rules or nothing: unknown ops, rooms or numbers are
dropped, so the model can only add requirements the engine understands.
"""
from __future__ import annotations

import re
from typing import Optional

ROOMS = {"primary", "bedroom", "kitchen", "living", "family", "dining", "office", "laundry", "mudroom",
         "pantry", "garage", "entry", "bath", "gym", "theatre"}
KIND = {"primary": "bedroom", "mudroom": "mud", "theatre": "family", "gym": "family"}
EXCLUDABLE = {"basement", "garage", "porch", "fireplace", "office", "pantry"}
OPS = {"ensuite_each": 0, "entry": 1, "open": 1, "no_bath_row": 0, "floor": 2, "side": 2, "near": 2,
       "scale": 2, "exclude": 1}


def validate(rule) -> Optional[str]:
    """A rule string in canonical form, or None when it isn't one the engine can keep."""
    if not isinstance(rule, str):
        return None
    parts = [p.strip().lower().replace(" ", "_") for p in re.split(r"[:(),]+", rule.strip()) if p.strip()]
    if not parts or parts[0] not in OPS:
        return None
    op, args = parts[0], parts[1:]
    if len(args) < OPS[op]:
        return None
    args = args[:OPS[op]]
    if op == "entry" and args[0] not in ("center", "centre", "middle", "left", "right"):
        return None
    if op == "entry":
        args = ["center" if args[0] in ("centre", "middle") else args[0]]
    if op == "open" and args[0] not in ("on", "off"):
        return None
    if op in ("floor", "side", "near", "scale") and args[0] not in ROOMS:
        return None
    if op == "floor" and args[1] not in ("main", "upper"):
        return None
    if op == "side" and args[1] not in ("front", "rear"):
        return None
    if op == "near" and args[1] not in ROOMS:
        return None
    if op == "scale":
        try:
            f = float(args[1])
        except ValueError:
            return None
        if not 0.7 <= f <= 1.6:
            return None
        args = [args[0], f"{f:g}"]
    if op == "exclude" and args[0] not in EXCLUDABLE:
        return None
    return ":".join([op] + args)


def clean(rules) -> list[str]:
    out = []
    for r in rules or []:
        v = validate(r)
        if v and v not in out:
            out.append(v)
    return out


def describe(rule: str) -> str:
    """The rule in plain words, for the app and the drawings' notes."""
    p = rule.split(":")
    return {
        "ensuite_each": lambda: "every bedroom has its own ensuite",
        "entry": lambda: f"front entrance {'in the middle' if p[1] == 'center' else 'on the ' + p[1]}",
        "open": lambda: "open floor plan" if p[1] == "on" else "separate rooms",
        "no_bath_row": lambda: "no bathrooms in a row",
        "floor": lambda: f"{p[1]} on the {p[2]} floor",
        "side": lambda: f"{p[1]} at the {p[2]}",
        "near": lambda: f"{p[1]} next to the {p[2]}",
        "scale": lambda: f"{'bigger' if float(p[2]) > 1 else 'smaller'} {p[1]}",
        "exclude": lambda: f"no {p[1]}",
    }.get(p[0], lambda: rule)()


# -- the phrase library: words -> rules, built in and learned ---------------------------

PHRASES: list[tuple[str, list[str]]] = [
    (r"ensuites? (?:bath(?:room)?s? )?only|only ensuites?|(?:all|every|each) (?:of the )?bed(?:room)?s? (?:has|have|with|gets?|get) (?:an? |their |its )?(?:own )?(?:ensuite|bath)|"
     r"ensuites? (?:in|for|with) (?:every|each|all)(?: the)? bed|no shared bath|every bedroom has its own ensuite|"
     r"private bath(?:room)?s? for (?:every|each|all)", ["ensuite_each"]),
    (r"(?:grand |front |main )?(?:middle|centre|center|central|centered|centred) (?:front )?(?:entrance|entry|door|foyer)|"
     r"(?:entrance|entry|front door) in the (?:middle|centre|center)|front entrance in the middle", ["entry:center"]),
    (r"open (?:floor )?(?:plan|concept)|open[- ]concept|no walls between|open kitchen|open floor plan", ["open:on"]),
    (r"separate rooms|closed (?:floor )?plan|no open plan|traditional layout", ["open:off"]),
    (r"no (?:two |twin )?bath(?:room)?s? (?:side by side|next to each other|in a row|parallel)|"
     r"no parallel bath(?:room)?s?|bath(?:room)?s? (?:not|never) (?:side by side|next to each other)|no bathrooms in a row", ["no_bath_row"]),
    (r"laundry (?:near|by|next to|off|beside) (?:the |my |our )?(?:primary|master)|"
     r"(?:primary|master)(?: bed(?:room)?| suite)? (?:near|by|next to) (?:the )?laundry", ["near:laundry:primary"]),
    (r"office (?:upstairs|on the (?:upper|second) floor)", ["floor:office:upper"]),
    (r"office (?:downstairs|on the (?:main|ground|first) floor)", ["floor:office:main"]),
    (r"laundry (?:upstairs|on the (?:upper|second) floor)", ["floor:laundry:upper"]),
    (r"mud ?room (?:near|by|next to|off) (?:the )?kitchen|kitchen (?:near|by|next to) (?:the )?mud ?room", ["near:mudroom:kitchen"]),
    (r"pantry (?:near|by|next to|off) (?:the )?kitchen|walk-?in pantry", ["near:pantry:kitchen"]),
    (r"(?:don'?t want|skip|without|no need for) (?:an? |the )?basement", ["exclude:basement"]),
    (r"(?:don'?t want|skip|without|no need for) (?:an? |the )?fireplace", ["exclude:fireplace"]),
    (r"(?:don'?t want|skip|without|no need for) (?:an? |the )?garage", ["exclude:garage"]),
]


# example phrasings per rule, for fuzzy matching and the model's menu
EXAMPLES: dict[str, list[str]] = {
    "ensuite_each": ["every bedroom has its own ensuite", "ensuite bathrooms only", "each room gets its own bathroom",
                     "no shared bathrooms", "private bath for every bedroom"],
    "entry:center": ["front door in the middle", "centred entrance", "grand middle entrance", "symmetrical entry"],
    "entry:left": ["front door on the left", "entrance at the left side"],
    "entry:right": ["front door on the right", "entrance at the right side"],
    "open:on": ["open floor plan", "open concept living", "no walls between kitchen and living",
                "hate walls between the kitchen and living room, one big space"],
    "open:off": ["separate rooms", "closed floor plan", "not an open concept"],
    "no_bath_row": ["no bathrooms side by side", "bathrooms not next to each other", "no parallel bathrooms"],
    "floor:office:upper": ["office upstairs", "study on the second floor"],
    "floor:office:main": ["office downstairs", "study on the main floor"],
    "floor:laundry:upper": ["laundry upstairs", "washer and dryer near the bedrooms"],
    "floor:laundry:main": ["laundry downstairs", "laundry on the main floor"],
    "floor:primary:main": ["primary bedroom downstairs", "master on the ground floor", "no stairs to my bedroom"],
    "floor:primary:upper": ["primary bedroom upstairs", "master upstairs"],
    "side:kitchen:rear": ["kitchen at the back", "kitchen facing the backyard"],
    "side:kitchen:front": ["kitchen at the front", "kitchen facing the street"],
    "side:living:rear": ["living room at the back", "living room facing the garden"],
    "side:office:front": ["office at the front", "study facing the street"],
    "near:laundry:primary": ["laundry next to the master bedroom", "laundry by my bedroom"],
    "near:mudroom:kitchen": ["mudroom next to the kitchen", "mudroom off the kitchen"],
    "near:pantry:kitchen": ["pantry off the kitchen", "walk-in pantry by the kitchen"],
    "exclude:basement": ["no basement", "no cellar"],
    "exclude:garage": ["no garage", "carport instead of a garage"],
    "exclude:fireplace": ["no fireplace"],
    "exclude:porch": ["no porch"],
}


def fuzzy_scores(clause: str) -> dict[str, float]:
    """How close the clause is to each rule's example phrasings (0-1)."""
    from difflib import SequenceMatcher
    c = " ".join(re.findall(r"[a-z]+", clause.lower()))
    out = {}
    for rule, exs in EXAMPLES.items():
        best = 0.0
        for e in exs:
            sm = SequenceMatcher(None, c, e).ratio()
            wa, wb = set(c.split()), set(e.split())
            ov = len(wa & wb) / max(len(wb), 1)
            best = max(best, sm, 0.5 * sm + 0.5 * ov)
        out[rule] = best
    return out


# a rule with a direction only counts when the clause says that direction
NEEDS = {":upper": r"upstairs|upper|second|top floor|bedroom floor|up stairs",
         ":main": r"downstairs|main|ground|first floor|lower",
         "entry:left": r"\bleft\b", "entry:right": r"\bright\b",
         "entry:center": r"middle|cent(?:er|re|ral)|symmetr",
         "open:off": r"separate|closed|not (?:an? )?open|traditional",
         "exclude:": r"\bno\b|don'?t|without|skip|instead|not\b",
         ":rear": r"back|rear|garden|yard", ":front": r"front|street"}


# a rule about a room only counts when the clause names that room
ROOM_WORDS = {"primary": r"primary|master|owner|my bedroom|our bedroom", "bedroom": r"bed(?:room)?s?|kids",
              "kitchen": r"kitchen", "living": r"living|lounge|great room", "family": r"family|great room",
              "dining": r"dining", "office": r"office|study|den\b|work from home", "laundry": r"laundry|washer|dryer",
              "mudroom": r"mud", "pantry": r"pantry", "garage": r"garage|park", "entry": r"entr|foyer|front door",
              "bath": r"bath", "gym": r"gym", "theatre": r"theat|cinema|media", "basement": r"basement|cellar",
              "fireplace": r"fireplace|hearth", "porch": r"porch|veranda"}


def plausible(rule: str, clause: str) -> bool:
    c = clause.lower()
    for key, pat in NEEDS.items():
        if (rule.endswith(key) or rule.startswith(key)) and not re.search(pat, c):
            return False
    p = rule.split(":")
    rooms = p[1:3] if p[0] in ("floor", "side") else p[1:3] if p[0] == "near" else p[1:2] if p[0] == "exclude" else []
    for room in rooms[:2] if p[0] == "near" else rooms[:1]:
        pat = ROOM_WORDS.get(room)
        if pat and not re.search(pat, c):
            return False
    return True


def fuzzy(clause: str, cutoff: float = 0.62) -> list[str]:
    """The rule whose example phrasing is closest to the clause, when close enough and the
    clause says the rule's direction (upstairs, left, separate...)."""
    sc = {r: v for r, v in fuzzy_scores(clause).items() if plausible(r, clause)}
    if not sc:
        return []
    best = max(sc, key=sc.get)
    return [best] if sc[best] >= cutoff else []


def _learned_path():
    import os
    from pathlib import Path
    return Path(os.environ.get("DREAMBUILT_HISTORY") or Path.home() / ".dreambuilt") / "learned_rules.json"


def learned() -> dict[str, list[str]]:
    """Phrases the local model turned into rules before (phrase -> rules)."""
    import json
    try:
        data = json.loads(_learned_path().read_text())
        return {k: clean(v) for k, v in data.items() if clean(v)}
    except (OSError, ValueError):
        return {}


def learn(phrase: str, rules: list[str]) -> None:
    """Remember a phrase -> rules mapping so the next brief that says it needs no model."""
    import json
    rules = clean(rules)
    phrase = " ".join(phrase.lower().split())
    if not rules or len(phrase) < 6:
        return
    data = learned()
    data[phrase] = rules
    try:
        p = _learned_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=1, sort_keys=True))
    except OSError:
        pass


def forget(phrase: str) -> None:
    import json
    data = learned()
    data.pop(" ".join(phrase.lower().split()), None)
    try:
        _learned_path().write_text(json.dumps(data, indent=1, sort_keys=True))
    except OSError:
        pass


def read_clauses(text: str, propose=None) -> list[tuple[str, list[str], str]]:
    """Rules for each clause the phrase library didn't cover: the nearest example first; then
    the model's proposals (`propose(clause) -> rules`), kept only where the clause names the
    room and direction and the examples agree at least loosely. (clause, rules, how)."""
    out = []
    for c in re.split(r"[.;\n]|,(?=\s*(?:and\s+)?(?:no|a|an|the|i|we|my|our|every|each|put|make)\b)", text.lower()):
        c = c.strip(" ,-:")
        if len(c) < 6 or len(c.split()) > 18:
            continue
        if read(c)[0]:
            continue  # the phrase library has it already
        got = fuzzy(c)
        how = "examples"
        if not got and propose is not None:
            sc = fuzzy_scores(c)
            got = [r for r in clean(propose(c)) if plausible(r, c) and sc.get(r, 0) >= 0.42]
            if len({r.split(":")[0] + ":" + (r.split(":")[1] if r.startswith(("entry", "open")) else "")
                    for r in got}) < len(got):
                got = []  # it couldn't decide (left and right): ask nothing rather than guess
            how = "model"
        if got:
            out.append((c, got, how))
    return out


def read(t: str) -> tuple[list[str], list[str]]:
    """(rules, the words they came from) from the built-in phrases, then learned ones."""
    out, used = [], []
    for pat, rules in PHRASES:
        m = re.search(pat, t)
        if m and not re.search(r"\b(?:no|not|don'?t want|without)\s+(?:an? |the )?$", t[max(0, m.start() - 15):m.start()]):
            out += rules
            used.append(m.group(0))
    for phrase, rules in learned().items():
        if phrase in t:
            out += rules
            used.append(phrase)
    if "open:on" in out and "open:off" in out:
        out.remove("open:off")
    return clean(out), used


# -- applying a rule to the brief (what the generators read) ----------------------------

def apply(b) -> None:
    """Fold the rules into the brief's ordinary fields, so every generator sees them."""
    for r in getattr(b, "rules", []) or []:
        p = r.split(":")
        if p[0] == "ensuite_each":
            b.baths = max(b.baths, b.beds + (0.5 if b.stories > 1 else 0.0))
        elif p[0] == "open" and p[1] == "on" and "open plan" not in b.features:
            b.features = sorted(set(b.features) | {"open plan"})
        elif p[0] == "floor" and p[1] == "primary":
            b.primary_floor = p[2]
        elif p[0] == "side" and p[1] in ("kitchen", "living", "family", "dining", "office", "primary"):
            key = f"{p[1]}:{p[2]}"
            if key not in b.places:
                b.places = sorted(set(b.places) | {key})
        elif p[0] == "scale":
            room = {"primary": "primary", "mudroom": "mud"}.get(p[1], p[1])
            b.sizes = {**b.sizes, room: float(p[2])}
        elif p[0] == "exclude":
            what = p[1]
            if what == "basement":
                b.basement, b.suites = False, []
            elif what == "garage":
                b.garage, b.cars = "none", 0
                b.features = sorted(set(b.features) | {"no garage"})
            b.must_haves = [m for m in b.must_haves if m != what]


# -- checking a rule on the drawing ------------------------------------------------------

def _kind(room: str) -> str:
    return KIND.get(room, room)


def _rooms(h, room: str):
    out = []
    for lv in h.all_levels:
        for r in lv.rooms:
            if room == "primary" and r.name.startswith("Primary Bedroom"):
                out.append((lv, r))
            elif room != "primary" and r.kind == _kind(room) and not r.name.startswith("Primary"):
                out.append((lv, r))
    return out


def check(h, rule: str) -> tuple[bool, str]:
    """(kept, why) for one rule on a finished design."""
    from .checks.planning import door_graph, is_ensuite
    p = rule.split(":")
    op = p[0]
    if op == "ensuite_each":
        for lv in h.all_levels:
            g = door_graph(lv)
            by = {id(r): r for r in lv.rooms}
            for r in lv.rooms:
                if r.kind != "bedroom" or r.unit:
                    continue
                own = [by[n] for n in g.get(id(r), ()) if n in by and by[n].kind == "bath"]
                if not own:
                    return False, f"{r.name} has no bath of its own"
            for r in lv.rooms:
                if r.kind == "bath" and not r.unit and not is_ensuite(r):
                    nb = {by[n].kind for n in g.get(id(r), ()) if n in by}
                    if nb & {"hall", "stair", "entry"}:
                        return False, f"{r.name} is a shared bath off the hall"
        return True, "every bedroom has its own bath"
    if op == "entry":
        lv = h.levels[0]
        door = next((o for o in lv.openings if o.kind == "door" and o.face == "S"), None)
        if door is None:
            return False, "no front door"
        x0, _, x1, _ = lv.footprint.bounds
        f = (door.start + door.width / 2 - x0) / max(x1 - x0, 1e-6)
        where = "center" if 0.38 <= f <= 0.62 else ("left" if f < 0.5 else "right")
        return where == p[1], f"front door sits {where}"
    if op == "open":
        lv = h.levels[0]
        wide = 0
        for d in lv.doors:
            if getattr(d, "kind", "") != "cased" or d.width < 8:
                continue
            a = lv.room_at(d.x, d.y - 0.3) if d.axis == "x" else lv.room_at(d.x - 0.3, d.y)
            b = lv.room_at(d.x, d.y + 0.3) if d.axis == "x" else lv.room_at(d.x + 0.3, d.y)
            if a and b and "kitchen" in (a.kind, b.kind):
                wide += 1
        ok = wide >= 1 if p[1] == "on" else wide == 0
        return ok, f"kitchen opens widely into {wide} room(s)"
    if op == "no_bath_row":
        bad = bath_rows(h)
        return not bad, ("no bathrooms in a row" if not bad else f"{bad[0][0]} and {bad[0][1]} in a row")
    if op == "floor":
        want = 0 if p[2] == "main" else 1
        rs = _rooms(h, p[1])
        ok = bool(rs) and all((h.levels.index(lv) if lv in h.levels else -1) >= 1 if want else
                              (h.levels.index(lv) if lv in h.levels else -1) == 0 for lv, _ in rs)
        return ok, f"{p[1]} on the {'main' if want == 0 else 'upper'} floor" if ok else f"{p[1]} not on the {p[2]} floor"
    if op == "side":
        rs = _rooms(h, p[1])
        for lv, r in rs:
            y0, y1 = lv.footprint.bounds[1], lv.footprint.bounds[3]
            if (p[2] == "front" and r.y <= y0 + 8) or (p[2] == "rear" and abs(r.y + r.h - y1) < 0.6):
                return True, f"{p[1]} at the {p[2]}"
        return False, f"{p[1]} not at the {p[2]}"
    if op == "near":
        from .design.details import shared_edge
        a, b = _rooms(h, p[1]), _rooms(h, p[2])
        for la, ra in a:
            for lb, rb in b:
                if la is lb:
                    e = shared_edge(ra, rb)
                    if e and e[3] - e[2] >= 2.5:
                        return True, f"{p[1]} next to the {p[2]}"
        return False, f"{p[1]} not next to the {p[2]}"
    if op == "scale":
        return True, "sized"  # applied through the program; nothing to measure against
    if op == "exclude":
        names = " ".join(r.name.lower() for lv in h.all_levels for r in lv.rooms)
        hit = {"basement": h.basement is not None, "garage": "garage" in names,
               "porch": any(pc.columns for pc in h.porches) and p[1] == "porch",
               "fireplace": bool(h.chimneys), "office": "office" in names, "pantry": "pantry" in names}[p[1]]
        return not hit, f"no {p[1]}" if not hit else f"has a {p[1]}"
    return True, ""


def bath_rows(h, direct: bool = True) -> list[tuple[str, str]]:
    """Pairs of full bathrooms in a row: sharing a wall, or with only a closet or linen
    cupboard (under 5') between them along the same band. Rental suites aside."""
    from .design.details import shared_edge
    out = []
    for lv in h.all_levels:
        baths = [r for r in lv.rooms if r.kind == "bath" and not r.unit]
        smalls = [r for r in lv.rooms if r.kind == "closet" and min(r.w, r.h) < 5.0]
        for i, a in enumerate(baths):
            for b in baths[i + 1:]:
                e = shared_edge(a, b)
                if e and e[3] - e[2] > 2.0:
                    if direct:
                        out.append((a.name, b.name))
                    continue
                for c in smalls:
                    ea, eb = shared_edge(a, c), shared_edge(b, c)
                    if ea and eb and ea[3] - ea[2] > 2.0 and eb[3] - eb[2] > 2.0 and ea[0] == eb[0]:
                        out.append((a.name, b.name))
                        break
    return out
