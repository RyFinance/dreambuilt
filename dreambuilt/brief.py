"""Briefs: what the client asks for, from YAML, a sentence, or (optionally) a local model.

    style: craftsman        # craftsman | colonial | foursquare | midcentury
    stories: 1
    beds: 3
    baths: 2                # 2.5 adds a powder room
    sqft: 1600              # heated area
    lot: 60x130             # width x depth, feet
    must_haves: [porch, mudroom, fireplace]
    name: The Linden        # optional
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from . import styles

STYLE_WORDS = {
    "craftsman": ["craftsman", "bungalow", "arts and crafts", "arts & crafts"],
    "colonial": ["colonial", "georgian", "federal", "cape cod"],
    "foursquare": ["foursquare", "four square", "four-square", "prairie box"],
    "midcentury": ["mid-century", "midcentury", "mid century", "mcm", "ranch", "modern ranch"],
    # a place is not a style: "a house in Surrey" says where, "Surrey-style" says what
    "westcoast": ["west coast", "westcoast", "vancouver special", "modern estate", "estate home",
                  "surrey style", "surrey-style", "surrey estate", "surrey mansion"],
    "farmhouse": ["farmhouse", "farm house", "barndominium", "country house"],
    "mediterranean": ["mediterranean", "spanish", "tuscan", "hacienda", "villa", "mission style", "santa barbara"],
    "tudor": ["tudor", "english cottage", "storybook", "half-timber", "half timber"],
    "scandinavian": ["scandinavian", "scandi", "nordic", "swedish", "norwegian", "danish"],
    "japanese": ["japanese", "japandi", "zen house", "ryokan", "wabi-sabi", "wabi sabi"],
    "modern": ["modern", "contemporary", "minimalist", "minimal", "box house"],
}
MUST_HAVES = {
    "porch": ["porch", "veranda"],
    "mudroom": ["mudroom", "mud room"],
    "fireplace": ["fireplace", "hearth", "chimney"],
    "office": ["office", "study", "den"],
    "upstairs laundry": ["upstairs laundry", "laundry upstairs", "second floor laundry",
                         "second-floor laundry"],
    "pantry": ["pantry"],
    "bonus room": ["bonus room", "playroom", "rec room"],
    "family room": ["family room", "great room"],
    "garage": ["garage", "car garage"],
    "spice kitchen": ["spice kitchen", "wok kitchen", "second kitchen"],
    "balcony": ["balcony", "deck off the primary"],
}
# design features: anything that changes the look or the plan beyond rooms and sizes
FEATURES = {
    "flat roof": ["flat roof", "flat-roof", "flat roofs"],
    "gable roof": ["gable roof", "gabled roof", "gables"],
    "hip roof": ["hip roof", "hipped roof"],
    "shed roof": ["shed roof", "skillion", "butterfly roof"],
    "big windows": ["big windows", "large windows", "floor-to-ceiling", "floor to ceiling",
                    "window wall", "walls of glass", "lots of glass", "black-framed windows",
                    "black framed windows", "oversized windows", "lots of light", "natural light"],
    "stone": ["stone", "rock face", "ledgestone"],
    "wood": ["wood", "cedar", "timber", "natural wood", "wood panel", "wood siding"],
    "brick": ["brick"],
    "board and batten": ["board and batten", "board & batten", "batten"],
    "stucco": ["stucco", "render", "smooth white"],
    "3-car garage": ["3 car", "3-car", "three car", "triple garage", "triple car"],
    "no garage": ["no garage", "without a garage", "without garage", "carport only"],
    "covered patio": ["covered patio", "outdoor kitchen", "covered deck", "outdoor living", "patio"],
    "roof terrace": ["rooftop terrace", "roof terrace", "roof deck", "rooftop deck", "rooftop patio"],
    "townhouse": ["townhouse", "town house", "row house", "rowhouse", "zero lot line", "infill"],
    "strict lot": ["do not ignore the lot", "invent additional land", "must physically fit",
                   "strictly limited", "respect the available property", "do not invent land"],
    "vaulted": ["vaulted", "double-height", "double height", "high ceilings", "tall ceilings",
                "open to below"],
    "theatre": ["theatre", "theater", "media room", "home cinema", "movie room"],
    "gym": ["gym", "fitness", "workout"],
    "wet bar": ["wet bar", "bar area", "basement bar"],
    "wine room": ["wine room", "wine cellar", "wine storage"],
    "open plan": ["open plan", "open concept", "open floor", "open-concept", "open layout"],
    "wide": ["wider than", "wide and shallow", "wider house", "make it wider", "more width"],
    "symmetrical": ["symmetrical", "symmetric", "balanced facade"],
    "dormers": ["dormer", "dormers"],
    "rear addition": ["rear addition", "bigger main floor", "one-storey section", "single storey section",
                      "main floor bigger", "stepped back upper", "smaller upper floor"],
    "grand entrance": ["grand entrance", "grand entry", "grand foyer", "double-height entry", "double height entry",
                       "two-storey entry", "two storey entry", "double doors", "double front door", "statement entry",
                       "impressive entrance", "grander entrance"],
}

WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "single": 1}


@dataclass
class DesignBrief:
    style: str = "craftsman"  # craftsman | colonial | foursquare | midcentury | westcoast
    stories: int = 1
    beds: int = 3
    baths: float = 2.0
    sqft: int = 1600
    lot_width: float = 60.0
    lot_depth: float = 130.0
    must_haves: list[str] = field(default_factory=list)
    name: Optional[str] = None
    basement: bool = False
    suites: list[int] = field(default_factory=list)  # bedrooms in each basement rental suite
    features: list[str] = field(default_factory=list)  # FEATURES keys: roof, cladding, rooms...
    garage: str = "auto"         # auto | front | side | none
    cars: int = 0                # 0: what fits
    primary_floor: str = "auto"  # auto | main | upper
    ceiling: float = 0.0         # main-floor ceiling height, ft (0: the style's)
    notes: list[str] = field(default_factory=list)  # asks the designer doesn't understand yet
    basement_sqft: int = 0       # a basement of this size (0: under the whole house)
    wishes: list[str] = field(default_factory=list)  # the small things: finishes, palette, lighting...
    places: list[str] = field(default_factory=list)  # "kitchen:rear", "office:front": where rooms go
    sizes: dict = field(default_factory=dict)  # room -> scale: {"kitchen": 1.25, "office": 0.8}
    rules: list[str] = field(default_factory=list)  # custom rules (custom_rules.py): "ensuite_each", "entry:center"

    def wants(self, feature: str) -> bool:
        return feature in self.features

    def validate(self) -> list[str]:
        """Problems that make the brief unbuildable; empty when fine."""
        out = []
        if self.style not in styles.available():
            out.append(f"unknown style {self.style!r}; choose from {styles.available()}")
        if not 1 <= self.stories <= 3:
            out.append("stories must be 1-3")
        if not 1 <= self.beds <= 7:
            out.append("beds must be 1-7")
        if not 1 <= self.baths <= 8:
            out.append("baths must be 1-8")
        per_floor = self.sqft / max(self.stories, 1)
        if per_floor < 450:
            out.append(f"{self.sqft} sq ft over {self.stories} floors is under 450 per floor")
        if self.sqft > 8000:
            out.append("sqft over 8,000 is out of range for v1")
        need = 380 + 150 * self.beds + 45 * self.baths
        if self.sqft < need * 0.8:
            out.append(f"{self.beds} bed / {self.baths:g} bath needs roughly {need:.0f}+ sq ft")
        return out

    def has(self, item: str) -> bool:
        return item in self.must_haves

    def summary(self) -> str:
        mh = ", ".join(self.must_haves) or "none"
        base = ""
        if self.basement:
            base = " + basement" + (f" with {' and '.join(f'{n}-bed' for n in self.suites)} rental suite"
                                    f"{'s' if len(self.suites) > 1 else ''}" if self.suites else "")
        feats = f"; features: {', '.join(self.features)}" if self.features else ""
        lay = []
        if self.garage != "auto" or self.cars:
            lay.append(f"garage: {self.garage}{f' {self.cars}-car' if self.cars else ''}")
        if self.primary_floor != "auto":
            lay.append(f"primary on the {self.primary_floor} floor")
        if self.ceiling:
            lay.append(f"{self.ceiling:g}' ceilings")
        feats += ("; " + ", ".join(lay)) if lay else ""
        return (f"{styles.get(self.style)['name']}, {self.stories} stor{'y' if self.stories == 1 else 'ies'}{base}, "
                f"{self.beds} bed / {self.baths:g} bath, {self.sqft:,} sq ft, "
                f"{self.lot_width:g}' x {self.lot_depth:g}' lot; must-haves: {mh}{feats}")


def parse_lot(text: str) -> tuple[float, float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*'?\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)", str(text), re.I)
    if not m:
        raise ValueError(f"lot should look like 60x130, got {text!r}")
    return float(m.group(1)), float(m.group(2))


def from_dict(d: dict) -> DesignBrief:
    d = dict(d)
    b = DesignBrief()
    if "lot" in d:
        b.lot_width, b.lot_depth = parse_lot(d.pop("lot"))
    for k, v in d.items():
        if k in ("style",):
            b.style = normalize_style(str(v)) or str(v).lower()
        elif k == "must_haves":
            b.must_haves = [normalize_must(x) for x in (v or [])]
        elif k in ("stories", "beds", "sqft"):
            setattr(b, k, int(v))
        elif k == "baths":
            b.baths = float(v)
        elif k in ("lot_width", "lot_depth"):
            setattr(b, k, float(v))
        elif k == "name":
            b.name = v
        elif k == "basement":
            b.basement = bool(v)
        elif k == "suites":
            b.suites = [int(x) for x in (v or [])]
            b.basement = b.basement or bool(b.suites)
        elif k == "features":
            b.features = [normalize_feature(x) for x in (v or []) if normalize_feature(x)]
        elif k in ("garage", "primary_floor"):
            setattr(b, k, str(v))
        elif k == "cars":
            b.cars = int(v)
        elif k == "basement_sqft":
            b.basement_sqft = int(v)
        elif k == "ceiling":
            b.ceiling = float(v)
        elif k == "notes":
            b.notes = [str(x) for x in (v or [])]
        elif k == "wishes":
            b.wishes = [str(x) for x in (v or [])]
        elif k == "places":
            b.places = [str(x) for x in (v or [])]
        elif k == "sizes":
            b.sizes = {str(a): float(c) for a, c in (v or {}).items()}
        elif k == "rules":
            from .custom_rules import clean
            b.rules = clean(v)
        else:
            raise ValueError(f"unknown brief field {k!r}")
    return b


def load(path: str | Path) -> DesignBrief:
    data = yaml.safe_load(Path(path).read_text())
    return from_dict(data)


def is_brief(data: dict) -> bool:
    return isinstance(data, dict) and "levels" not in data and ("beds" in data or "sqft" in data)


def normalize_style(text: str) -> Optional[str]:
    t = text.lower()
    # "Surrey craftsman" / "west coast modern" is the West Coast house with that trim
    if any(w in t for w in STYLE_WORDS["westcoast"]) and not re.search(r"\bnot (?:a |the )?(?:surrey|west coast)", t):
        return "westcoast"
    # "Surrey two-storey", "Surrey modern house": the place used as a style word. "A house in
    # Surrey" is only where it is, and says nothing about how it looks.
    if re.search(r"(?<!\bin )(?<!\bnear )(?<!\bat )(?<!\bfrom )(?<!\bof )\bsurrey\s+(?:style|estate|mansion|special|"
                 r"modern|craftsman|west|home|house|two|three|single|one|2|3)\b", t):
        return "westcoast"
    if "modern ranch" in t or "mid-century modern" in t or "mid century modern" in t:
        return "midcentury"
    if "modern farmhouse" in t:
        return "farmhouse"
    # a named style beats a generic word ("scandinavian bungalow" is Scandinavian)
    generic = {"bungalow", "country house", "villa", "cottage", "rancher", "ranch"}
    for pass_ in (0, 1):
        for key, words in STYLE_WORDS.items():
            if key == "modern":
                continue
            if any(w in t for w in words if pass_ or w not in generic):
                return key
    if any(re.search(rf"\b{w}\b", t) for w in STYLE_WORDS["modern"]):
        return "modern"
    return None


def normalize_feature(text: str) -> Optional[str]:
    t = str(text).lower().strip()
    if t in FEATURES:
        return t
    for key, words in FEATURES.items():
        if any(w in t for w in words):
            return key
    return None


def clean_text(text: str) -> str:
    """Markdown and pasted prompts down to plain words: no headings, bullets or bold."""
    t = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    t = re.sub(r"^\s*(?:[-*\u2022]|\d+\.)\s+", "", t, flags=re.M)
    t = t.replace("**", "").replace("__", "").replace("`", "")
    return re.sub(r"[ \t]+", " ", t).strip()


def _near_lot(t: str, start: int, end: int) -> bool:
    return bool(re.search(r"\blot\b|\bproperty\b|\bsite\b|\bparcel\b|\bplot\b", t[max(0, start - 30):end + 40]))


def _lot_from_area(area: float) -> tuple[float, float]:
    """A lot of this many square feet, shaped like a typical suburban lot (about 1:2.2)."""
    w = round((area / 2.2) ** 0.5 / 2) * 2
    return float(w), float(round(area / w / 5) * 5)


def normalize_must(text: str) -> str:
    t = str(text).lower().strip()
    for key, words in MUST_HAVES.items():
        if any(w in t for w in words):
            return key
    return t


NEGATE = re.compile(r"\b(?:no|not|don'?t|do not|never|without|avoid|cannot|can'?t|nor)\b")
INTERIOR = re.compile(r"countertop|cabinet|flooring|floors?\b|interior|furniture|tile|mirror|vanity|palette|backsplash|oak")
EXTERIOR_ONLY = {"stone", "wood", "brick", "stucco", "board and batten"}


def _affirmed(t: str, word: str, key: str) -> bool:
    """The word is asked for: present in a clause that doesn't negate it (and, for outside
    finishes, isn't about the interior: stone countertops aren't a stone facade)."""
    for m in re.finditer(re.escape(word), t):
        a = max(t.rfind(c, 0, m.start()) for c in ".;\n*") + 1
        ends = [i for i in (t.find(c, m.end()) for c in ".;\n") if i >= 0]
        clause = t[a:min(ends) if ends else len(t)]
        # a negation reaches only the word itself or one filler before it ("no garage",
        # "without a garage"); "no walls office" keeps the office
        before = t[a:m.start()].split()[-2:]
        fillers = {"a", "an", "the", "any", "big", "large", "small", "separate", "attached", "extra"}
        if re.search(r"(?:not (?:a )?(?:big |huge )?fan of|don'?t (?:like|want|need)|dislike|hate|no need for)"
                     r"\s+(?:[a-z-]+\s+){0,2}$", t[a:m.start()]):
            continue
        if before and (NEGATE.fullmatch(before[-1]) or
                       (len(before) == 2 and before[-1] in fillers and NEGATE.fullmatch(before[0]))):
            continue
        if key in EXTERIOR_ONLY and INTERIOR.search(clause):
            continue
        if key in ("office", "garage", "bonus room") and re.search(r"\bif (?:space|room)|or flexible|cannot fit", clause) \
                and key != "office":
            continue
        return True
    return False


def _read_sizes(t: str) -> dict:
    """House size and lot from the words: "3,000 sq ft", "3k house", "10k lot",
    "7,000 sq ft lot", "50 x 120 lot", "a 50 foot lot". Room sizes like 18' x 20' are ignored."""
    out = {}
    num = r"(\d{1,2}(?:,\d{3})|\d{3,5}|\d{1,2}(?:\.\d)?\s*k)"
    for m in re.finditer(num + r"\s*(?:sq\.?\s*f(?:ee)?t|sf|square\s*f(?:ee|oo)t|sqft|sq\b)?\s*(\w+)?", t):
        raw, nxt = m.group(1).replace(",", "").replace(" ", ""), (m.group(2) or "")
        unit = m.group(0)[len(m.group(1)):]
        has_unit = bool(re.search(r"sq|sf|square", unit))
        is_k = raw.endswith("k")
        if not (has_unit or is_k):
            continue
        val = float(raw[:-1]) * 1000 if is_k else float(raw)
        after = t[m.end() - len(nxt): m.end() + 12]
        if re.match(r"\s*(?:lot|property|land|yard)", after) or nxt in ("lot", "property", "land"):
            if 2000 <= val <= 60000:
                out.setdefault("lot_area", val)
        elif 500 <= val <= 12000 and "sqft" not in out and not (val <= 2500 and (
                re.match(r"\s*(?:of\s+)?(?:a\s+)?(?:finished\s+|unfinished\s+)?basement",
                         t[(m.start(2) if m.group(2) else m.end()):]) or
                re.search(r"basement\s*(?:of|:|is|at|about)?\s*$", t[max(0, m.start() - 20):m.start()]))):
            out["sqft"] = int(val)  # (a "600 sq ft basement" is the basement's size, not the house's)
    mw = re.search(r"\bwidth\s*:?\s*(\d{1,3}(?:\.\d)?)\s*(?:'|ft|feet|foot)", t)
    md = re.search(r"\bdepth\s*:?\s*(\d{1,3}(?:\.\d)?)\s*(?:'|ft|feet|foot)", t)
    if mw and md and re.search(r"\b(?:lot|property|site|parcel|plot)\b", t):
        out["lot"] = (float(mw.group(1)), float(md.group(1)))
    for m in re.finditer(r"(\d{1,3})\s*(?:'|ft|feet|foot)?\s*(?:x|by|\u00d7)\s*(\d{1,3})\s*(?:'|ft|feet|foot)?", t):
        if "lot" in out:
            break
        w, d = float(m.group(1)), float(m.group(2))
        near = _near_lot(t, m.start(), m.end())
        # a lot is at least 25' wide and deeper than it is narrow, unless the words say it's the
        # lot ("an 18 x 20 property"); otherwise "18' x 20'" is a room
        # (nothing 50' deep is a room: "20 x 80" is a narrow lot; a townhouse's "18 x 40" too)
        town = re.search(r"\b(?:townhouse|town house|row ?house|infill|narrow lot)", t)
        if (near and 10 <= w <= 250 and 10 <= d <= 500) or (25 <= w <= 250 and 60 <= d <= 500 and w >= 33) \
                or (14 <= w <= 250 and 50 <= d <= 500) or (town and 12 <= w <= 40 and 18 <= d <= 200):
            out["lot"] = (w, d)
            break
    if "lot" not in out:
        if m := re.search(r"(\d{2,3})\s*(?:'|-?\s*(?:ft|foot|feet))\s*(?:wide\s*)?lot", t):
            if 25 <= float(m.group(1)) <= 250:
                out["lot_width"] = float(m.group(1))
    return out


# features each style can take on its own (the client can always ask for anything)
STYLE_FEATURES = {
    "modern": {"big windows", "wood", "stone", "stucco", "covered patio", "vaulted", "flat roof"},
    "westcoast": {"stone", "stucco", "big windows", "covered patio", "vaulted", "3-car garage", "hip roof"},
    "craftsman": {"stone", "wood", "board and batten", "covered patio", "gable roof"},
    "colonial": {"brick", "gable roof", "symmetrical"},
    "foursquare": {"brick", "hip roof", "covered patio"},
    "midcentury": {"big windows", "wood", "flat roof", "covered patio", "vaulted"},
    "farmhouse": {"board and batten", "big windows", "covered patio", "vaulted", "gable roof"},
    "mediterranean": {"stucco", "stone", "covered patio", "hip roof"},
    "tudor": {"brick", "gable roof"},
    "scandinavian": {"wood", "big windows", "gable roof"},
    "japanese": {"wood", "covered patio", "hip roof"},
}


def default_lot(sqft: int, stories: int, style: str) -> tuple[float, float]:
    """A lot that suits the house when the client didn't give one."""
    foot = sqft / max(stories, 1)
    w = max(40.0, min(80.0, round((foot ** 0.5 * 1.25 + 14) / 2) * 2))
    if style == "westcoast":
        w = min(w, 66.0)
    return w, max(110.0, min(160.0, round(w * 2.2 / 5) * 5))


