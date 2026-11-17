# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Skill data from bdocodex.com: names, icons and the class a skill belongs to."""

import json
import re

from ..i18n import tr
from . import config
from .errors import BdoUiError

ICON_SOURCE = "https://bdocodex.com/us/skill/{}/"


def icon_path(skill):
    """Cached icon file of a skill, or None."""
    for path in config.ICON_DIR.glob(f"{int(skill)}.*") if config.ICON_DIR.is_dir() else []:
        return path
    return None


def fetch_icon(skill):
    """Download a skill icon from bdocodex into the cache; return its path."""
    import urllib.request
    headers = {"User-Agent": "Mozilla/5.0"}
    page = urllib.request.urlopen(urllib.request.Request(
        ICON_SOURCE.format(int(skill)), headers=headers), timeout=20
    ).read().decode("utf-8", "ignore")
    m = re.search(r'og:image" content="([^"]+)"', page)
    if not m:
        raise BdoUiError(tr("err.no_icon", skill=skill))
    url = m.group(1)
    ext = url.rsplit(".", 1)[-1].lower() if "." in url.rsplit("/", 1)[-1] else "webp"
    data = urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=20).read()
    config.ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = config.ICON_DIR / f"{int(skill)}.{ext}"
    path.write_bytes(data)
    title = re.search(r'og:title" content="([^"]+)"', page)
    if title:
        names = skill_names()
        names[str(int(skill))] = title.group(1).replace("&#039;", "'").replace("&amp;", "&")
        (config.ICON_DIR / "names.json").write_text(
            json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def skill_names():
    """Skill id -> name, learned while downloading icons."""
    try:
        return json.loads((config.ICON_DIR / "names.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def skill_name(skill, profile=None):
    name = ((profile or {}).get("names", {}).get(str(skill))
            or skill_names().get(str(skill)) or skill_db().get(str(skill), [None])[0])
    return name or tr("skill.unknown", id=skill)


SKILL_DB_SOURCE = "https://bdocodex.com/query.php?a=skills&type=sorceress&l=us"

_skill_db = None


def skill_db():
    """Skill id -> [name, class] for every class, or {} until fetched."""
    global _skill_db
    if _skill_db is None:
        try:
            _skill_db = json.loads(config.SKILL_DB.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return _skill_db


def fetch_skill_db():
    """Download the skill list of all classes from bdocodex (one request, ~5 MB)."""
    global _skill_db
    import html
    import urllib.request
    # This class filter is ignored by the site, so the reply covers every class.
    raw = urllib.request.urlopen(urllib.request.Request(
        SKILL_DB_SOURCE, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    rows = json.loads(raw.decode("utf-8-sig"))["aaData"]
    db = {str(r[0]): [html.unescape(re.sub(r"<[^>]+>", "", r[2])).strip(), r[4]] for r in rows}
    if len({v[1] for v in db.values()}) < 5:
        raise BdoUiError(tr("err.skill_db"))
    config.ICON_DIR.mkdir(parents=True, exist_ok=True)
    config.SKILL_DB.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    _skill_db = db
    return db


def char_class(skills):
    """(class, spec) guessed from the skills sitting in a character's slots."""
    db = skill_db()
    votes, prime = {}, 0
    for skill in skills:
        name, cls = db.get(str(skill), ("", None))
        if cls and cls != "Agent":          # "Agent" = skills shared by all classes
            votes[cls] = votes.get(cls, 0) + 1
            prime += name.startswith(("Prime:", "Succession:"))
    if not votes:
        return None, None
    cls = max(votes, key=votes.get)
    if cls.startswith("NEW_CLASS"):         # placeholder rows in the source list
        return None, None
    # Too few skills in the slots to tell the spec apart.
    spec = ("Succession" if prime >= 3 else "Awakening") if votes[cls] >= 6 else None
    return cls, spec
