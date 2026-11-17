# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Panels of a UI preset: parsing the lines of a slot and the geometry.

RelativePos is the panel centre divided by the screen size (in UI units), so
both the screen size and every panel size can be recovered from a preset.
"""

import re
import statistics
import struct

from .. import panels
from ..i18n import tr
from .errors import BdoUiError

DEFAULT_SCREEN = (1920, 1080)

_OPEN_RE = re.compile(r'^\t<(\w+)((?: \w+="[^"]*")*) ?(/?)>$')
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


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
