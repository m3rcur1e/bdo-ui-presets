# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""The game side: families, the three preset slots of a family file, backups.

The game keeps three UI preset slots per family in
UserCache/<family>/gamevariable.xml as flat lines:

    <UISettingPreset Version="1">
        <UISettingPreset0 Index=".." PosX=".." RelativePosX=".." .../>
        ...
    </UISettingPreset>
"""

import datetime
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ..i18n import tr
from . import config
from .config import WINDOWS
from .errors import BdoUiError
from .layout import parse_elements

GAME_EXE = "blackdesert64.exe"
GAME_WINDOW_CLASS = "steam_app_" + "582660"
KEEP_BACKUPS = 30
SLOT_TAGS = ["UISettingPreset0", "UISettingPreset1", "UISettingPreset2"]
REVERT_TAG = "UISettingRevert"
_BLOCK_RE = re.compile(
    rb'<UISettingPreset Version="(\d+)"(?:/>|>(.*?)\r?\n</UISettingPreset>)', re.S)


def families():
    """Family ids that have a settings file, most recently used first."""
    found = []
    cache = config.BDO_DIR / "UserCache"
    if not cache.is_dir():
        raise BdoUiError(tr("err.no_settings", path=config.BDO_DIR))
    for d in cache.iterdir():
        f = d / "gamevariable.xml"
        if d.is_dir() and d.name.isdigit() and len(d.name) > 3 and f.is_file():
            found.append((f.stat().st_mtime, d.name))
    return [name for _, name in sorted(found, reverse=True)]


def family_file(family):
    return config.BDO_DIR / "UserCache" / family / "gamevariable.xml"


def _read_block(family):
    path = family_file(family)
    data = path.read_bytes()
    m = _BLOCK_RE.search(data)
    if not m:
        raise BdoUiError(tr("err.no_block", path=path))
    body = m.group(2) or b""
    lines = body.decode("latin1").replace("\r\n", "\n").split("\n")
    return data, m, parse_elements(lines)


def read_slots(family):
    """Return {tag: [El]} for every tag present in the preset block."""
    _, _, entries = _read_block(family)
    slots = {}
    for tag, el in entries:
        slots.setdefault(tag, []).append(el)
    return slots


def slot_is_empty(els):
    return not any(el.index is not None for el in els or [])


def _replace(tmp, path):
    """Atomically move tmp over path; explain the usual Windows failure."""
    try:
        os.replace(tmp, path)
    except PermissionError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise BdoUiError(tr("err.locked", name=path.name))


def game_running():
    if WINDOWS:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH"],
                capture_output=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            return False
        return GAME_EXE.encode() in out.lower()
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if GAME_EXE.encode() in (p / "cmdline").read_bytes().lower():
                return True
        except OSError:
            continue
    return False


def backup(family):
    """Commit the settings repo (if set up) and keep a plain copy of the file."""
    if config.COMMIT_SCRIPT.is_file() and os.access(config.COMMIT_SCRIPT, os.X_OK):
        subprocess.run([str(config.COMMIT_SCRIPT)], capture_output=True, timeout=120)
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = config.BACKUP_DIR / f"{family}-{stamp}.xml"
    shutil.copy2(family_file(family), dest)
    old = sorted(config.BACKUP_DIR.glob(f"{family}-*.xml"))[:-KEEP_BACKUPS]
    for f in old:
        f.unlink()
    return dest


def write_slot(family, slot, els, force=False):
    """Replace game slot `slot` (0..2) with `els`. Game must be closed."""
    if game_running() and not force:
        raise BdoUiError(tr("err.running"))
    target = SLOT_TAGS[slot]
    data, m, entries = _read_block(family)
    backup_path = backup(family)

    groups, order = {}, []
    for tag, el in entries:
        if tag not in groups:
            groups[tag] = []
            order.append(tag)
        groups[tag].append(el)
    if target not in groups:
        # Keep slots in numeric order, ahead of Revert / BattlePreset.
        later = [t for t in order if t not in SLOT_TAGS or t > target]
        pos = order.index(later[0]) if later else len(order)
        order.insert(pos, target)
    groups[target] = els

    lines = [f'<UISettingPreset Version="{m.group(1).decode()}">']
    for tag in order:
        for el in groups[tag]:
            lines.extend(el.lines(tag))
    lines.append("</UISettingPreset>")
    block = "\r\n".join(lines).encode("latin1")

    path = family_file(family)
    tmp = path.with_name(path.name + ".bdo-ui.tmp")
    tmp.write_bytes(data[:m.start()] + block + data[m.end():])
    shutil.copymode(path, tmp)
    _replace(tmp, path)
    return backup_path


def ui_scale():
    try:
        text = (config.BDO_DIR / "GameOption.txt").read_text(encoding="latin1")
        m = re.search(r"^uiScale\s*=\s*([\d.]+)", text, re.M)
        return float(m.group(1)) if m else 1.0
    except OSError:
        return 1.0


def _windows_game_client_size():
    """Client-area size in pixels of the game window, or None."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value.upper().startswith("BLACK DESERT"):
                    rect = wintypes.RECT()
                    user32.GetClientRect(hwnd, ctypes.byref(rect))
                    if rect.right > 400:
                        found.append((rect.right, rect.bottom))
            return True

        user32.EnumWindows(visit, 0)
        return found[0] if found else None
    except Exception:
        return None


def game_window_screen():
    """Screen size in UI units of the running game window, or None."""
    if WINDOWS:
        size = _windows_game_client_size()
        if not size:
            return None
        s = ui_scale()
        return (round(size[0] / s), round(size[1] / s))
    try:
        clients = json.loads(subprocess.run(
            ["hyprctl", "clients", "-j"], capture_output=True, timeout=5).stdout)
        monitors = json.loads(subprocess.run(
            ["hyprctl", "monitors", "-j"], capture_output=True, timeout=5).stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    scale_by_id = {m["id"]: m.get("scale", 1.0) for m in monitors}
    for c in clients:
        if c.get("class") == GAME_WINDOW_CLASS and c["size"][0] > 400:
            px = scale_by_id.get(c.get("monitor"), 1.0) if c.get("xwayland") else 1.0
            s = ui_scale()
            return (round(c["size"][0] * px / s), round(c["size"][1] * px / s))
    return None
