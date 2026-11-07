"""The local model (MiniCPM5-2B on MLX, offline), used where language helps most.

improve(text)        rewrites a thin brief into a full, specific one an architect would write
extract(text)        reads any brief into every field the designer understands
revise(brief, ask)   turns a change request ("make it bigger, add a suite") into field edits

The model is loaded once and reused. Every answer is checked and clamped; the rule-based
parser stays the fallback, so a bad answer never breaks a design.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import os

# MiniCPM5-2B (Apache-2.0, openbmb/MiniCPM5-2B-MLX, 4-bit): `dreambuilt get-model` fetches it
# into models/; DREAMBUILT_MODEL points at another local MLX text model
_MODELS = Path(__file__).resolve().parents[1] / "models"
MODEL_REPO = "openbmb/MiniCPM5-2B-MLX"
MODEL_REVISION = "8a9ad7539ac86281d0ac2b017ba04a5de53fe9a3"
DEFAULT_MODEL = os.environ.get("DREAMBUILT_MODEL") or str(_MODELS / "MiniCPM5-2B-MLX")

STYLES = "craftsman, colonial, foursquare, midcentury, westcoast, modern, farmhouse, mediterranean, tudor, scandinavian, japanese"
# no example values in the schema: a small model copies them into every answer
FIELDS = """{
  "style": one of [craftsman, colonial, foursquare, midcentury, westcoast, modern, farmhouse,
            mediterranean, tudor, scandinavian, japanese],
  "stories": storeys above ground, a number 1 to 3,
  "beds": bedrooms in the main house (rental suite bedrooms do not count),
  "baths": bathrooms in the main house (a half means a powder room),
  "sqft": total finished square feet including any basement,
  "lot": the lot as WIDTHxDEPTH in feet,
  "basement": true or false,
  "suites": a list with the bedroom count of each basement rental suite, empty if none,
  "must_haves": short phrases from [porch, fireplace, mudroom, office, pantry, upstairs laundry,
                 bonus room, garage, spice kitchen, balcony],
  "features": short phrases from [flat roof, gable roof, hip roof, shed roof, big windows, stone,
               wood, brick, board and batten, stucco, 3-car garage, no garage, covered patio,
               vaulted, theatre, gym, wet bar, wine room, open plan, wide, symmetrical],
  "garage": one of [auto, front, side, none],
  "cars": garage spaces, 0 if not said,
  "primary_floor": one of [auto, main, upper],
  "ceiling": main-floor ceiling height in feet, 0 if not said,
  "name": null unless the client gave the house a name
}"""


def available(path: str = DEFAULT_MODEL) -> bool:
    return Path(path, "model.safetensors").exists()


def is_vision(path: str) -> bool:
    """Kept for callers: this build ships a text-only model."""
    return False


def get_model(dest: str = DEFAULT_MODEL) -> str:
    """Download MiniCPM5-2B (about 1.4 GB, once) into models/."""
    from huggingface_hub import snapshot_download
    Path(dest).mkdir(parents=True, exist_ok=True)
    snapshot_download(MODEL_REPO, revision=MODEL_REVISION, local_dir=dest,
                      allow_patterns=["*.json", "*.safetensors", "*.jinja", "*.md"])
    return dest


@lru_cache(maxsize=2)
def _load(path: str):
    from mlx_lm import load as load_lm
    return load_lm(path)


def _chat(prompt: str, image: Optional[str] = None, max_tokens: int = 400, temperature: float = 0.0,
          path: str = DEFAULT_MODEL) -> str:
    """One answer from the local text model (mlx-lm)."""
    if image:
        raise RuntimeError("this build reads text only (no photo model)")
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler
    model, tok = _load(path)
    msgs = [{"role": "user", "content": prompt}]
    try:
        chat = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False)
    except TypeError:
        chat = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    out = generate(model, tok, chat, max_tokens=max_tokens, sampler=make_sampler(temp=temperature), verbose=False)
    return re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON in model answer: {text[:160]!r}")
    raw = m.group(0)
    raw = re.sub(r",\s*([}\]])", r"\1", raw)  # trailing commas
    return json.loads(raw)


# -- extract ----------------------------------------------------------------------

EXTRACT = """Read this house brief and fill in this JSON. Use null for anything the brief does not say.
Reply with JSON only.

