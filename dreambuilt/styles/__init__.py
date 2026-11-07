"""Era style library: one YAML file per style."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_DIR = Path(__file__).parent


def available() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.yaml"))


@lru_cache(maxsize=None)
def get(key: str) -> dict:
    path = _DIR / f"{key.lower().replace(' ', '').replace('-', '')}.yaml"
    if not path.exists():
        raise KeyError(f"unknown style {key!r}; have {available()}")
    return yaml.safe_load(path.read_text())
