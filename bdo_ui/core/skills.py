# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Skill profiles: what sits in the cooldown and quick slots of a character.

A profile is read from and written to the character file
UserCache/<family>/400/<char>/gameVariable.xml.
"""

import datetime
import json
import os
import re
import shutil
import subprocess

from .. import panels
from ..i18n import tr
from . import config
from .errors import BdoUiError
from .game import _replace, game_running
from .library import profile_path
from .skilldb import fetch_icon, icon_path, skill_names

_QUICK_LINE_RE = re.compile(r'^\t<Quick\w+ Key="(\d+)"[^>]*/>$')
_COOL_LINE_RE = re.compile(r'^\t<SkillCoolTimeSlot SlotNo="(\d+)" SkillNo="\d+"/>$')


def char_file(family, char_id):
    d = config.BDO_DIR / "UserCache" / family / "400" / char_id
    for p in d.iterdir() if d.is_dir() else []:
        if p.name.lower() == "gamevariable.xml":
            return p
    raise BdoUiError(tr("err.no_char_file", char=char_id, family=family))


def skills_profile(name):
    path = profile_path(name)
    if not path.is_file():
        raise BdoUiError(tr("err.no_profile", name=name, path=config.SKILLS_DIR))
    return json.loads(path.read_text(encoding="utf-8"))


def save_profile(name, profile):
    path = profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def characters(family):
    """[(mtime, char_id)] of a family's characters, most recently played first."""
    base = config.BDO_DIR / "UserCache" / family / "400"
    out = []
    for d in base.iterdir() if base.is_dir() else []:
        if d.is_dir() and d.name.startswith("4000"):
            try:
                out.append((char_file(family, d.name).stat().st_mtime, d.name))
            except BdoUiError:
                continue
    return sorted(out, reverse=True)


def capture_profile(family, char_id, keep=None):
    """Snapshot what sits in a character's cooldown and quick slots.

    Only skills are captured from quick slots; items stay untouched on apply.
    `keep` is an older profile whose skill names are carried over.
    """
    text = char_file(family, char_id).read_bytes().decode("latin1")
    cooldown = {slot: int(skill) for slot, skill in re.findall(
        r'<SkillCoolTimeSlot SlotNo="(\d+)" SkillNo="(\d+)"/>', text) if int(skill)}
    quick = {str(int(key) + 1): int(skill) for key, skill in re.findall(
        r'<QuickSlotSkillData Key="(\d+)" SkillNo="(\d+)"', text)}
    memo = dict(_MEMO_LINE_RE.findall(text))
    profile = {"family": family, "char": char_id, "cooldown": cooldown,
               "quick": quick, "memo": memo,
               "captured": datetime.datetime.now().isoformat(timespec="seconds")}
    if keep and keep.get("names"):
        profile["names"] = keep["names"]
    return profile


def _section(text, tag):
    m = re.search(r'<%s Version="\d+">\r\n(.*?)</%s>' % (tag, tag), text, re.S)
    if not m:
        raise BdoUiError(tr("err.no_section", tag=tag))
    return m


_MEMO_BLOCK_RE = re.compile(
    r'<SkillCoolTimeMemo Version="(\d+)"(?:/>|>\r\n(.*?)</SkillCoolTimeMemo>)', re.S)
_MEMO_LINE_RE = re.compile(r'<SkillCoolTimeMemo SkillNo="(\d+)" Memo="([^"]*)"/>')
SKILL_SECTIONS = ("cooldown", "quick", "memo")


def _apply_memos(text, wanted, changes, names):
    """Set cooldown-slot captions. The game keys them by the skill's rank I id."""
    m = _MEMO_BLOCK_RE.search(text)
    if not m:
        raise BdoUiError(tr("err.no_memo_section"))
    memos = {int(k): v for k, v in _MEMO_LINE_RE.findall(m.group(2) or "")}
    for skill, memo in wanted.items():
        if re.search(r'["<>&\r\n]', memo):
            raise BdoUiError(tr("err.bad_memo", memo=memo))
        if memos.get(int(skill)) != memo:
            changes.append(tr("change.memo", skill=names.get(str(skill), skill), memo=memo))
            memos[int(skill)] = memo
    lines = [f'\t<SkillCoolTimeMemo SkillNo="{k}" Memo="{v}"/>' for k, v in sorted(memos.items())]
    block = (f'<SkillCoolTimeMemo Version="{m.group(1)}">\r\n'
             + "".join(line + "\r\n" for line in lines) + "</SkillCoolTimeMemo>")
    return text[:m.start()] + block + text[m.end():]


