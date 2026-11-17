#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Build the portable Windows package of bdo-ui.

    python3 tools/build_windows.py [--out dist]

The result is dist/bdo-ui-<version>-windows-x64.zip: the program as committed
(git HEAD), plus a "python" folder with the official embeddable Python and the
few parts of Qt the editor uses. Unpack anywhere, start bdo-ui.bat; nothing
has to be installed.

Runs on any system: the Windows files are only downloaded and repacked, never
executed. Downloads (python.org, pypi.org) are checked against the hashes
below and kept in <out>/cache. The archive is reproducible: file order and
timestamps do not depend on the machine it was built on.

To move to a newer Python or Qt, change the versions and hashes below.
"""

import argparse
import hashlib
import io
import json
import os
import struct
import subprocess
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent

PYTHON_VERSION = "3.14.10"
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"
PYTHON_URL = (f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
              f"python-{PYTHON_VERSION}-embed-amd64.zip")

# (project on PyPI, version, sha256 of the win_amd64 wheel)
WHEELS = (
    ("PySide6-Essentials", "6.12.0",
     "c9a95102aa23c1f86516a30d5a9be37552d324eee7e567eb7508973f1218cb42"),
    ("shiboken6", "6.12.0",
     "a1906cb8116869178c64b6bab52623bbc8b4ceed7b30bfc3c9aa0f6e67f6438e"),
)
WHEEL_TAG = "win_amd64"

# What the editor needs from Qt. Everything these files link against is found
# and added automatically; the rest of the wheel is left out.
QT_ROOTS = (
    "PySide6/QtCore.pyd",
    "PySide6/QtGui.pyd",
    "PySide6/QtWidgets.pyd",
    "PySide6/plugins/platforms/qwindows.dll",
    "PySide6/plugins/platforms/qoffscreen.dll",
    "PySide6/plugins/styles/qmodernwindowsstyle.dll",
    "PySide6/plugins/imageformats/qjpeg.dll",
    "PySide6/plugins/imageformats/qgif.dll",
    "PySide6/plugins/imageformats/qico.dll",
    "PySide6/plugins/imageformats/qwebp.dll",
)
BINARY = (".dll", ".pyd", ".exe", ".lib")
TOP = "bdo-ui"
SITE = "python/Lib/site-packages"
USER_AGENT = "bdo-ui-build"

THIRD_PARTY = """\
Third-party software in this folder
===================================

Python {python}, (c) Python Software Foundation, PSF License Agreement:
LICENSE.txt in this folder. https://www.python.org/

Qt for Python (PySide6 {qt}) and Qt {qt}, (c) The Qt Company Ltd and other
contributors, used under the GNU Lesser General Public License version 3.
Only the QtCore, QtGui and QtWidgets modules and a few plugins are included,
unmodified, as shipped in the PySide6-Essentials and shiboken6 packages on
https://pypi.org/. Sources: https://code.qt.io/ and
https://download.qt.io/official_releases/QtForPython/
The licence texts: https://www.gnu.org/licenses/lgpl-3.0.txt and
https://www.gnu.org/licenses/gpl-3.0.txt (also LICENSE in the program folder).

The Microsoft Visual C++ runtime libraries next to them are redistributed as
shipped with those packages.
"""


def fetch(url, sha256, cache):
    """Download `url` into the cache (once) and check its hash."""
    path = cache / url.rsplit("/", 1)[1]
    if not path.exists():
        print(f"download {url}", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        path.write_bytes(data)
    data = path.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        path.unlink()
        raise SystemExit(f"{path.name}: sha256 is {got}, expected {sha256}")
    return data


def wheel_url(project, version, sha256):
    url = f"https://pypi.org/pypi/{project}/{version}/json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        info = json.load(r)
    for f in info["urls"]:
        if f["filename"].endswith(f"{WHEEL_TAG}.whl") and f["digests"]["sha256"] == sha256:
            return f["url"]
    raise SystemExit(f"{project} {version}: no {WHEEL_TAG} wheel with the pinned hash")


def fetch_wheel(project, version, sha256, cache):
    for path in cache.glob("*.whl"):
        if hashlib.sha256(path.read_bytes()).hexdigest() == sha256:
            return path.read_bytes()
    return fetch(wheel_url(project, version, sha256), sha256, cache)


def pe_imports(data):
    """Names of the DLLs a Windows binary links against (also delay-loaded)."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        return []
    sections, opt_size = struct.unpack_from("<H", data, pe + 6)[0], \
        struct.unpack_from("<H", data, pe + 20)[0]
    opt = pe + 24
    dirs = opt + (112 if struct.unpack_from("<H", data, opt)[0] == 0x20B else 96)
    table = []
    for i in range(sections):
        vsize, va, rsize, raw = struct.unpack_from("<IIII", data, opt + opt_size + 40 * i + 8)
        table.append((va, max(vsize, rsize), raw))

    def offset(rva):
        for va, size, raw in table:
            if va <= rva < va + size:
                return rva - va + raw
        return None

    def name(rva):
        at = offset(rva)
        return data[at:data.index(b"\0", at)].decode("ascii", "replace") if at else None

    found = []
    # (data directory index, descriptor size, offset of the name RVA in it)
    for index, size, name_at in ((1, 20, 12), (13, 32, 4)):
        at = offset(struct.unpack_from("<I", data, dirs + 8 * index)[0])
        while at is not None:
            entry = data[at:at + size]
            if len(entry) < size or not any(entry):
                break
            dll = name(struct.unpack_from("<I", entry, name_at)[0])
            if dll:
                found.append(dll)
            at += size
    return found


