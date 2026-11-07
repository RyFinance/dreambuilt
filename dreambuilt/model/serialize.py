"""House model <-> plain dicts, JSON and YAML."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import yaml

from .house import (Balcony, Brief, Chimney, Cladding, Dormer, Fixture, House, InteriorDoor, Level, Lot, Opening,
                    Porch, RoofMass, Room, Steps)


def to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def _build(cls, data: dict, **nested):
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ValueError(f"{cls.__name__}: unknown field(s) {sorted(unknown)}")
    kwargs = dict(data)
    for key, fn in nested.items():
        if kwargs.get(key) is not None:
            kwargs[key] = fn(kwargs[key])
    return cls(**kwargs)


def _list(cls, **nested):
    return lambda items: [_build(cls, d, **nested) for d in items]


def from_dict(data: dict) -> House:
    level = lambda d: _build(Level, d, rooms=_list(Room), openings=_list(Opening),
                             doors=_list(InteriorDoor), fixtures=_list(Fixture))
    return _build(
        House, data,
        levels=lambda items: [level(d) for d in items],
        roofs=_list(RoofMass, gable_ends=tuple),
        porches=_list(Porch, columns=lambda cs: [tuple(c) for c in cs], steps=_list(Steps)),
        chimneys=_list(Chimney),
        balconies=_list(Balcony),
        claddings=_list(Cladding),
        dormers=_list(Dormer),
        basement=level,
        lot=lambda d: _build(Lot, d),
        brief=lambda d: _build(Brief, d),
    )


def dumps(house: House) -> str:
    return json.dumps(to_dict(house), indent=2)


def load(path: str | Path) -> House:
    path = Path(path)
    text = path.read_text()
    data = yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)
    return from_dict(data)


def save(house: House, path: str | Path) -> None:
    path = Path(path)
    if path.suffix in (".yaml", ".yml"):
        path.write_text(yaml.safe_dump(to_dict(house), sort_keys=False))
    else:
        path.write_text(dumps(house) + "\n")
