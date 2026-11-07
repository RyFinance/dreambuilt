"""Room program: turn a brief into rooms with target areas and minimum sizes."""
from __future__ import annotations

from dataclasses import dataclass

from ..brief import DesignBrief


@dataclass
class Spec:
    name: str
    kind: str
    target: float  # square feet before scaling
    min_dim: float  # smallest acceptable width or depth, feet

    def scaled(self, k: float) -> "Spec":
        return Spec(self.name, self.kind, self.target * k, self.min_dim)


BASE = {  # kind: (target sq ft, min dimension)
    "living": (300, 12), "dining": (150, 10), "kitchen": (180, 10), "entry": (80, 6),
    "powder": (30, 4), "pantry": (25, 3), "laundry": (50, 6.0), "mud": (60, 6.0),
    "office": (120, 10), "family": (250, 12), "primary": (200, 11), "primary_bath": (80, 6),
    "wic": (45, 4), "bedroom": (135, 10), "bath": (50, 5),
}

KIND = {"primary": "bedroom", "primary_bath": "bath", "wic": "closet", "pantry": "closet"}


def spec(key: str, name: str, scale: float = 1.0) -> Spec:
    t, m = BASE[key]
    return Spec(name, KIND.get(key, key), t * scale, m)


@dataclass
class Program:
    public: list[Spec]  # living, dining, kitchen, entry, office, family
    service: list[Spec]  # laundry, mud, powder, pantry
    primary: list[Spec]  # bedroom, bath, closet
    bedrooms: list[Spec]  # secondary
    baths: list[Spec]  # shared full baths
    upstairs_laundry: bool
    extras: list[Spec]  # office / bonus rooms for upper floors
    ensuite_each: bool = False  # every secondary bedroom's bath is its own ("Ensuite N")

    def all(self) -> list[Spec]:
        return self.public + self.service + self.primary + self.bedrooms + self.baths + self.extras


def build_program(b: DesignBrief) -> Program:
    big = b.sqft / max(b.beds, 1) > 650  # roomy house: walk-in closet, bigger rooms
    multi = b.stories > 1
    public = [spec("living", "Living"), spec("dining", "Dining"), spec("kitchen", "Kitchen")]
    if multi:
        public.insert(0, spec("entry", "Entry"))
    extras: list[Spec] = []
    if b.has("office"):
        (extras if b.stories == 3 else public).append(spec("office", "Office"))
    if b.has("family room") and not any(s.kind == "family" for s in public):
        public.append(spec("family", "Family Room"))
    if b.has("bonus room"):
        (extras if multi else public).append(spec("family", "Family Room" if not multi else "Bonus Room"))
    service = []
    upstairs = multi and b.has("upstairs laundry")
    small = b.sqft < 1500
    if small and not upstairs:
        # small houses share one room for coats, boots and the washer
        service.append(Spec("Mud & Laundry" if b.has("mudroom") else "Laundry", "laundry", 55, 6))
    else:
        if not upstairs:
            service.append(spec("laundry", "Laundry"))
        if b.has("mudroom") or multi:
            service.append(spec("mud", "Mudroom"))
    full = int(b.baths)
    half = b.baths - full >= 0.5
    if half:
        service.append(spec("powder", "Powder"))
    if b.has("pantry") or (multi and half):
        service.append(spec("pantry", "Pantry"))
    primary = [spec("primary", "Primary Bedroom"), spec("primary_bath", "Primary Bath")]
    if not small:
        primary.append(spec("wic", "Walk-in Closet"))  # small houses use a built-in closet
    bedrooms = [spec("bedroom", f"Bedroom {i}") for i in range(2, b.beds + 1)]
    shared = max(full - 1, 0)
    if shared == 0 and b.beds > 1 and full >= 1:
        # one full bath total: it serves everyone, so it is not inside the primary suite
        primary[1] = Spec("Bath", "bath", 60, 5)
    baths = [spec("bath", f"Bath {i}") for i in range(2, 2 + shared)]
    ensuite = "ensuite_each" in (getattr(b, "rules", []) or []) and len(baths) >= len(bedrooms) > 0
    if ensuite:
        # a bath of its own for every bedroom, named for it so its door opens from that room
        baths = [Spec(f"Ensuite {i}", "bath", 45, 5) for i in range(2, b.beds + 1)]
    prog = Program(public, service, primary, bedrooms, baths, upstairs, extras, ensuite)
    # "big kitchen", "small office": the client's size words scale those rooms
    scale = getattr(b, "sizes", {}) or {}
    key = {"Primary Bedroom": "primary", "Primary Bath": "primary_bath", "Walk-in Closet": "wic", "Pantry": "pantry",
           "Mudroom": "mud", "Entry": "entry"}
    for sp in prog.all():
        k = key.get(sp.name) or ("bedroom" if sp.name.startswith("Bedroom") else sp.kind)
        if k in scale:
            sp.target *= scale[k]
        if sp.name.lower() in scale:  # one titled room ("bedroom 3"): an edit aimed at it
            sp.target *= scale[sp.name.lower()]
    return prog
