"""Self-update from the project's GitHub repository.

The installed version is the VERSION file next to this module. A newer one is
looked up in the same file on the default branch of REPO; a release is
therefore "bump VERSION and push".

    check()    -> the newer version available, or None
    install()  -> bring the program folder to that version

A folder that is a git checkout is updated with `git pull --ff-only`; any
other copy gets the branch archive downloaded and unpacked over it, with the
replaced files kept in .update-backup/. Only the standard library is used and
nothing but the fixed GitHub URLs below is contacted.
"""

import io
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from i18n import tr

REPO = "m3rcur1e/bdo-ui-presets"
BRANCH = "main"
VERSION_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/VERSION"
ARCHIVE_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
PAGE_URL = f"https://github.com/{REPO}"

APP_DIR = Path(__file__).resolve().parent
BACKUP_DIR = APP_DIR / ".update-backup"
USER_AGENT = "bdo-ui-updater"
TIMEOUT = 10                        # seconds, per request
MAX_ARCHIVE = 64 * 1024 * 1024      # refuse anything larger than this
REQUIRED = ("main.py", "core.py", "gui.py", "VERSION")


class UpdateError(Exception):
    pass


def parse_version(text):
    """'1.2.3' -> (1, 2, 3); anything unparsable sorts lowest."""
    parts = []
    for piece in str(text).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def local_version(folder=None):
    try:
        return (Path(folder or APP_DIR) / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def _fetch(url, limit):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError(tr("update.err.missing", repo=REPO)) from e
        raise UpdateError(tr("update.err.network", reason=f"HTTP {e.code}")) from e
    except (OSError, ValueError) as e:
        raise UpdateError(tr("update.err.network", reason=getattr(e, "reason", e))) from e
    if len(data) > limit:
        raise UpdateError(tr("update.err.broken"))
    return data


def remote_version():
    text = _fetch(VERSION_URL, 64).decode("ascii", "replace").strip()
    if not parse_version(text):
        raise UpdateError(tr("update.err.broken"))
    return text


def check():
    """The version available on GitHub if it is newer than this copy, else None."""
    remote = remote_version()
    return remote if parse_version(remote) > parse_version(local_version()) else None


def is_git_checkout():
    return (APP_DIR / ".git").exists()


def _git(*args):
    try:
        return subprocess.run(
            ["git", "-C", str(APP_DIR), *args], capture_output=True, text=True,
            timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise UpdateError(tr("update.err.git", reason=e)) from e


def _pull():
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != BRANCH:
        # A development checkout: leave it to its owner.
        raise UpdateError(tr("update.err.branch", branch=branch or "?", main=BRANCH))
    result = _git("pull", "--ff-only")
    if result.returncode != 0:
        reason = (result.stderr or result.stdout).strip().splitlines()
        raise UpdateError(tr("update.err.git", reason=reason[-1] if reason else "?"))


def _unpack(data, dest):
    """Unpack the branch archive into `dest`; return the folder with the program."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise UpdateError(tr("update.err.broken")) from e
    root = Path(dest).resolve()
    for info in archive.infolist():
        target = (root / info.filename).resolve()
        if root != target and root not in target.parents:
            raise UpdateError(tr("update.err.broken"))      # path escapes the folder
    archive.extractall(root)
    tops = [p for p in root.iterdir() if p.is_dir()]
    if len(tops) != 1 or not all((tops[0] / name).is_file() for name in REQUIRED):
        raise UpdateError(tr("update.err.broken"))
    for path in tops[0].rglob("*.py"):
        try:                        # a truncated download must not replace working code
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (SyntaxError, UnicodeDecodeError, OSError) as e:
            raise UpdateError(tr("update.err.broken")) from e
    return tops[0]


def _copy_over(source, version_from):
    """Copy the new files over the program folder, keeping what they replace."""
    backup = BACKUP_DIR / version_from
    try:
        if backup.exists():
            shutil.rmtree(backup)
        files = [p for p in sorted(source.rglob("*")) if p.is_file()]
        # VERSION goes last: an interrupted copy is then retried on the next check.
        files.sort(key=lambda p: p.name == "VERSION")
        for path in files:
            rel = path.relative_to(source)
            target = APP_DIR / rel
            if target.is_file() and target.read_bytes() == path.read_bytes():
                continue
            if target.is_file():
                (backup / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup / rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".new")
            shutil.copyfile(path, tmp)
            os.replace(tmp, target)
    except OSError as e:
        raise UpdateError(tr("update.err.write", folder=APP_DIR, reason=e)) from e


def install():
    """Update the program folder; return the version it is at afterwards."""
    before = local_version()
    if is_git_checkout():
        _pull()
    else:
        data = _fetch(ARCHIVE_URL, MAX_ARCHIVE)
        with tempfile.TemporaryDirectory(prefix="bdo-ui-update-") as tmp:
            source = _unpack(data, tmp)
            if parse_version(local_version(source)) <= parse_version(before):
                raise UpdateError(tr("update.err.same", version=before))
            _copy_over(source, before)
    return local_version()
