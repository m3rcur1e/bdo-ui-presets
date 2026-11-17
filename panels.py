"""Panel index -> name / known size tables for BDO UI presets.

Names come from CppEnums.PAGameUIType (decompiled client lua, 2022 dump).
Indices added to the game later (160+) are unknown and get a generic label.
"""

NAMES = {
    2: "EXP gauge",
    3: "UI menu",
    9: "Minimap",
    12: "Quick slot bar",
    13: "Main status bar",
    15: "Party",
    21: "Quest tracker",
    22: "House navi",
    32: "Chat",
    55: "Mount window",
    82: "New equipment",
    83: "Guild quest",
    84: "PvP mode",
    85: "Adrenaline",
    86: "Game tips",
    87: "Time bar",
    88: "Skill command guide",
    89: "Class resource",
    111: "Skill cooldown",
    112: "Key viewer",
    113: "Main quest",
    114: "Left icons",
    115: "Right icons",
    116: "Challenge alert",
    117: "Coupon alert",
    118: "Premium alert",
    119: "Buff list",
    120: "Horse HP",
    121: "Horse MP",
    122: "Stamina",
    123: "Endurance",
    124: "Horse endurance",
    125: "Carriage endurance",
    126: "Ship endurance",
    127: "Large party",
    138: "Main status (remaster)",
    139: "Mount icon",
    140: "World minimap",
    141: "Widget functions",
    142: "Area of Hadum",
    143: "Kill log",
    144: "Console quick menu",
    145: "Console chat viewer",
    146: "Console mount icon",
    147: "Console item counter",
    158: "Skill log",
    159: "Item log",
}

# Short labels drawn inside small slot rectangles.
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
    NAMES[quick_slot_index(_slot)] = f"Quick slot {_slot}"
    SHORT[quick_slot_index(_slot)] = f"Q{_slot}"

# SkillCoolTimeQuickSlot_0..9 = 128..137, _10..19 = 148..157
for _i in range(10):
    NAMES[128 + _i] = f"Cooldown slot {_i}"
    SHORT[128 + _i] = f"C{_i}"
    NAMES[148 + _i] = f"Cooldown slot {10 + _i}"
    SHORT[148 + _i] = f"C{10 + _i}"

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
    if index == 32:
        return "chat"
    return "other"