def qt_files(wheel, languages):
    """Paths inside the PySide6 wheel that go into the package."""
    names = wheel.namelist()
    by_name = {PurePosixPath(n).name.lower(): n for n in names
               if n.startswith("PySide6/") and n.count("/") == 1}
    keep, queue = set(), list(QT_ROOTS)
    while queue:
        path = queue.pop()
        if path in keep:
            continue
        if path not in names:
            raise SystemExit(f"{path} is not in the PySide6 wheel")
        keep.add(path)
        for dll in pe_imports(wheel.read(path)):
            if dll.lower() in by_name:
                queue.append(by_name[dll.lower()])
    for n in names:
        if n.endswith("/") or "__pycache__" in n:
            continue
        top = n.split("/")[0]
        if top.endswith(".dist-info"):
            keep.add(n)                       # metadata and licence notes
        elif n.startswith("PySide6/") and n.endswith(".py") and (
                n.count("/") == 1 or n.startswith("PySide6/support/")):
            keep.add(n)
        elif n.startswith("PySide6/translations/qtbase_") and \
                PurePosixPath(n).stem[len("qtbase_"):] in languages:
            keep.add(n)                       # texts of the standard dialogs
    return sorted(keep)


def sources():
    """Committed files of the program: {path: bytes}, as a checkout on Windows."""
    data = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "HEAD"],
                          check=True, capture_output=True).stdout
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}


def commit_time():
    """Time of the commit being packaged, in UTC, as a zip timestamp."""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%cd",
                          "--date=format-local:%Y %m %d %H %M %S", "HEAD"],
                         check=True, capture_output=True, text=True,
                         env={**os.environ, "TZ": "UTC"}).stdout
    return tuple(int(x) for x in out.split())


def build(out):
    cache = out / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    files = {}                                # path inside the package -> bytes

    program = sources()
    version = program["VERSION"].decode().strip()
    files.update(program)
    languages = {PurePosixPath(n).stem for n in program if n.startswith("bdo_ui/lang/")}

    with zipfile.ZipFile(io.BytesIO(fetch(PYTHON_URL, PYTHON_SHA256, cache))) as z:
        for n in z.namelist():
            if n.endswith("/"):
                continue
            data = z.read(n)
            if n.endswith("._pth"):
                # The interpreter looks for modules only where this file says.
                data = "\r\n".join([Path(n).stem + ".zip", ".", "Lib\\site-packages", ""]).encode()
            files[f"python/{n}"] = data

    qt_version = ""
    for project, wheel_version, sha256 in WHEELS:
        with zipfile.ZipFile(io.BytesIO(fetch_wheel(project, wheel_version, sha256, cache))) as z:
            if project.lower().startswith("pyside6"):
                qt_version = wheel_version
                keep = qt_files(z, languages)
            else:
                keep = [n for n in z.namelist() if not n.endswith("/")
                        and not n.endswith(".lib") and "/include/" not in n
                        and "__pycache__" not in n]
            for n in keep:
                files[f"{SITE}/{n}"] = z.read(n)

    files["python/THIRD-PARTY.txt"] = THIRD_PARTY.format(
        python=PYTHON_VERSION, qt=qt_version).replace("\n", "\r\n").encode()

    # Every Qt or runtime library a kept binary asks for must be in the package.
    shipped = {PurePosixPath(n).name.lower() for n in files}
    for n, data in files.items():
        if n.startswith(SITE) and n.lower().endswith(BINARY):
            for dll in pe_imports(data):
                low = dll.lower()
                if low.startswith(("qt6", "pyside6", "shiboken6", "msvcp", "vcruntime",
                                   "concrt", "python3")) and low not in shipped:
                    raise SystemExit(f"{n} needs {dll}, which is not packaged")

    stamp = commit_time()
    target = out / f"bdo-ui-{version}-windows-x64.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n in sorted(files):
            info = zipfile.ZipInfo(f"{TOP}/{n}", date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0            # plain DOS attributes, no Unix modes
            z.writestr(info, files[n])
    size = sum(len(d) for d in files.values())
    print(f"{target}  {target.stat().st_size / 1e6:.1f} MB "
          f"({len(files)} files, {size / 1e6:.1f} MB unpacked)")
    print(f"sha256 {hashlib.sha256(target.read_bytes()).hexdigest()}")
    return target


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist"), help="output folder (default: dist)")
    args = ap.parse_args()
    build(Path(args.out).resolve())


if __name__ == "__main__":
    main()