PLACE_ROOMS = {"kitchen": "kitchen", "living room": "living", "living": "living", "great room": "family",
               "family room": "family", "dining": "dining", "office": "office", "den": "office",
               "primary bedroom": "primary", "master bedroom": "primary", "primary": "primary", "master": "primary"}
PLACE_SIDES = {"back": "rear", "backyard": "rear", "rear": "rear", "yard": "rear", "garden": "rear",
               "front": "front", "street": "front"}
PLACE_RE = re.compile(r"\b(kitchen|living room|living|great room|family room|dining|office|den|primary bedroom|"
                      r"master bedroom|primary|master)\b(?:(?!\band\b|\bwith\b)[^.;,\n]){0,25}?\b(?:facing|at|on|toward|towards|"
                      r"overlooking|to|in|near|by)\s+(?:the\s+)?(back|backyard|rear|yard|garden|front|street)\b")


SIZE_SCALE = {"tiny": 0.75, "small": 0.8, "little": 0.8, "compact": 0.8, "cozy": 0.85, "modest": 0.9,
              "big": 1.25, "large": 1.25, "spacious": 1.3, "generous": 1.25, "oversized": 1.4,
              "huge": 1.5, "massive": 1.5, "giant": 1.5, "grand": 1.35, "chef's": 1.3, "gourmet": 1.3,
              "spa": 1.35, "spa-like": 1.35, "luxurious": 1.3, "luxury": 1.3}
