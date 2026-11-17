# bdo-ui

Library and editor for Black Desert Online UI presets.

The game keeps only three UI preset slots (Edit UI) per family, and the layout
belongs to the family, not to a character. `bdo-ui` keeps any number of layouts
on disk and puts the one you need into one of the three game slots. In game you
load it with the usual preset button.

- Drag-and-drop editor for the panels, with snapping, align tools and undo.
- A library entry holds the layout and, optionally, what sits in the slots of
  a character: cooldown slots, quick slots and hotkey captions.
- Skill icons in the editor, downloaded on request from bdocodex.com.
- Command line for everything the editor does.
- Interface in English, Russian and Ukrainian.
- Works on Linux (Steam + Proton) and Windows.

## Install

Needs Python 3.10 or newer.

```
pip install -r requirements.txt
```

Run the editor:

- Linux: `python3 main.py`
- Windows: `bdo-ui.bat`

The game's `Black Desert` documents folder is found automatically. If it is
not, the editor asks for it on start; in a terminal use `bdo-ui docs <path>`.

`CLAUDE-SETUP.md` is a detailed setup guide (in Russian) written for an AI
assistant that is asked to install the tool.

## Use

```
bdo-ui                       open the editor
bdo-ui edit <name>           open the editor on a library preset
bdo-ui list                  library presets and the game slots
bdo-ui save <name> <slot>    copy game slot 1..3 into the library
bdo-ui load <name> <slot>    put a library preset into game slot 1..3
bdo-ui skills <profile>      put a skill profile into its character file
bdo-ui chars                 characters of the family, last played first
bdo-ui icons <profile>       download skill icons of a profile
bdo-ui docs [path]           show or set the game's documents folder
bdo-ui update                install the newest version from GitHub
bdo-ui --version             the installed version
```

`python3 main.py --help` lists the options of each command.

## How it stays safe

- The game writes its settings during a session, so a game slot can only be
  written while the game is closed. Reading works at any time.
- Before every write the game file is copied to `.backups` inside the library
  (`~/.bdo/ui-presets`, on Windows `%USERPROFILE%\.bdo\ui-presets`).
- Only the lines of the target slot are replaced; the rest of the file stays
  byte for byte the same.

The tool edits local settings files only. It does not touch the game client
or its memory.

## Updates

The editor checks this repository for a newer version on start and offers to
install it; nothing is installed without asking. The check can be turned off
in the Help menu.

## Languages

One JSON file per language in `lang/`; `en.json` is the source. To add a
language, copy it, translate the values and run `python3 i18n.py` to check
the result.

## License

Copyright © 2026 m3rcur1e

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. It comes with no warranty. See [LICENSE](LICENSE).

Not affiliated with Pearl Abyss. Black Desert is a trademark of its owner.
