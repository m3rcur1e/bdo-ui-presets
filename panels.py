# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Panel index -> name / known size tables for BDO UI presets.

Names come from CppEnums.PAGameUIType (decompiled client lua, 2022 dump).
Indices added to the game later (160+) are unknown and get a generic label.
The names themselves are in the language catalogs (lang/*.json) under the
keys "panel.<index>"; a new known panel is one more key in lang/en.json.
"""

import i18n

CHAT = 32
# Panel index -> slot number as the game shows it.
QUICK = {}
COOLDOWN = {}
# Short labels drawn inside small slot rectangles (the same in every language).
SHORT = {}

# Enum: NewQuickSlot_1..9 = 91..99, _0 = 100, _11..19 = 101..109, _10 = 110.
# The enum suffix is the 0-based Key in the character file; the game shows it
# as slot Key+1 (hotkeys 1..9, 0, then the second row), so name panels that way.
def quick_slot_index(slot):
    """Panel index of quick slot `slot` as numbered in game (1..20)."""
    key = slot - 1
    if key == 0:
        return 100
    if key == 10:
        return 110
    return 90 + key


for _slot in range(1, 21):
    QUICK[quick_slot_index(_slot)] = _slot
    SHORT[quick_slot_index(_slot)] = f"Q{_slot}"

# SkillCoolTimeQuickSlot_0..9 = 128..137, _10..19 = 148..157
for _i in range(10):
    COOLDOWN[128 + _i] = _i
    SHORT[128 + _i] = f"C{_i}"
    COOLDOWN[148 + _i] = 10 + _i
    SHORT[148 + _i] = f"C{10 + _i}"


def name(index, window=0):
    """Name of a panel in the interface language; `window` tells chat windows apart."""
    if index == CHAT:
        return i18n.tr("panel.chat", n=window + 1)
    if index in QUICK:
        return i18n.tr("panel.quick", n=QUICK[index])
    if index in COOLDOWN:
        return i18n.tr("panel.cooldown", n=COOLDOWN[index])
    key = f"panel.{index}"
    return i18n.tr(key) if i18n.has(key) else i18n.tr("panel.unknown", n=index)


# Sizes (UI units) that were identical in every preset inspected. Used only to
# estimate the screen size a preset was saved at; real sizes are then derived
# from RelativePos for every panel.
FIXED_SIZES = {
    12: (560, 70), 13: (385, 40), 15: (320, 25), 22: (54, 54), 55: (60, 60),
    82: (165, 56), 84: (50, 50), 85: (47, 47), 88: (300, 250), 89: (58, 58),
    111: (42, 42), 112: (660, 250), 114: (35, 35), 119: (410, 162),
    122: (244, 17), 127: (300, 25), 139: (51, 51), 141: (500, 60),
    143: (328, 100), 158: (200, 80), 159: (350, 300), 161: (416, 84),
}
for _i in list(range(91, 111)):
    FIXED_SIZES[_i] = (50, 65)
for _i in list(range(128, 138)) + list(range(148, 158)):
    FIXED_SIZES[_i] = (50, 50)


def group(index):
    """Colour group of a panel."""
    if 91 <= index <= 110:
        return "quick"
    if 128 <= index <= 137 or 148 <= index <= 157:
        return "cooldown"
    if index == CHAT:
        return "chat"
    return "other"