SIZE_ROOMS = {"kitchen": "kitchen", "living room": "living", "living": "living", "great room": "family",
              "family room": "family", "dining room": "dining", "dining": "dining", "office": "office",
              "study": "office", "den": "office", "primary bedroom": "primary", "master bedroom": "primary",
              "primary suite": "primary", "master suite": "primary", "primary": "primary", "master": "primary",
              "bedrooms": "bedroom", "bedroom": "bedroom", "garage": "garage", "mudroom": "mud", "mud room": "mud",
              "pantry": "pantry", "laundry": "laundry", "laundry room": "laundry", "foyer": "entry",
              "entry": "entry", "bathrooms": "bath", "ensuite": "primary_bath", "walk-in": "wic",
              "walk in closet": "wic", "closet": "wic"}
SIZE_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in SIZE_SCALE) + r")\s+(?:open\s+)?(" +
                     "|".join(sorted((re.escape(k) for k in SIZE_ROOMS), key=len, reverse=True)) + r")\b")


def read_sizes_words(t: str) -> dict:
    """"big kitchen", "small office", "huge primary suite": a scale per room."""
    out = {}
    for m in SIZE_RE.finditer(t):
        out[SIZE_ROOMS[m.group(2)]] = SIZE_SCALE[m.group(1)]
    return out