{fields}

Brief: "{text}"
"""


def extract(text: str, path: str = DEFAULT_MODEL) -> dict:
    data = _json(_chat(EXTRACT.format(fields=FIELDS, text=text.strip()), max_tokens=260, path=path))
    return {k: v for k, v in data.items() if v not in (None, "", [], "null")}


# -- revise -----------------------------------------------------------------------

REVISE = """A house design was made from this brief (JSON):
{brief}

The client now asks: "{ask}"

Reply with JSON containing ONLY the fields that should change, using the same field names and
meanings as above. For "bigger"/"smaller" without a number, change sqft by about 15%. For a new
must-have, return the full new must_haves list. Reply with JSON only."""


def revise(brief: dict, ask: str, path: str = DEFAULT_MODEL) -> dict:
    data = _json(_chat(REVISE.format(brief=json.dumps(brief), ask=ask.strip()), max_tokens=200, path=path))
    return {k: v for k, v in data.items() if v is not None}


# -- look -------------------------------------------------------------------------



# -- complete: the full brief, then the words --------------------------------------

COMPLETE = """You are an experienced residential architect. A client wrote:
<<<
{text}
>>>

Fill in EVERY field of this JSON for the house they describe. Rules:
- Keep everything the client stated exactly.
- Choose the rest from their own words and the kind of house they describe, not from any
  standard: a modern house gets modern features, a farmhouse a farmhouse's, a cottage a
  cottage's size. Words like luxury, big, family, starter or small set the size.
- Only set basement true if they mention a basement, and only list suites if they mention a
  suite, rental, legal suite or mortgage helper.
- features: what they asked for, plus up to three that suit the look they describe.
- must_haves: what they asked for, plus at most two that clearly suit them.
Reply with JSON only.

{fields}"""

CHARACTER = """You are an architect writing the design notes for a concept set.
The house: {brief}
Its style: {style}
What the client wrote: "{text}"

Write four short sentences in plain words, true to the style and the client:
1. the massing and roof (shape, what steps forward, what is tallest),
2. the materials and windows on the street side,
3. the entry and garage,
4. how the main floor flows and one highlight inside.
No numbers, no prices, no lists, no headings. Reply with the four sentences only."""


def complete(text: str, path: str = DEFAULT_MODEL) -> dict:
    from .brief import clean_text
    data = _json(_chat(COMPLETE.format(text=clean_text(text)[:9000], fields=FIELDS), max_tokens=360,
                       temperature=0.2, path=path))
    return {k: v for k, v in data.items() if v not in (None, "", "null")}


def character(brief_summary: str, style_key: str = "", path: str = DEFAULT_MODEL, text: str = "") -> str:
    from . import styles
    try:
        st = styles.get(style_key)
        style = f"{st['name']}: {st['summary']}"
    except KeyError:
        style = ""
    from .brief import clean_text
    out = _chat(CHARACTER.format(brief=brief_summary, style=style, text=clean_text(text)[:600]),
                max_tokens=220, temperature=0.5, path=path)
    out = clean_text(out)
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", out.strip().strip('"')) if len(x) > 12]
    return " ".join(sentences[:4])


RULES_FREE = """A client wrote this about the house they want:
"{text}"

Turn it into design rules, using ONLY these forms (anything else is ignored):
  ensuite_each              every bedroom has its own private bathroom
  entry:center|left|right   where the front door is
  open:on|off               open floor plan, or separate rooms
  no_bath_row               no bathrooms side by side
  floor:ROOM:main|upper     which floor a room is on
  side:ROOM:front|rear      which side of the house a room faces
  near:ROOM:ROOM            two rooms next to each other
  scale:ROOM:NUMBER         room size, 0.7 small to 1.6 huge
  exclude:basement|garage|porch|fireplace|office|pantry
ROOM is one of: primary, bedroom, kitchen, living, family, dining, office, laundry, mudroom, pantry, garage, entry.
Reply with a JSON list of rule strings only, [] if none apply."""

RULES_MENU = """A client wrote this about the house they want:
"{text}"

