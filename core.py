"""BDO UI preset library: parse / edit / write the UISettingPreset slots.

The game keeps three UI preset slots per family in
UserCache/<family>/gamevariable.xml as flat lines:

    <UISettingPreset Version="1">
        <UISettingPreset0 Index=".." PosX=".." RelativePosX=".." .../>
        ...
    </UISettingPreset>

RelativePos is the panel centre divided by the screen size (in UI units), so
both the screen size and every panel size can be recovered from a preset.
"""

import datetime
import json
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
from pathlib import Path

import panels
from i18n import tr

WINDOWS = sys.platform == "win32"
GAME_EXE = "blackdesert64.exe"
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
GAME_WINDOW_CLASS = "steam_app_" + "582660"
KEEP_BACKUPS = 30

SLOT_TAGS = ["UISettingPreset0", "UISettingPreset1", "UISettingPreset2"]
REVERT_TAG = "UISettingRevert"
LIB_TAG = "Preset"
DEFAULT_SCREEN = (1920, 1080)

_OPEN_RE = re.compile(r'^\t<(\w+)((?: \w+="[^"]*")*) ?(/?)>$')
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
_BLOCK_RE = re.compile(
    rb'<UISettingPreset Version="(\d+)"(?:/>|>(.*?)\r?\n</UISettingPreset>)', re.S)
_NAME_RE = re.compile(r'^[\w][\w .\-]{0,60}$')


class BdoUiError(Exception):
    pass


# ---------------------------------------------------------------- elements

class El:
    """One top-level entry of a preset slot (a panel, or the bare slot marker)."""

    __slots__ = ("attrs", "children")

    def __init__(self, attrs, children=None):
        self.attrs = attrs          # ordered list of [key, value]
        self.children = children    # raw child lines, or None when self-closed

    def get(self, key, default=None):
        for k, v in self.attrs:
            if k == key:
                return v
        return default

    def set(self, key, value):
        for pair in self.attrs:
            if pair[0] == key:
                pair[1] = value
                return
        self.attrs.append([key, value])

    @property
    def index(self):
        v = self.get("Index")
        return int(v) if v is not None else None

    @property
    def positioned(self):
        return self.get("PosX") is not None

    @property
    def shown(self):
        return self.get("IsShow") == "true"

    def label(self):
        idx = self.index
        if idx is None:
            return tr("panel.marker")
        return panels.name(idx, int(self.get("WindowIndex", "0")))

    def short_label(self):
        return panels.SHORT.get(self.index) or self.label()

    def lines(self, tag):
        attrs = "".join(f' {k}="{v}"' for k, v in self.attrs)
        if self.children is None:
            return [f"\t<{tag}{attrs}/>"]
        return [f"\t<{tag}{attrs}>", *self.children, f"\t</{tag}>"]

    def copy(self):
        return El([list(p) for p in self.attrs],
                  None if self.children is None else list(self.children))


def parse_elements(lines):
    """Parse slot lines into [(tag, El)], keeping child lines verbatim."""
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip():
            continue
        m = _OPEN_RE.match(line)
        if not m:
            raise BdoUiError(tr("err.bad_line", line=line[:80]))
        tag, attr_text, closed = m.groups()
        attrs = [[k, v] for k, v in _ATTR_RE.findall(attr_text)]
        children = None
        if not closed:
            children = []
            end = f"\t</{tag}>"
            while i < len(lines) and lines[i] != end:
                children.append(lines[i])
                i += 1
            if i >= len(lines):
                raise BdoUiError(tr("err.unterminated", tag=tag))
            i += 1
        out.append((tag, El(attrs, children)))
    return out


# ---------------------------------------------------------------- geometry

def fmt_rel(v):
    # The game stores these as 32-bit floats printed with 6 significant digits.
    return "%.6g" % struct.unpack("f", struct.pack("f", v))[0]