def read_places(t: str) -> list[str]:
    out = []
    for m in PLACE_RE.finditer(t):
        p = f"{PLACE_ROOMS[m.group(1)]}:{PLACE_SIDES[m.group(2)]}"
        if p not in out:
            out.append(p)
    return out


def _read_layout(t: str, b: DesignBrief) -> None:
    """Where things go: garage position and size, primary-bedroom floor, ceiling height."""
    if re.search(r"\bno garage\b|without (?:a )?garage", t):
        b.garage, b.cars = "none", 0
    elif re.search(r"side[- ]?(?:load|entry)?\s*garage|garage (?:on|at|to) the side|attached garage", t):
        b.garage = "side"
    elif re.search(r"(?:front|forward)[- ]?(?:load|facing)?\s*garage|garage (?:out |up )?(?:front|forward)|garage pushed", t):
        b.garage = "front"
    if m := re.search(r"(\d)\s*-?\s*car", t):
        b.cars = int(m.group(1))
        if b.garage == "none":
            b.garage = "auto"
    if re.search(r"(?:primary|master)(?: bed(?:room)?| suite)?\s+(?:on|at)\s+(?:the\s+)?(?:main|ground|first)\b|"
                 r"main[- ]floor (?:primary|master)", t):
        b.primary_floor = "main"
    elif re.search(r"(?:primary|master)(?: bed(?:room)?| suite)?\s+(?:on|at)\s+(?:the\s+)?(?:upper|second|top|up)", t):
        b.primary_floor = "upper"
    if m := re.search(r"basement[^.;,\n]{0,25}?(\d{3,4})\s*(?:sq|sf|square)|(\d{3,4})\s*(?:sq\.?\s*f(?:ee)?t|sf|sqft|square feet)\s*(?:of\s+)?basement", t):
        v = int(m.group(1) or m.group(2))
        # (a basement over 2,500 sq ft isn't a basement size: "5000 sq ft basement theatre gym"
        # is a 5,000 sq ft house with a basement)
        if 200 <= v <= 2500:
            b.basement_sqft, b.basement = v, True
        elif v > 2500:
            b.basement = True
    elif re.search(r"\bsmall basement\b|\bpartial basement\b", t):
        b.basement = True
        b.basement_sqft = b.basement_sqft or 600
    if m := re.search(r"(\d{1,2})\s*(?:'|ft|foot|feet)?\s*-?\s*(?:high |tall )?ceilings?", t):
        v = float(m.group(1))
        if 8 <= v <= 20:
            b.ceiling = v