Which of these requirements did they ask for? Reply with the numbers only, separated by commas, or 0 if none.
{menu}"""


def rules_free(text: str, path: str = DEFAULT_MODEL) -> list[str]:
    """The model writes rules in the rule language; anything outside it is dropped."""
    from . import custom_rules
    out = _chat(RULES_FREE.format(text=text[:600]), max_tokens=120, temperature=0.0, path=path)
    m = re.search(r"\[.*?\]", out, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = re.findall(r'"([^"]+)"', m.group(0)) if m else []
    return custom_rules.clean(items)


def rules_menu(text: str, path: str = DEFAULT_MODEL) -> list[str]:
    """The model only picks numbers from a menu of concrete rules (no free text to go wrong)."""
    from . import custom_rules
    keys = list(custom_rules.EXAMPLES)
    menu = "\n".join(f"{i + 1}. {custom_rules.EXAMPLES[k][0]}" for i, k in enumerate(keys))
    out = _chat(RULES_MENU.format(text=text[:600], menu=menu), max_tokens=30, temperature=0.0, path=path)
    picks = [int(x) for x in re.findall(r"\d+", out) if 1 <= int(x) <= len(keys)]
    return custom_rules.clean([keys[i - 1] for i in picks])


def fit_size(b) -> None:
    """Raise a guessed size until the plan the designer would pick actually fits it
    (only used when the client didn't give a size)."""
    import copy
    from . import styles
    from .design import estate
    if not b.basement or b.stories < 2 or not styles.get(b.style).get("layout", {}).get("estate"):
        return
    style = styles.get(b.style)
    for _ in range(40):
        above = copy.copy(b)
        above.sqft = int(round(b.sqft / 1.62))
        if estate.applies(above, style) or b.sqft >= 8000:
            return
        b.sqft += 250


def improve(text: str, path: str = DEFAULT_MODEL) -> tuple[str, "object"]:
    """A thin or loose brief becomes a full one: (paragraph to show the user, DesignBrief).

    The model fills in what the client left out; anything they actually said wins. Its
    guesses are checked against the words (no suites nobody asked for, no invented names)."""
    from . import brief as briefs
    stated = briefs.parse_text(text)
    said = briefs.stated_fields(text)
    low = briefs.clean_text(text).lower()
    try:
        data = complete(text, path)
        guess = briefs.from_fields(data, briefs.DesignBrief())
    except Exception:  # model answered badly: keep the rule reading
        guess = stated
    # what the client actually said always wins over the model's guess
    for f in said - {"features"}:
        setattr(guess, f, getattr(stated, f))
    if "style" not in said and guess.style == "westcoast":
        # the estate is a style the client asks for, never a default (a Surrey address isn't one)
        guess.style = stated.style if stated.style != "westcoast" else "modern"
    # layout asks the rules read (garage, primary floor, ceilings) always win too
    # layout asks come only from the client's words (the model doesn't invent a 3-car
    # garage, 10' ceilings or a main-floor primary)
    model = briefs.from_fields(data, briefs.DesignBrief()) if isinstance(locals().get("data"), dict) else None
    for f in ("garage", "cars", "primary_floor", "ceiling"):
        setattr(guess, f, getattr(stated, f))
    # where the rules found nothing, the model's reading counts when the client's own words
    # back it up (a capable model reads "my bedroom on the ground floor" or "single garage")
    if model is not None:
        if stated.primary_floor == "auto" and model.primary_floor in ("main", "upper") and re.search(
                r"ground floor|main floor|first floor|main level|downstairs|no stairs|climb|upstairs|"
                r"second floor|upper floor", low):
            guess.primary_floor = model.primary_floor
        if not stated.cars and 1 <= (model.cars or 0) <= 3 and re.search(r"garage|car\b|cars\b", low):
            guess.cars = model.cars
        if stated.garage == "auto" and model.garage == "none" and re.search(
                r"no garage|without a garage|carport|don'?t need a garage", low):
            guess.garage = "none"
    guess.notes, guess.wishes = list(stated.notes), list(stated.wishes)
    # custom rules: the phrase library and examples (in the rule reading), then the model
    # proposes rules for what's left, checked against the clause; what it gets right is learned
    from . import custom_rules
    guess.rules = list(getattr(stated, "rules", []))
    try:
        extra = custom_rules.read_clauses(text, propose=lambda c: rules_menu(c, path))
    except Exception:
        extra = []
    for clause, rules, how in extra:
        guess.rules = sorted(set(guess.rules) | set(rules))
        guess.notes = [n for n in guess.notes if not (n in clause or clause in n)]
        if how == "model":
            custom_rules.learn(clause, rules)
    guess.places, guess.sizes = list(stated.places), dict(stated.sizes)
    guess.basement_sqft = stated.basement_sqft
    if getattr(stated, "_stories_said", False):
        guess._stories_said = True
    guess._style_said = "style" in said or getattr(stated, "_style_said", True)
    # the model may add at most one small, safe extra the style suits; never rooms that
    # change the plan (pantry, garage, office, suites) unless the client asked
    safe = {"craftsman": {"porch", "fireplace"}, "colonial": {"porch", "fireplace"},
            "foursquare": {"porch"}, "midcentury": {"fireplace"}, "westcoast": {"fireplace", "mudroom"},
            "modern": set()}.get(guess.style, set())
    extra = [m for m in guess.must_haves if m not in stated.must_haves and m in safe][:1]
    guess.must_haves = sorted(set(stated.must_haves) | set(extra))
    # the model's own picks must suit the style; layout wishes only come from the client
    fits = briefs.STYLE_FEATURES.get(guess.style, set())
    feats = [f for f in guess.features if f not in stated.features and f in fits][:2]
    clash = {"flat roof", "gable roof", "hip roof", "shed roof"}
    if clash & set(stated.features):
        feats = [f for f in feats if f not in clash]  # the client chose the roof
    if "no garage" in stated.features:
        feats = [f for f in feats if f != "3-car garage"]
    guess.features = sorted(set(stated.features) | set(feats))
    if "sqft" not in said and getattr(stated, "_sized_by", "") == "words":
        guess.sqft = stated.sqft  # "luxury", "small": the size words
    # basement and suites: exactly what the rules read ("no basement" stays no basement)
    guess.basement, guess.suites = stated.basement, list(stated.suites)
    if model is not None and not stated.basement and model.basement and \
            re.search(r"basement|lower level|cellar", low) and not re.search(r"no basement", low):
        guess.basement = True
    if model is not None and not stated.suites and model.suites and \
            re.search(r"suite|rental|mortgage|tenant|in-law|legal", low) and not re.search(r"no (?:rental )?suite", low):
        guess.suites, guess.basement = list(model.suites)[:2], True
    if not re.search(r"\b(?:called|named|name it)\b", low):
        guess.name = None
    # sizes and storeys the client didn't give follow sensible rules, not the model's whim
    if "baths" not in said:
        guess.baths = max(guess.baths, 2.0 if guess.beds >= 3 else 1.0, 2.5 if guess.beds >= 4 else 0)
    need = 380 + 150 * guess.beds + 45 * guess.baths
    fixed_lot = "strict lot" in guess.features or "townhouse" in guess.features
    if "sqft" not in said and getattr(stated, "_sized_by", "") != "words" and not fixed_lot:
        share = 1 + (1.0 / max(guess.stories, 1) if guess.basement else 0)
        # a big family house gets room to breathe (5 bedrooms in 2,000 sq ft is a squeeze)
        above = max(need * (1.6 if guess.beds >= 5 else 1.4), min(guess.sqft / share, need * 1.9))
        guess.sqft = int(round(above * share / 50) * 50)
    if "stories" not in said:
        above = guess.sqft / (1 + (1 if guess.basement else 0) / max(guess.stories, 1))
        if re.search(r"\b(?:cottage|bungalow|rancher|ranch|one[- ]level|single[- ]level)\b", low) or above <= 1600:
            guess.stories = 1
        elif guess.beds >= 4 and above >= 2000 and guess.stories == 1:
            guess.stories = 2  # four or more bedrooms: two storeys unless the client says otherwise
    if fixed_lot:
        guess.sqft = stated.sqft  # what the lot can hold
    lot_read = (stated.lot_width, stated.lot_depth) != (briefs.DesignBrief().lot_width, briefs.DesignBrief().lot_depth)
    if model is not None and not lot_read and (model.lot_width, model.lot_depth) != \
            (briefs.DesignBrief().lot_width, briefs.DesignBrief().lot_depth) and \
            re.search(r"\blot\b|feet|foot|\bft\b|wide|deep", low):
        # a lot in words ("twenty foot wide, eighty feet deep") the rules couldn't read
        guess.lot_width, guess.lot_depth = model.lot_width, model.lot_depth
    elif not {"lot_width", "lot_depth"} & said:
        guess.lot_width, guess.lot_depth = briefs.default_lot(guess.sqft, guess.stories, guess.style)
    elif "lot_depth" not in said:
        guess.lot_depth = briefs.default_lot(guess.sqft, guess.stories, guess.style)[1]
    briefs.make_sane(guess)
    if "sqft" not in said:
        fit_size(guess)
    words = ""
    try:
        words = character(guess.summary(), guess.style, path, text)
    except Exception:
        pass
    return briefs.describe(guess) + (" " + words if words else ""), guess


def removed_wishes(ask: str) -> set[str]:
    """Must-haves the client is taking out: "swap the fireplace for an office", "no porch",
    "drop the mudroom", "remove the balcony", "without a garage"."""
    from .brief import MUST_HAVES
    t = ask.lower()
    gone = set()
    for key, words in MUST_HAVES.items():
        for w in words:
            w = re.escape(w)
            if re.search(rf"(?:swap|replace|trade)\s+(?:the\s+|a\s+)?{w}\b", t) or \
               re.search(rf"\b(?:no|drop|remove|lose|skip|without|ditch|get rid of)\s+(?:the\s+|a\s+|an\s+)?{w}\b", t):
                gone.add(key)
    return gone


TOPICS = {
    "style": r"style|modern|craftsman|colonial|foursquare|mid-?century|west coast|surrey[- ]style|contemporary|"
             r"farmhouse|mediterranean|spanish|tudor|scandinavian|scandi|nordic|japanese|japandi",
    "stories": r"stor(?:y|ey|ies|eys)|floor|level|bungalow|rancher",
    "beds": r"bed",
    "baths": r"bath|powder|ensuite",
    "sqft": r"sq|square|size|big|small|bigger|smaller|larger|tiny|huge|grow|shrink|reduce|increase|more space|less space",
    "lot": r"lot|property",
    "basement": r"basement|suite|rental",
    "suites": r"suite|rental",
    "must_haves": r"add|with|include|want|need|no |remove|drop|swap|replace|without|lose|skip",
    "features": r"roof|window|glass|stone|wood|brick|stucco|batten|garage|patio|vault|ceiling|theat|gym|bar|wine|open|wide|symmetr|cedar",
}
BIGGER = r"\b(?:bigger|larger|more space|grow|increase|expand|add (?:more )?(?:space|room)|roomier)\b"
SMALLER = r"\b(?:smaller|less space|shrink|reduce|cut|tighter|trim|compact)\b"


def revise_brief(base, ask: str, path: str = DEFAULT_MODEL):
    """Apply a change request to a brief: the model handles fuzzy asks ("a bit bigger",
    "swap the fireplace for an office"); anything stated outright ("5 bed", "60 x 130 lot",
    "a 1-bed suite") is read by the rules and wins."""
    import copy
    from dataclasses import asdict
    from . import brief as briefs
    out = copy.deepcopy(base)
    fields = asdict(base)
    fields["lot"] = f"{base.lot_width:g}x{base.lot_depth:g}"
    for k in ("lot_width", "lot_depth"):
        fields.pop(k, None)
    t = ask.lower()
    try:
        patch = revise(fields, ask, path)
        # the model may only touch what the ask is about
        patch = {k: v for k, v in patch.items() if k in TOPICS and re.search(TOPICS[k], t)}
        out = briefs.from_fields(patch, out)
    except Exception:
        pass
    # a fuzzy size change always moves the way the client said, by a sensible step
    share = 1.0
    if re.search(r"basement", t) and base.basement:
        share = 0.38  # the basement is roughly this much of the total
    if re.search(SMALLER, t) and "sqft" not in briefs.stated_fields(ask):
        out.sqft = int(round(base.sqft * (1 - 0.15 * share) / 50) * 50)
    elif re.search(BIGGER, t) and "sqft" not in briefs.stated_fields(ask):
        out.sqft = int(round(base.sqft * (1 + 0.15 * share) / 50) * 50)
    elif "sqft" not in briefs.stated_fields(ask):
        out.sqft = base.sqft
    if not re.search(r"basement|suite|rental", t):
        out.basement, out.suites = base.basement, list(base.suites)
    elif re.search(r"\b(?:no|remove|drop|without|lose)\s+(?:the\s+)?basement", t):
        out.basement, out.suites = False, []
    elif base.basement and not re.search(r"\b(?:no|remove|drop|without)\b", t):
        out.basement = True  # "make the basement smaller" keeps the basement
    ruled = briefs.parse_text(ask, copy.deepcopy(base))
    for f in briefs.stated_fields(ask):
        setattr(out, f, getattr(ruled, f))
    added = set(ruled.must_haves) - set(base.must_haves)
    out.must_haves = sorted((set(out.must_haves) | added) - removed_wishes(ask))
    out.features = sorted(set(out.features) | set(ruled.features))
    if ruled.basement and not base.basement:
        out.basement, out.suites = True, ruled.suites
    elif ruled.suites != base.suites and ruled.suites:
        out.suites = ruled.suites
    return briefs.make_sane(out)


# -- edits the word reader missed: the model chooses, by likelihood, from fixed lists --------

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def choose(prompt: str, options: list[str], path: str = DEFAULT_MODEL) -> tuple[int, float]:
    """The option the model finds most likely, scored on the next token's logits over the
    option letters (no text generated, so it can't answer outside the list). (index, prob)."""
    import mlx.core as mx
    model, tok = _load(path)
    letters = LETTERS[:len(options)]
    body = prompt + "\n" + "\n".join(f"{c}) {o}" for c, o in zip(letters, options)) + "\nAnswer with one letter."
    msgs = [{"role": "user", "content": body}]
    try:
        chat = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False, enable_thinking=False)
    except TypeError:
        chat = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    ids = tok.encode(chat)
    logits = model(mx.array(ids)[None])[0, -1]
    lp = logits - mx.logsumexp(logits)
    scores = []
    for c in letters:
        cands = {tok.encode(c, add_special_tokens=False)[0], tok.encode(" " + c, add_special_tokens=False)[-1]}
        scores.append(max(float(lp[i]) for i in cands))
    best = max(range(len(scores)), key=lambda i: scores[i])
    import math
    total = sum(math.exp(s) for s in scores) or 1.0
    return best, math.exp(scores[best]) / total


