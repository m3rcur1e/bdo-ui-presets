# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Where things are: the game's documents folder, the library, the config file.

The folders are module attributes that can change while the program runs
(set_docs, tests), so other modules read them as config.BDO_DIR and so on
instead of importing the names.
"""

import json
import os
import re
import sys
from pathlib import Path

from ..i18n import tr
from .errors import BdoUiError

WINDOWS = sys.platform == "win32"
STEAM_APP_ID = "582660"
PROTON_DOCS = "pfx/drive_c/users/steamuser/Documents/Black Desert"


def _steam_proton_documents():
    """Find the game's Documents folder inside a Steam/Proton prefix (Linux)."""
    home = Path.home()
    roots = [home / ".steam/steam", home / ".local/share/Steam",
             home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    libraries = []
    for root in roots:
        libraries.append(root)
        try:
            text = (root / "steamapps/libraryfolders.vdf").read_text(errors="ignore")
        except OSError:
            continue
        libraries += [Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', text)]
    for lib in libraries:
        docs = lib / "steamapps/compatdata" / STEAM_APP_ID / PROTON_DOCS
        if docs.is_dir():
            return docs
    return None


def _windows_documents():
    """The user's Documents folder (it may be redirected, e.g. to OneDrive)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                        ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        fid = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                   (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0 and out.value:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception:
        pass
    return Path.home() / "Documents"


CONFIG_PATH = Path.home() / ".bdo" / "bdo-ui.json"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(**values):
    """Update some keys of the config file, keeping the rest."""
    config = load_config()
    config.update(values)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=1), encoding="utf-8")


def docs_valid(path=None):
    """True if the folder looks like the game's 'Black Desert' documents folder."""
    return (Path(path) if path else BDO_DIR).joinpath("UserCache").is_dir()


def normalize_docs(path):
    """Accept the folder itself, its parent, or its UserCache subfolder."""
    path = Path(path)
    for cand in (path, path / "Black Desert", path.parent):
        if docs_valid(cand):
            return cand
    return None


def set_docs(path):
    """Remember a hand-picked game folder and switch to it."""
    global BDO_DIR
    docs = normalize_docs(path)
    if not docs:
        raise BdoUiError(tr("err.not_docs", path=path))
    save_config(docs=str(docs))
    BDO_DIR = docs
    return docs


def _default_docs():
    # Order: explicit env override, folder saved by the picker, auto-detection.
    if os.environ.get("BDO_DOCS"):
        return Path(os.environ["BDO_DOCS"])
    saved = load_config().get("docs")
    if saved and docs_valid(saved):
        return Path(saved)
    if WINDOWS:
        return _windows_documents() / "Black Desert"
    return _steam_proton_documents() or Path.home() / "Documents" / "Black Desert"


BDO_DIR = _default_docs()
LIB_DIR = Path(os.environ.get("BDO_UI_LIB", Path.home() / ".bdo" / "ui-presets"))
BACKUP_DIR = LIB_DIR / ".backups"
COMMIT_SCRIPT = Path.home() / "bin" / "bdo-settings-commit"
SKILLS_DIR = LIB_DIR / "skills"
ICON_DIR = LIB_DIR / "icons"
SKILL_DB = ICON_DIR / "skills.json"
CHAR_REGISTRY = LIB_DIR / "characters.json"