# words every brief uses, so a clause made only of these isn't an unknown ask
_KNOWN = re.compile(
    r"\b(?:\d|bed|bath|storey|story|stories|floor|sq|square|ft|feet|foot|lot|basement|suite|rental|garage|"
    r"car|style|house|home|with|and|the|a|an|for|of|in|on|plus|want|need|like|please|make|build|design|"
    r"modern|craftsman|colonial|foursquare|mid|century|west|coast|surrey|contemporary|bungalow|rancher|ranch|"
    r"cottage|family|big|small|large|luxury|primary|master|ceiling|level|main|upper|kitchen|living|dining|"
    r"great room|open|room|bedrooms?|bathrooms?|one|two|three|four|five|practical|full|secondary|"
    r"space|integrated|permits|depending|available|if|or|into|to|be|spa|ensuite|other|are|upstairs|"
    r"downstairs|is|not|separate|wing|built|inside|them|of|it)\b")


def sync_garage(b: DesignBrief) -> DesignBrief:
    """The garage fields and the garage words in must-haves / features say the same thing."""
    if "no garage" in b.features:
        b.garage, b.cars = "none", 0
    if "3-car garage" in b.features and not b.cars:
        b.cars = 3
    if b.garage == "none":
        b.must_haves = [m for m in b.must_haves if m != "garage"]
        b.features = sorted(set(b.features) - {"3-car garage"} | {"no garage"})
    else:
        b.features = [f for f in b.features if f not in ("no garage", "3-car garage")]
        if b.cars >= 3:
            b.features = sorted(set(b.features) | {"3-car garage"})
    return b


SMALL = re.compile(r"finish|colou?r|palette|white|beige|grey|gray|black|charcoal|oak|wood|lighting|light|"
                   r"flooring|cabinet|countertop|landscap|screen|mirror|furniture|wardrobe|built-in|storage|"
                   r"entrance|roofline|window|minimal|seating|appliance|clutter|materials|accent|"
                   r"television|entertainment|\btv\b", re.I)
META = re.compile(r"\b(?:plan|elevation|visuali[sz]ation|perspective|show|dimension|setback|regulation|"
                  r"legal|zoning|requirement|deliverable|measurement|accurate|produce|explain|act as|objective)", re.I)


SMALL_HEAD = re.compile(r"^\W*(?:the\s+)?(?:small|little|other|finer)?\s*(?:things|details|finishes|touches|extras|"
                        r"wishes|nice[- ]to[- ]haves?)\s*:\s*", re.I)


def small_things(text: str) -> list[str]:
    """The details that don't change the plan but matter to the client (finishes, colours,
    lighting, built-ins, landscaping), kept so they reach the drawings' notes."""
    out = []
    for line in re.split(r"\n", text):
        # "Small things: oak floors, black frames, ...": every item on a list the client labelled
        m = SMALL_HEAD.match(clean_text(line))
        if not m:
            continue
        for item in re.split(r",|;|\.\s|\band\b(?=[^,]*$)", clean_text(line)[m.end():]):
            item = item.strip(" .;:-*\u2022").strip()
            if 3 <= len(item) <= 70 and not re.match(r"(?:not a fan|no |don'?t|never)", item, re.I) \
                    and item.lower() not in (o.lower() for o in out):
                out.append(item)
    for line in re.split(r"\n|(?<=[.;])\s+", text):
        if SMALL_HEAD.match(clean_text(line)):
            continue
        item = clean_text(line).strip(" .;:-*\u2022").strip()
        if not (3 <= len(item) <= 70) or META.search(item) or not SMALL.search(item):
            continue
        if re.search(r"\b(?:bed|bath|lot|width|depth|floors?\b|basement|garage|storey|story)", item, re.I):
            continue
        if item.lower() not in (o.lower() for o in out):
            out.append(item)
    return out[:30]


DESIGN_NOUNS = re.compile(
    r"closet|suite|ensuite|room|kitchen|island|ceiling|stair|window|door|deck|porch|patio|yard|garden|pool|"
    r"court|hall|laundry|pantry|bath|bed|floor|level|wing|loft|attic|terrace|balcony|garage|driveway|fireplace|"
    r"office|den|library|gym|spa|sauna|elevator|lift|accessible|wheelchair|foyer|entry|entrance|roof|wall|"
    r"storage|shop|studio|nook|bar|cellar|courtyard|view|light|aging")


def unknown_asks(text: str) -> list[str]:
    """Clauses of the brief that matched nothing the designer reads, so they can be shown
    back as not understood instead of silently dropped."""
    out = []
    for c in re.split(r"[,.;\n]|\band\b|\bwith\b", clean_text(text).lower()):
        c = c.strip(" -:")
        if len(c) < 4 or len(c.split()) < 2:
            continue
        hit = any(w in c for words in list(MUST_HAVES.values()) + list(FEATURES.values()) for w in words) or \
            any(w in c for words in STYLE_WORDS.values() for w in words)
        if hit:
            continue
        if META.search(c) or re.search(r"\b(?:designer|architect|constraints?|objective|aim|prioriti[sz]e|"
                                        r"consider|features?|layout|dimensions?|account|determine|assume|"
                                        r"respect|ensure|maximi[sz]e|minimi[sz]e|unless|feasible|footprint|"
                                        r"area|maximum|lot|basement|floors?)\b", c) or c.endswith(":"):
            continue
        if SMALL.search(c) or re.search(r"\b(?:look|should|avoid|feel)\b", c):
            continue  # a finish or a mood: kept with the small things, not an unmet ask
        if not DESIGN_NOUNS.search(c):
            continue  # chatter ("for me and my girl", "nothing crazy"), not an ask
        if re.search(r"walk[- ]?in closets?|\b\d+(?:\.5)? (?:beds?|baths?)\b|ensuites? (?:in|for|with) (?:every|each|all)|"
                     r"(?:single|one)[- ]level|no stairs|aging in place|and a half|half bath", c):
            continue  # walk-ins come with every primary; counts were read
        rest = _KNOWN.sub(" ", c)
        if len(re.findall(r"[a-z]{3,}", rest)) >= 2:  # real words left over: something we don't read
            out.append(c)
    return out[:6]


SIZE_WORDS = [(r"\b(?:luxury|mansion|estate|executive)\b|\bgrand (?:house|home|estate|place|build)\b", 4500),
              (r"\b(?:big|large|spacious|huge)(?:\s+(?:ahh|family|modern|new))?\s+(?:house|home|place|build|crib)\b", 3600),
              (r"\b(?:small|starter|tiny|compact|cozy|cosy|lil|little)(?:\s+\w+)?\s+(?:house|home|place|cottage|crib|bungalow|build)\b", 1300)]