ACTIONS = [("bigger", "make it bigger"), ("smaller", "make it smaller"), ("front", "move it to the front"),
           ("rear", "move it to the back"), ("remove", "remove it"), ("none", "none of these")]


def edit_ops(text: str, house, path: str = DEFAULT_MODEL, min_p: float = 0.45):
    """Edit operations for a request the word reader couldn't parse: the model picks one room
    from this design's own titles and one action from a fixed list. Low-confidence picks give
    nothing (better to ask again than to change the wrong room)."""
    from . import edit
    rooms = [r for lv in house.all_levels for r in lv.rooms
             if r.kind not in ("void", "closet", "stair", "hall") and not r.unit][:24]
    if not rooms:
        return []
    ri, rp = choose(f'A client says about their house plan: "{text}"\nWhich room are they talking about?',
                    [r.label for r in rooms], path)
    ai, ap = choose(f'A client says: "{text}"\nWhat do they want done to the {rooms[ri].label}?',
                    [a[1] for a in ACTIONS], path)
    act = ACTIONS[ai][0]
    if rp < min_p or ap < min_p or act == "none":
        return []
    t = rooms[ri].label
    return [{"bigger": edit.Op("resize", t, value=edit.GROW), "smaller": edit.Op("resize", t, value=edit.SHRINK),
             "front": edit.Op("move", t, side="front"), "rear": edit.Op("move", t, side="rear"),
             "remove": edit.Op("remove", t)}[act]]