def plan_skills(profile, only=None):
    """Return (path, old_text, new_text, changes) for a skill profile.

    `only` limits the work to some of SKILL_SECTIONS; other parts of the
    character file are left exactly as the game wrote them.
    """
    sections = tuple(only) if only else SKILL_SECTIONS
    for name in sections:
        if name not in SKILL_SECTIONS:
            raise BdoUiError(tr("err.bad_section", name=name,
                                choices=", ".join(SKILL_SECTIONS)))
    path = char_file(profile["family"], profile["char"])
    old = path.read_bytes().decode("latin1")
    names = dict(skill_names())
    names.update(profile.get("names", {}))
    changes = []

    def rewrite(tag, line_re, wanted, make, change_key):
        nonlocal text
        m = _section(text, tag)
        lines = m.group(1).split("\r\n")
        left = dict(wanted)
        for i, line in enumerate(lines):
            lm = line_re.match(line)
            if lm and lm.group(1) in left:
                skill = left.pop(lm.group(1))
                new_line = make(lm.group(1), skill, line)
                if new_line != line:
                    shown = int(lm.group(1)) + (1 if tag == "QuickSlotData" else 0)
                    changes.append(tr(change_key, slot=shown, skill=names.get(
                        str(skill), skill) if skill else tr("change.empty")))
                    lines[i] = new_line
        if left:
            raise BdoUiError(tr("err.no_entries", tag=tag, slots=", ".join(sorted(left))))
        text = text[:m.start(1)] + "\r\n".join(lines) + text[m.end(1):]

    def quick(key, skill, line):
        def attr(name, default):
            am = re.search(r' %s="([^"]*)"' % name, line)
            return am.group(1) if am else default
        tail = (f'Position="{attr("Position", "0.000000 0.000000")}" '
                f'KeyboardKey="{attr("KeyboardKey", "0")}" Memo="{attr("Memo", "")}"/>')
        if not skill:
            return f'\t<QuickEmpty Key="{key}" {tail}'
        return f'\t<QuickSlotSkillData Key="{key}" SkillNo="{skill}" SkillLevel="1" {tail}'

    def quick_keys(slots):
        # Profiles number quick slots as the game shows them (1..20);
        # the file stores a 0-based Key.
        out = {}
        for slot, skill in slots.items():
            if not 1 <= int(slot) <= 20:
                raise BdoUiError(tr("err.quick_range", slot=slot))
            out[str(int(slot) - 1)] = skill
        return out

    text = old
    if "cooldown" in sections:
        rewrite("SkillCoolTimeSlot", _COOL_LINE_RE, profile.get("cooldown", {}),
                lambda slot, skill, line: f'\t<SkillCoolTimeSlot SlotNo="{slot}" SkillNo="{skill}"/>',
                "change.cooldown")
    if "quick" in sections:
        rewrite("QuickSlotData", _QUICK_LINE_RE, quick_keys(profile.get("quick", {})), quick,
                "change.quick")
    if "memo" in sections and profile.get("memo"):
        text = _apply_memos(text, profile["memo"], changes, names)
    return path, old, text, changes


def profile_for_preset(name):
    """The skill profile that shares a preset's name, or None."""
    try:
        return skills_profile(name) if name else None
    except (BdoUiError, OSError, ValueError):
        return None


def slot_skills(profile):
    """Map panel index -> skill id for the cooldown and quick slots of a profile."""
    out = {}
    for slot, skill in profile.get("cooldown", {}).items():
        n = int(slot)
        if skill and 0 <= n <= 19:
            out[128 + n if n < 10 else 148 + n - 10] = int(skill)
    for slot, skill in profile.get("quick", {}).items():
        if skill and 1 <= int(slot) <= 20:
            out[panels.quick_slot_index(int(slot))] = int(skill)
    return out


def fetch_profile_icons(profile, progress=None):
    """Fetch every missing icon of a profile. Returns (fetched, failed)."""
    import time
    fetched, failed = 0, []
    wanted = sorted(set(slot_skills(profile).values()))
    for skill in wanted:
        if icon_path(skill):
            continue
        try:
            fetch_icon(skill)
            fetched += 1
        except Exception as e:      # network errors must not stop the batch
            failed.append((skill, str(e)))
        if progress:
            progress(skill)
        time.sleep(0.3)
    return fetched, failed


def apply_skills(profile, force=False, only=None):
    """Write cooldown-slot skills, quick-slot skills and memos into a character file."""
    if game_running() and not force:
        raise BdoUiError(tr("err.running"))
    path, old, new, changes = plan_skills(profile, only)
    if new == old:
        return None, changes
    if config.COMMIT_SCRIPT.is_file() and os.access(config.COMMIT_SCRIPT, os.X_OK):
        subprocess.run([str(config.COMMIT_SCRIPT)], capture_output=True, timeout=120)
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = config.BACKUP_DIR / f"char-{profile['char']}-{stamp}.xml"
    shutil.copy2(path, dest)
    tmp = path.with_name(path.name + ".bdo-ui.tmp")
    tmp.write_bytes(new.encode("latin1"))
    shutil.copymode(path, tmp)
    _replace(tmp, path)
    return dest, changes