def parse_text(text: str, base: Optional[DesignBrief] = None) -> DesignBrief:
    """Rule-based reading of a one-line brief. Fields it can't find keep their defaults."""
    b = base or DesignBrief()
    beds_before = b.beds
    t = " " + re.sub(r",(?!\d{3})", " ; ", clean_text(text).lower()) + " "
    for w, n in WORD_NUMS.items():
        t = re.sub(rf"\b{w}\b", str(n), t)
    t = re.sub(r"\b(\d)\s+and\s+(?:a\s+)?half\b", r"\1.5", t)  # "three and a half baths"
    t = re.sub(r"\b(?:double|2[- ]?car)\s+garage", "2-car garage", t)
    t = re.sub(r"\b(?:triple|3[- ]?car)\s+garage", "3-car garage", t)
    t = re.sub(r"\bsingle\s+(?:car\s+)?garage", "1-car garage", t)
    style = normalize_style(t)
    if style:
        b.style = style
    if m := re.search(r"(\d)\s*(?:-|\s)?\s*(?:stor(?:y|ey|ies|eys)|floors?|levels?)\b", t):
        b.stories = int(m.group(1))
    elif "ranch" in t or "bungalow" in t:
        b.stories = 1
    if m := re.search(r"(\d)\s*(?:-|\s)?\s*(?:bed(?:room)?s?|br|bd)\b", t):
        b.beds = int(m.group(1))
    elif adj := re.findall(r"\b(\d)\s+(?:[a-z-]+\s+){1,2}bed(?:room)?s?\b", t):
        b.beds = sum(int(x) for x in adj)  # "1 primary bedroom ... 1 secondary bedroom"
    if m := re.search(r"(\d(?:\.5)?)\s*(?:-|\s)?\s*(?:bath(?:room)?s?|ba)\b", t):
        b.baths = float(m.group(1))
    elif adj := re.findall(r"\b(\d)\s+(?:[a-z-]+\s+){1,2}bath(?:room)?s?\b", t):
        b.baths = float(sum(int(x) for x in adj))
    if m := re.search(r"max(?:imum)?\s+(?:floors|storeys|stories|levels)\s*:?\s*(\d)", t):
        b.stories = int(m.group(1))
    sizes = _read_sizes(t)
    if "sqft" in sizes:
        b.sqft = sizes["sqft"]
    elif base is None:
        for pat, size in SIZE_WORDS:
            if re.search(pat, t):
                b.sqft = size
                b._sized_by = "words"  # "luxury", "lil": the client's own sense of size
                break
    if "lot" in sizes:
        b.lot_width, b.lot_depth = sizes["lot"]
    elif "lot_area" in sizes:
        b.lot_width, b.lot_depth = _lot_from_area(sizes["lot_area"])
    elif "lot_width" in sizes:
        b.lot_width = sizes["lot_width"]  # "a 50 foot lot": the width; depth stays
    feats = [k for k, words in FEATURES.items() if any(_affirmed(t, w, k) for w in words)]
    if re.search(r"\bno (?:basement|suite)", t):
        feats = [f for f in feats if f not in ("theatre", "gym", "wet bar", "wine room")]
    if feats:
        b.features = sorted(set(b.features) | set(feats))
    if "no garage" in b.features:
        b.must_haves = [m for m in b.must_haves if m != "garage"]
    if re.search(r"(?:invent|no room for|cannot (?:physically )?fit|can'?t fit)[^.\n]{0,60}garage|garage[^.\n]{0,30}cannot (?:physically )?fit", t):
        b.features = sorted(set(b.features) | {"no garage"})
    if "sqft" not in sizes and ("lot" in sizes or "lot_area" in sizes) and base is None:
        # no size given: the most the lot can hold, not a size word's guess
        cover = b.lot_width * b.lot_depth * (0.75 if "townhouse" in b.features or b.lot_width < 30 else 0.4)
        b.sqft = int(min(b.sqft, max(300, cover * b.stories)))
    _read_layout(t, b)
    sync_garage(b)
    places = read_places(t)
    if places:
        b.places = sorted(set(b.places) | set(places))
    rs = read_sizes_words(t)
    if rs:
        b.sizes = {**b.sizes, **rs}
        if "garage" in rs and not b.cars and b.garage != "none":
            b.cars = 3 if rs["garage"] > 1 else 1
            b.must_haves = sorted(set(b.must_haves) | {"garage"})
    if base is None:
        b.notes = [n for n in unknown_asks(text) if not read_places(n)]
        b.wishes = small_things(text)
    found = []
    for key, words in MUST_HAVES.items():
        if any(_affirmed(t, w, key) for w in words):
            found.append(key)
    if "no garage" in b.features and "garage" in found:
        found.remove("garage")
    if found:
        b.must_haves = sorted(set(b.must_haves) | set(found))
    # basement and rental suites: "2-bed and 1-bed rental suites", "a 1 bedroom suite", "basement"
    # basement and rental suites: "2-bed and 1-bed rental suites", "a 1 bedroom suite", "basement"
    bed_pat = r"(\d)\s*-?\s*(?:bed(?:room)?s?|br|bd)\b"
    suites, own = [], None
    ms = list(re.finditer(bed_pat, t))
    flags = []
    for i, m in enumerate(ms):
        # the words after "N bed", up to the next number or the end of the clause
        end = ms[i + 1].start() if i + 1 < len(ms) else len(t)
        clause = re.split(r"[,.;]|\d", t[m.end():end], maxsplit=1)[0]
        flags.append(bool(re.search(r"suites?\b", clause)))
    for i in range(len(ms) - 2, -1, -1):
        # "2-bed and 1-bed rental suites": both are suites
        between = t[ms[i].end():ms[i + 1].start()]
        if flags[i + 1] and re.fullmatch(r"\s*(?:and|&|\+|,|;)?\s*", between):
            flags[i] = True
    for m, is_suite in zip(ms, flags):
        if is_suite:
            suites.append(int(m.group(1)))
        elif own is None:
            own = int(m.group(1))
    for m in re.finditer(r"suites?\s*\(\s*(\d)\s*-?\s*(?:bed(?:room)?s?|br|bd)", t):
        n = int(m.group(1))
        suites.append(n)
        if own == n and len(ms) == 1:
            own = None  # that "2 bed" was the suite's
    m = re.search(r"\b(?:rental|legal|secondary|basement|mortgage[- ]helper)\s+suite", t)
    if not suites and m and _affirmed(t, m.group(0), "suite"):
        suites = [1]  # "a rental suite" (not "no rental suite")
    if suites or _affirmed(t, "basement", "basement"):
        b.basement = True
        b.suites = suites[:2]
        if b.stories == 3:
            b.stories = 2  # "three storeys" with a basement means two above grade
        b.beds = own if own is not None else beds_before  # suite bedrooms aren't the house's
    said = stated_fields(text) if base is None else set()
    if base is None and re.search(r"ensuites?\s+(?:in|for|with)\s+(?:every|each|all)(?:\s+the)?\s+bed", t) \
            and "baths" not in said:
        b.baths = b.beds + 0.5  # every bedroom with its own bath, plus a powder room
    if base is None and re.search(r"\b(?:single|one)[- ]level\b|\bno stairs\b|aging in place|wheelchair", t):
        b.stories = 1
    if base is None and "baths" not in said:
        b.baths = max(b.baths, {1: 1, 2: 1.5, 3: 2, 4: 2.5, 5: 3.5, 6: 4.5}.get(b.beds, b.beds - 1.5))
    if base is None and "sqft" not in sizes and not b.basement_sqft and b.sqft == DesignBrief().sqft:
        above = max(1300, (380 + 150 * b.beds + 45 * b.baths) * (1.55 if b.stories == 1 else 1.75))
        if b.basement:
            above *= 1 + 1.0 / max(b.stories, 1)  # the basement comes on top
        b.sqft = int(round(above / 50) * 50)
    if base is None and "sqft" not in sizes and b.basement_sqft:
        # only the basement's size was given: a sensible house above it, plus the basement
        above = max(1300, (380 + 150 * b.beds + 45 * b.baths) * 1.5)
        b.sqft = int(round(above / 50) * 50) + b.basement_sqft
    if base is None and "sqft" in sizes and b.basement and \
            re.search(r"(?:sq\.?\s?f(?:ee)?t|square feet)\s+(?:of\s+)?(?:living\s+)?above[- ](?:ground|grade)|"
                      r"above[- ](?:ground|grade)\s+(?:living\s+)?(?:area|space|sq)", t):
        # "4,200 sq ft above ground": the basement comes on top of that
        b.sqft = int(b.sqft + (b.basement_sqft or round(b.sqft / max(b.stories, 1) / 50) * 50))
    if base is None and "stories" not in stated_fields(text) and b.sqft - b.basement_sqft >= 2600 and b.stories == 1:
        b.stories = 2  # nobody builds 2,600+ sq ft on one floor of a suburban lot unasked
    if base is None and ("stories" in stated_fields(text) or
                         re.search(r"\b(?:bungalow|cottage|rancher|ranch|one[- ]level|single[- ]level|one[- ]stor(?:e?y|ies))\b", t)):
        b._stories_said = True  # the storeys are the client's: the designer won't add one to fit
    if base is None:
        b._style_said = normalize_style(t) is not None  # unnamed: the candidates may try styles
    # custom rules from the phrase library (built-in and learned): asks the fields can't hold
    from . import custom_rules
    found, used = custom_rules.read(t)
    for clause, rules, _how in custom_rules.read_clauses(t):  # (the nearest example phrasing)
        found, used = found + rules, used + [clause]
    if found:
        b.rules = sorted(set(b.rules) | set(custom_rules.clean(found)))
        b.notes = [n for n in b.notes if not any(u in n or n in u for u in used)]
    return b


