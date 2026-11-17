# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Characters of a family: names, classes, portraits, what is bound to them."""

import json
import re

from ..i18n import tr
from . import config
from .errors import BdoUiError
from .game import family_file
from .library import lib_list
from .skilldb import char_class
from .skills import capture_profile, characters, profile_for_preset


def char_registry():
    """Names given to characters by the user (the game keeps them server-side)."""
    try:
        return json.loads(config.CHAR_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_char_name(char_id, name):
    reg = char_registry()
    reg.setdefault(char_id, {})["name"] = name.strip()
    config.LIB_DIR.mkdir(parents=True, exist_ok=True)
    config.CHAR_REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")


def game_char_order(family):
    """Characters that exist in the game's selection screen: {char_id: order}."""
    try:
        text = family_file(family).read_bytes().decode("latin1")
    except OSError:
        return {}
    return {c: int(o) for c, o in re.findall(
        r'<CharacterOrderList CharacterNo="(\d+)" Order="(\d+)"/>', text)}


def portrait_path(char_id):
    path = config.BDO_DIR / "FaceTexture" / f"{char_id}.bmp"
    return path if path.is_file() else None


def char_cards(family):
    """Everything the character picker shows, in the game's own order."""
    order = game_char_order(family)
    reg = char_registry()
    bound = {}
    for entry in lib_list():
        prof = profile_for_preset(entry)
        if prof and prof.get("family") == family:
            bound.setdefault(prof["char"], []).append(entry)
    cards = []
    for mtime, char in characters(family):
        prof = capture_profile(family, char)
        skills = list(prof["cooldown"].values()) + list(prof["quick"].values())
        cls, spec = char_class(skills)
        cards.append({
            "char": char, "mtime": mtime, "order": order.get(char),
            "name": reg.get(char, {}).get("name", ""), "class": cls, "spec": spec,
            "cooldown": len(prof["cooldown"]), "quick": len(prof["quick"]),
            "portrait": portrait_path(char), "entries": bound.get(char, []),
        })
    cards.sort(key=lambda c: (c["order"] is None, c["order"] if c["order"] is not None
                              else -c["mtime"]))
    return cards


def char_title(family, char_id):
    """Short human label of a character: its name and class when known."""
    name = char_registry().get(char_id, {}).get("name", "")
    try:
        prof = capture_profile(family, char_id)
        cls, _ = char_class(list(prof["cooldown"].values()) + list(prof["quick"].values()))
    except (BdoUiError, OSError):
        cls = None
    parts = [p for p in (name, cls) if p]
    return " · ".join(parts) if parts else tr("char.anon", id=char_id[-8:])
