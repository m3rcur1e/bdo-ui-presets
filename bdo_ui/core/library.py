# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""The preset library: layouts kept on disk, one XML file per preset."""

import datetime
import json
import os
import re

from ..i18n import tr
from . import config
from .errors import BdoUiError
from .game import read_slots, slot_is_empty
from .layout import estimate_screen, parse_elements

LIB_TAG = "Preset"

_NAME_RE = re.compile(r'^[\w][\w .\-]{0,60}$')


class Preset:
    """A named layout: elements plus the screen size they were saved at."""

    def __init__(self, els, screen=None, name=None, meta=None):
        self.els = els
        self.screen = tuple(screen) if screen else estimate_screen(els)
        self.name = name
        self.meta = meta or {}

    def copy(self):
        return Preset([e.copy() for e in self.els], self.screen, self.name,
                      dict(self.meta))


def check_name(name):
    if not _NAME_RE.match(name or ""):
        raise BdoUiError(tr("err.bad_name"))
    return name


def lib_path(name):
    return config.LIB_DIR / f"{check_name(name)}.xml"


def lib_list():
    if not config.LIB_DIR.is_dir():
        return []
    return sorted((p.stem for p in config.LIB_DIR.glob("*.xml")), key=str.lower)


def lib_save(preset, name):
    config.LIB_DIR.mkdir(parents=True, exist_ok=True)
    meta = dict(preset.meta)
    meta.update(screen=list(preset.screen),
                saved=datetime.datetime.now().isoformat(timespec="seconds"))
    lines = ["<!-- bdo-ui " + json.dumps(meta) + " -->"]
    for el in preset.els:
        lines.extend(el.lines(LIB_TAG))
    path = lib_path(name)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="latin1")
    os.replace(tmp, path)
    preset.name, preset.meta = name, meta
    return path


def lib_load(name):
    path = lib_path(name)
    if not path.is_file():
        raise BdoUiError(tr("err.no_preset", name=name, path=config.LIB_DIR))
    lines = path.read_text(encoding="latin1").split("\n")
    meta = {}
    if lines and lines[0].startswith("<!-- bdo-ui "):
        meta = json.loads(lines[0][len("<!-- bdo-ui "):-len(" -->")])
        lines = lines[1:]
    els = [el for _, el in parse_elements(lines)]
    return Preset(els, meta.get("screen"), name, meta)


def lib_meta(name):
    """Header of a library entry (screen size, save time) without parsing the layout."""
    try:
        with open(lib_path(name), encoding="latin1") as f:
            line = f.readline().rstrip("\n")
        if line.startswith("<!-- bdo-ui "):
            return json.loads(line[len("<!-- bdo-ui "):-len(" -->")])
    except (BdoUiError, OSError, ValueError):
        pass
    return {}


def profile_path(name):
    return config.LIB_DIR / "skills" / f"{check_name(name)}.json"


def lib_delete(name):
    """Delete a library entry: the layout and its skill profile."""
    lib_path(name).unlink()
    if profile_path(name).is_file():
        profile_path(name).unlink()


def lib_rename(old, new):
    dst = lib_path(new)
    if dst.exists():
        raise BdoUiError(tr("err.exists", name=new))
    lib_path(old).rename(dst)
    if profile_path(old).is_file():
        profile_path(old).rename(profile_path(new))


def preset_from_slot(family, tag):
    els = read_slots(family).get(tag, [])
    if slot_is_empty(els):
        raise BdoUiError(tr("err.slot_empty", tag=tag, family=family))
    return Preset([e.copy() for e in els], meta={"family": family, "from": tag})