# -- optional local model (MLX, Apple Silicon) ----------------------------------

DEFAULT_MODEL = "models/MiniCPM5-2B-MLX"

_PROMPT = """Extract a house brief as JSON with exactly these keys:
style (one of craftsman, colonial, foursquare, midcentury), stories (1-3), beds, baths (number,
.5 means a powder room), sqft, lot (like "60x130"), must_haves (list of short phrases).
Use null for anything not stated. Reply with JSON only.

Request: {text}"""

def _generate(prompt: str, image: Optional[str], model_path: str) -> str:
    from . import llm
    return llm._chat(prompt, max_tokens=200, path=model_path)


def _json_from(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"model gave no JSON: {text[:200]!r}")
    return json.loads(m.group(0))


def parse_with_model(text: str, model_path: str = DEFAULT_MODEL) -> DesignBrief:
    """Model reads the sentence; the rule parser fills anything it leaves out or garbles."""
    rules = parse_text(text)
    try:
        data = _json_from(_generate(_PROMPT.format(text=text), None, model_path))
    except Exception:
        return rules
    clean = {k: v for k, v in data.items() if v not in (None, "", [])}
    try:
        got = from_dict({k: v for k, v in clean.items()
                         if k in ("style", "stories", "beds", "baths", "sqft", "lot", "must_haves")})
    except (ValueError, TypeError):
        return rules
    # trust the rules for numbers they found explicitly; the model for the rest
    for f in ("style", "stories", "beds", "baths", "sqft", "lot_width", "lot_depth"):
        if getattr(rules, f) != getattr(DesignBrief(), f):
            setattr(got, f, getattr(rules, f))
        elif f not in clean and f not in ("lot_width", "lot_depth"):
            setattr(got, f, getattr(rules, f))
    got.must_haves = sorted(set(got.must_haves) | set(rules.must_haves))
    return got


# -- helpers shared with the local model ---------------------------------------------

def stated_fields(text: str) -> set[str]:
    """Which fields the client actually wrote down (so a model guess never overrides them)."""
    t = " " + re.sub(r",(?!\d{3})", " ; ", clean_text(text).lower()) + " "
    out = set()
    if normalize_style(t):
        out.add("style")
    if re.search(r"(\d|one|two|three|single)\s*(?:-|\s)?\s*(?:stor(?:y|ey|ies|eys)|floors?|levels?)\b", t) \
            or "ranch" in t or "bungalow" in t:
        out.add("stories")
    for m in re.finditer(r"(\d|one|two|three|four|five|six)\s*(?:-|\s)?\s*(?:bed(?:room)?s?|br|bd)\b", t):
        clause = re.split(r"[,.;]", t[m.end():], maxsplit=1)[0]
        if not re.search(r"suites?\b", clause):  # suite bedrooms aren't the house's
            out.add("beds")
    if re.search(r"(\d(?:\.5)?|one|two|three|four)\s*(?:-|\s)?\s*(?:bath(?:room)?s?|ba)\b", t) or \
            re.search(r"\b(?:\d|one|two|three)\s+(?:[a-z-]+\s+){1,2}bath(?:room)?s?\b", t):
        out.add("baths")
    if re.search(r"\b(?:\d|one|two|three)\s+(?:[a-z-]+\s+){1,2}bed(?:room)?s?\b", t):
        out.add("beds")
    if re.search(r"max(?:imum)?\s+(?:floors|storeys|stories|levels)\s*:?\s*\d", t):
        out.add("stories")
    sizes = _read_sizes(t)
    if "sqft" in sizes:
        out.add("sqft")
    if "lot" in sizes or "lot_area" in sizes:
        out |= {"lot_width", "lot_depth"}
    elif "lot_width" in sizes:
        out.add("lot_width")
    if any(any(w in t for w in words) for words in FEATURES.values()):
        out.add("features")
    return out


