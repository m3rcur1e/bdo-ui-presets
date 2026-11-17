# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""BDO UI preset library: parse, edit and write the game's UI preset slots.

The parts, each a module of this package:

    config      where the game folder, the library and the config file are
    layout      panels of a preset and their geometry
    game        families, the preset slots of a family file, backups
    library     presets kept on disk
    skills      skill profiles of a character (cooldown and quick slots)
    skilldb     skill names, icons and classes from bdocodex.com
    characters  characters of a family

Everything public is also available from the package itself: core.lib_load,
core.write_slot. The folders are the exception, they can change at run time
and are read as core.config.BDO_DIR, core.config.LIB_DIR and so on.
"""

from . import config
from .errors import BdoUiError
from .config import (PROTON_DOCS, STEAM_APP_ID, WINDOWS, docs_valid, load_config, normalize_docs,
                     save_config, set_docs)
from .layout import (DEFAULT_SCREEN, El, estimate_screen, fmt_rel, panel_size, parse_elements,
                     set_position)
from .game import (GAME_EXE, GAME_WINDOW_CLASS, KEEP_BACKUPS, REVERT_TAG, SLOT_TAGS, backup,
                   families, family_file, game_running, game_window_screen, read_slots,
                   slot_is_empty, ui_scale, write_slot)
from .library import (LIB_TAG, Preset, check_name, lib_delete, lib_list, lib_load, lib_meta,
                      lib_path, lib_rename, lib_save, preset_from_slot, profile_path)
from .skilldb import (ICON_SOURCE, SKILL_DB_SOURCE, char_class, fetch_icon, fetch_skill_db,
                      icon_path, skill_db, skill_name, skill_names)
from .skills import (SKILL_SECTIONS, apply_skills, capture_profile, char_file, characters,
                     fetch_profile_icons, plan_skills, profile_for_preset, save_profile,
                     skills_profile, slot_skills)
from .characters import (char_cards, char_registry, char_title, game_char_order, portrait_path,
                         set_char_name)