def estimate_screen(els, fallback=DEFAULT_SCREEN):
    """Recover the screen size (UI units) a preset was saved at."""
    result = []
    for axis, size_i in (("X", 0), ("Y", 1)):
        samples = []
        for el in els:
            if not el.positioned:
                continue
            size = None
            explicit = el.get("Size" + axis)
            if explicit is not None and float(explicit) > 0:
                size = float(explicit)
            elif el.index in panels.FIXED_SIZES:
                size = panels.FIXED_SIZES[el.index][size_i]
            rel = float(el.get("RelativePos" + axis, "0"))
            if size is None or rel < 0.05:
                continue
            samples.append((rel, (float(el.get("Pos" + axis)) + size / 2) / rel))
        if not samples:
            result.append(fallback[size_i])
            continue
        # Larger rel -> less rounding noise; use the better half.
        samples.sort(reverse=True)
        best = samples[:max(3, len(samples) // 2)]
        result.append(round(statistics.median(s[1] for s in best)))
    return tuple(result)


def panel_size(el, screen):
    """Panel size in UI units, derived from RelativePos (centre / screen)."""
    out = []
    for axis, total, size_i in (("X", screen[0], 0), ("Y", screen[1], 1)):
        explicit = el.get("Size" + axis)
        if explicit is not None and float(explicit) > 0:
            out.append(round(float(explicit)))
            continue
        rel = float(el.get("RelativePos" + axis, "0"))
        size = round(2 * (rel * total - float(el.get("Pos" + axis))))
        if not 4 <= size <= total:
            size = panels.FIXED_SIZES.get(el.index, (50, 50))[size_i]
        out.append(size)
    return tuple(out)


def set_position(el, x, y, size, screen):
    el.set("PosX", str(int(x)))
    el.set("PosY", str(int(y)))
    el.set("RelativePosX", fmt_rel((x + size[0] / 2) / screen[0]))
    el.set("RelativePosY", fmt_rel((y + size[1] / 2) / screen[1]))


# ---------------------------------------------------------------- game file

def families():
    """Family ids that have a settings file, most recently used first."""
    found = []
    cache = BDO_DIR / "UserCache"
    if not cache.is_dir():
        raise BdoUiError(tr("err.no_settings", path=BDO_DIR))
    for d in cache.iterdir():
        f = d / "gamevariable.xml"
        if d.is_dir() and d.name.isdigit() and len(d.name) > 3 and f.is_file():
            found.append((f.stat().st_mtime, d.name))
    return [name for _, name in sorted(found, reverse=True)]


def family_file(family):
    return BDO_DIR / "UserCache" / family / "gamevariable.xml"


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
    if COMMIT_SCRIPT.is_file() and os.access(COMMIT_SCRIPT, os.X_OK):
        subprocess.run([str(COMMIT_SCRIPT)], capture_output=True, timeout=120)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"{family}-{stamp}.xml"
    shutil.copy2(family_file(family), dest)
    old = sorted(BACKUP_DIR.glob(f"{family}-*.xml"))[:-KEEP_BACKUPS]
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


# ---------------------------------------------------------------- library

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
    return LIB_DIR / f"{check_name(name)}.xml"


def lib_list():
    if not LIB_DIR.is_dir():
        return []
    return sorted((p.stem for p in LIB_DIR.glob("*.xml")), key=str.lower)


def lib_save(preset, name):
    LIB_DIR.mkdir(parents=True, exist_ok=True)
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
        raise BdoUiError(tr("err.no_preset", name=name, path=LIB_DIR))
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
    return LIB_DIR / "skills" / f"{check_name(name)}.json"


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


# ---------------------------------------------------------------- misc

def ui_scale():
    try:
        text = (BDO_DIR / "GameOption.txt").read_text(encoding="latin1")
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


# ---------------------------------------------------------------- character skills

SKILLS_DIR = LIB_DIR / "skills"
_QUICK_LINE_RE = re.compile(r'^\t<Quick\w+ Key="(\d+)"[^>]*/>$')
_COOL_LINE_RE = re.compile(r'^\t<SkillCoolTimeSlot SlotNo="(\d+)" SkillNo="\d+"/>$')


def char_file(family, char_id):
    d = BDO_DIR / "UserCache" / family / "400" / char_id
    for p in d.iterdir() if d.is_dir() else []:
        if p.name.lower() == "gamevariable.xml":
            return p
    raise BdoUiError(tr("err.no_char_file", char=char_id, family=family))


def skills_profile(name):
    path = profile_path(name)
    if not path.is_file():
        raise BdoUiError(tr("err.no_profile", name=name, path=SKILLS_DIR))
    return json.loads(path.read_text(encoding="utf-8"))


def save_profile(name, profile):
    path = profile_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def characters(family):
    """[(mtime, char_id)] of a family's characters, most recently played first."""
    base = BDO_DIR / "UserCache" / family / "400"
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


# ---------------------------------------------------------------- skill icons

ICON_DIR = LIB_DIR / "icons"
ICON_SOURCE = "https://bdocodex.com/us/skill/{}/"


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


def icon_path(skill):
    """Cached icon file of a skill, or None."""
    for path in ICON_DIR.glob(f"{int(skill)}.*") if ICON_DIR.is_dir() else []:
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
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    path = ICON_DIR / f"{int(skill)}.{ext}"
    path.write_bytes(data)
    title = re.search(r'og:title" content="([^"]+)"', page)
    if title:
        names = skill_names()
        names[str(int(skill))] = title.group(1).replace("&#039;", "'").replace("&amp;", "&")
        (ICON_DIR / "names.json").write_text(
            json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def skill_names():
    """Skill id -> name, learned while downloading icons."""
    try:
        return json.loads((ICON_DIR / "names.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def skill_name(skill, profile=None):
    name = ((profile or {}).get("names", {}).get(str(skill))
            or skill_names().get(str(skill)) or skill_db().get(str(skill), [None])[0])
    return name or tr("skill.unknown", id=skill)


# ---------------------------------------------------------------- characters

SKILL_DB = ICON_DIR / "skills.json"
SKILL_DB_SOURCE = "https://bdocodex.com/query.php?a=skills&type=sorceress&l=us"
CHAR_REGISTRY = LIB_DIR / "characters.json"
_skill_db = None


def skill_db():
    """Skill id -> [name, class] for every class, or {} until fetched."""
    global _skill_db
    if _skill_db is None:
        try:
            _skill_db = json.loads(SKILL_DB.read_text(encoding="utf-8"))
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
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    SKILL_DB.write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    _skill_db = db
    return db


def char_registry():
    """Names given to characters by the user (the game keeps them server-side)."""
    try:
        return json.loads(CHAR_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_char_name(char_id, name):
    reg = char_registry()
    reg.setdefault(char_id, {})["name"] = name.strip()
    LIB_DIR.mkdir(parents=True, exist_ok=True)
    CHAR_REGISTRY.write_text(json.dumps(reg, indent=1, ensure_ascii=False), encoding="utf-8")


def game_char_order(family):
    """Characters that exist in the game's selection screen: {char_id: order}."""
    try:
        text = family_file(family).read_bytes().decode("latin1")
    except OSError:
        return {}
    return {c: int(o) for c, o in re.findall(
        r'<CharacterOrderList CharacterNo="(\d+)" Order="(\d+)"/>', text)}


def portrait_path(char_id):
    path = BDO_DIR / "FaceTexture" / f"{char_id}.bmp"
    return path if path.is_file() else None


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
    if COMMIT_SCRIPT.is_file() and os.access(COMMIT_SCRIPT, os.X_OK):
        subprocess.run([str(COMMIT_SCRIPT)], capture_output=True, timeout=120)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = BACKUP_DIR / f"char-{profile['char']}-{stamp}.xml"
    shutil.copy2(path, dest)
    tmp = path.with_name(path.name + ".bdo-ui.tmp")
    tmp.write_bytes(new.encode("latin1"))
    shutil.copymode(path, tmp)
    _replace(tmp, path)
    return dest, changes