def is_thin(text: str) -> bool:
    """True when the brief leaves most of the basics unsaid."""
    return len(text.split()) < 6 or len(stated_fields(text) & {"style", "stories", "beds", "baths", "sqft", "lot_width"}) < 4


def from_fields(data: dict, base: Optional[DesignBrief] = None) -> DesignBrief:
    """A brief from model JSON, clamped to sane values; unknown keys are ignored."""
    b = base or DesignBrief()
    def num(v, lo, hi, cast=float):
        try:
            return max(lo, min(hi, cast(float(str(v).replace(",", "")))))
        except (TypeError, ValueError):
            return None
    if (s := normalize_style(str(data.get("style", "")))):
        b.style = s
    for key, lo, hi, cast in (("stories", 1, 3, int), ("beds", 1, 7, int), ("sqft", 600, 8000, int)):
        if (v := num(data.get(key), lo, hi, cast)) is not None:
            setattr(b, key, v)
    if (v := num(data.get("baths"), 1, 8)) is not None:
        b.baths = round(v * 2) / 2
    if data.get("lot"):
        try:
            b.lot_width, b.lot_depth = parse_lot(str(data["lot"]))
        except ValueError:
            pass
    if isinstance(data.get("must_haves"), list):
        b.must_haves = sorted({normalize_must(x) for x in data["must_haves"] if isinstance(x, str)}
                              & set(MUST_HAVES))
    if isinstance(data.get("suites"), list):
        b.suites = [int(x) for x in data["suites"] if str(x).isdigit() and 0 < int(x) <= 3][:2]
    if "basement" in data:
        b.basement = bool(data["basement"]) or bool(b.suites)
    if isinstance(data.get("features"), list):
        b.features = sorted({f for f in (normalize_feature(x) for x in data["features"]) if f})
    for k in ("garage", "primary_floor"):
        if str(data.get(k, "")).lower() in ("front", "side", "none", "main", "upper"):
            setattr(b, k, str(data[k]).lower())
    if (v := num(data.get("cars"), 0, 4, int)) is not None:
        b.cars = v
    if (v := num(data.get("ceiling"), 0, 20)) is not None and (v == 0 or v >= 8):
        b.ceiling = v
    sync_garage(b)
    if isinstance(data.get("name"), str) and 2 < len(data["name"]) < 40:
        b.name = data["name"]
    return b


def make_sane(b: DesignBrief) -> DesignBrief:
    """Fix combinations that can't be built (too few square feet for the rooms, and so on)."""
    need = 380 + 150 * b.beds + 45 * b.baths
    floor = need + (650 * len(b.suites) if b.basement else 0)
    if b.sqft < floor:
        b.sqft = int(round(floor * 1.15 / 50) * 50)
    if b.baths > b.beds + 1.5:
        b.baths = b.beds + 1.5
    if b.basement and b.stories == 3:
        b.stories = 2
    return b


def describe(b: DesignBrief) -> str:
    """The brief written back as a plain sentence the rule parser reads exactly."""
    st = {"westcoast": "West Coast", "midcentury": "mid-century", "foursquare": "Foursquare",
          "craftsman": "Craftsman", "colonial": "Colonial", "modern": "Modern", "farmhouse": "modern farmhouse",
          "mediterranean": "Mediterranean", "tudor": "Tudor", "scandinavian": "Scandinavian"}.get(b.style, b.style.title())
    storey = {1: "one-storey", 2: "two-storey", 3: "three-storey"}[b.stories]
    parts = [f"{st} {storey}, {b.beds} bed {b.baths:g} bath, {b.sqft:,} sq ft total, "
             f"{b.lot_width:g} x {b.lot_depth:g} lot"]
    if b.basement:
        if b.suites:
            parts.append(" and ".join(f"{n}-bed" for n in b.suites) +
                         f" rental suite{'s' if len(b.suites) > 1 else ''} in the basement")
        else:
            parts.append("finished basement")
    mh = [m for m in b.must_haves if not (m == "garage" and b.garage in ("front", "side"))]
    if mh:
        parts.append("with " + ", ".join(mh))
    fe = [f for f in b.features if f not in ("no garage", "3-car garage")]
    if fe:
        parts.append(", ".join(fe))
    if b.garage in ("front", "side"):
        parts.append(f"{b.garage} garage" + (f", {b.cars}-car" if b.cars else ""))
    elif b.cars and b.garage != "none":
        parts.append(f"{b.cars}-car garage")
    elif b.garage == "none":
        parts.append("no garage")
    if b.primary_floor in ("main", "upper"):
        parts.append(f"primary on the {b.primary_floor} floor")
    if b.ceiling:
        parts.append(f"{b.ceiling:g} ft ceilings")
    if b.basement and b.basement_sqft:
        parts.append(f"{b.basement_sqft} sq ft basement")
    for p in b.places:
        room, side = p.split(":")
        parts.append(f"{'primary bedroom' if room == 'primary' else room} at the {side}")
    word = {0.75: "tiny", 0.8: "small", 0.85: "cozy", 0.9: "modest", 1.25: "big", 1.3: "spacious",
            1.35: "grand", 1.4: "oversized", 1.5: "huge"}
    names = {"family": "great room", "primary": "primary suite", "mud": "mudroom", "wic": "walk-in",
             "primary_bath": "ensuite", "entry": "foyer", "bath": "bathrooms", "bedroom": "bedrooms"}
    for room, k in b.sizes.items():
        if room != "garage":
            parts.append(f"{word.get(k, 'big' if k > 1 else 'small')} {names.get(room, room)}")
    from .custom_rules import describe as rule_words
    for r in getattr(b, "rules", []) or []:
        if not r.startswith(("scale:", "side:", "floor:primary", "open:on")):  # (already said above)
            parts.append(rule_words(r))
    return ", ".join(parts) + "."
