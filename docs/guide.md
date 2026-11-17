# bdo-ui guide

Details that do not fit the [README](../README.md): how the game folder is
found, what the editor window does, how library entries, characters and skill
profiles hang together, and what to check when something does not work.
The command line and the file formats are in [AGENTS.md](../AGENTS.md).

`bdo-ui` below stands for `python3 main.py` (Linux) or `bdo-ui.bat` (Windows).
Menu and button names are those of the English interface.

## Game folder

Usually nothing has to be set up. The folder with the game's settings is found
automatically:

- **Windows:** `Documents\Black Desert`, also when Documents was moved (for
  example into OneDrive). The same for the Steam version and the Pearl Abyss
  launcher.
- **Linux (Steam + Proton):** looked up through the Steam libraries of
  `libraryfolders.vdf`, in
  `steamapps/compatdata/582660/pfx/drive_c/users/steamuser/Documents/Black Desert`.

If that fails, the folder is given once and remembered in `~/.bdo/bdo-ui.json`
(Windows: `%USERPROFILE%\.bdo\bdo-ui.json`):

- in the editor a folder dialog appears on start; later: File → Game folder…
- in a terminal: `bdo-ui docs <path>`; without a path it shows the folder in
  use and whether it was found.

The folder wanted is the `Black Desert` one that holds `GameOption.txt` and
`UserCache/`. Its parent and `UserCache` itself are accepted too.

Order: the `BDO_DOCS` environment variable (overrides everything), then the
remembered folder, then detection. Detection runs on every start; its result
is not cached.

`BDO_UI_LIB` moves the library. The default is `~/.bdo/ui-presets`
(Windows: `%USERPROFILE%\.bdo\ui-presets`).

## First steps

1. `bdo-ui list` should print the library (empty) and the three game slots
   with their panel count and screen size.
2. Save the current slots into the library before changing anything. This only
   reads, so the game may be running:

   ```
   bdo-ui save "my layout 1" 1
   bdo-ui save "my layout 2" 2
   bdo-ui save "my layout 3" 3
   ```
3. On Linux, a launcher is a script in `~/bin` or `~/.local/bin` with
   `exec python3 /path/to/bdo-ui/main.py "$@"`. On Windows make a shortcut to
   `bdo-ui.bat`.

Switching to another layout:

1. Close the game.
2. `bdo-ui load <name> <slot>`, or the yellow "Write to game slot" button in
   the editor.
3. Start the game and load that preset in Edit UI.

What is on the screen right now and the three preset slots are different
things. The tool changes the slots only; the screen changes when the preset is
loaded in game.

## Safety

- **Writing needs the game closed.** The game keeps the presets and the
  character settings in memory and rewrites the files, so a write during a
  session is lost. The tool refuses to write while `blackdesert64.exe` runs.
- **Do not edit the game files by hand.** The format depends on line endings
  and line order; the tool keeps everything but the target slot byte for byte.
- **Backups.** Before every write the file is copied to `.backups` inside the
  library; the last 30 per family are kept. They are restored by hand: there
  is no restore command.

## The editor window

Pick an entry on the left, arrange the panels, Save, "Write to game slot".

- **Left:** the library. Entries show the portrait and class of the bound
  character and the screen size; Ctrl+F searches. Right click: Open, Rename,
  Duplicate, Write to game slot, Delete. Below are the three game slots of the
  chosen family and "Game default". Clicking a slot opens a copy of it, which
  becomes a library entry once saved.
- **Centre:** the game screen. Dragging moves a panel; edges snap to other
  panels and to the screen borders. Arrow keys move by 1 unit, with Shift by
  10. Wheel zooms, middle button or Space + drag pans, F fits the screen.
- **Right:** "Layout" (character, screen size), "Selection" (X/Y of the
  selected panels, visibility in game, align tools) and the list of all panels
  with a filter; the check box is the visibility in game.
- **Toolbar:** Save, undo and redo, align, show or hide (H), snapping and
  grid, what to draw (hidden panels, skill icons, a background screenshot).
  Help → Keyboard and mouse (F1) lists the keys.
- **While the game runs** the write button is disabled and the slots are
  marked read-only. This is checked every three seconds.
- Window size, sidebar widths and the view switches are remembered in
  `~/.bdo/bdo-ui.json` when the window closes.

The language follows the system on the first start and is changed in
View → Language, without a restart. The command line always answers in
English. Skill and class names come from bdocodex.com and stay English.

## What a layout is

- **A layout belongs to a screen size.** A preset stores the screen size in UI
  units: window pixels divided by `uiScale` of `GameOption.txt`. A preset made
  for another resolution is converted with Layout → Screen size…: the panels
  keep their relative places. Check the screen edges and overlaps afterwards.
- **A layout belongs to the family**, not to a character, and holds only the
  position and visibility of panels. Panel sizes cannot be changed.
- **What sits in the slots is separate.** The skills in the quick slots and
  cooldown slots are in the character file,
  `UserCache/<family>/400/<character id>/gameVariable.xml`.
- **Panel names** come from the client's scripts of 2022. Panels the game
  added later (index 160 and up) are shown as "Panel N".

## Library entries and characters

An entry is two files with the same name: `<library>/<name>.xml`, the layout,
and `<library>/skills/<name>.json`, the skill profile: which character the
entry is for and what is in that character's quick and cooldown slots, with
the hotkey captions.

- `bdo-ui save <name> <slot>` stores the layout and the slot contents of the
  character played last. `--char <id>` picks another one (`bdo-ui chars`
  lists them), `--no-skills` stores the layout only.
- `bdo-ui load <name> <slot>` writes the layout only and says so when the
  character's slots differ from the stored ones; `--with-skills` restores
  them. The editor asks after writing a slot. This is not the default on
  purpose: the skills may have been rearranged in game since the save.
- `bdo-ui skills <name> --capture` reads the slot contents back into the
  profile.
- In the editor an entry is bound to a character with Layout → Character…
  The cards are in the order of the game's character selection, with
  portrait, name, class, last login and the entries already bound.
  - The portrait is `FaceTexture/<character id>.bmp` of the game folder.
  - Class and spec are worked out from the skills in the character's slots.
    That needs the skill list of all classes from bdocodex.com: one request of
    about 5 MB, cached in `<library>/icons/skills.json`. A character with
    empty slots has no known class.
  - The game does not keep character names locally. A name is typed once
    ("Name…", or `bdo-ui chars --char <id> --name <name>`) and kept in
    `<library>/characters.json`.
  - Deleted characters are hidden; `bdo-ui chars --all` shows them.

With a profile the editor draws the skill icons in the slots. Icons are
downloaded from bdocodex.com on request (the "Download" button in the Layout
block, or `bdo-ui icons <name>`) and cached in `<library>/icons/`. The network
is used only for this, for the skill list and for updates.

### Notes on skill profiles

The format is in [AGENTS.md](../AGENTS.md#skill-profiles). Beyond it:

- Quick slot 10 is the `0` key. The game file numbers the slots from 0; the
  tool converts.
- Slots a profile does not mention, and items in quick slots, are left alone.
- Captions are stored by the game under the id of the **base skill of the
  first rank**; for a `Prime:` skill that is the skill it replaces. A caption
  written under another id shows up, and the game moves it to the base id on
  its next save. Run `--capture` after a session to pick those ids up, so
  that writing the profile again changes nothing.
- `--only cooldown,quick,memo` limits a write to some parts, for example to
  add captions without touching slots rearranged in game.
- A profile from another account does not work as it is: `family` and `char`
  differ. The family is the numeric folder in `UserCache/`, the characters
  are the folders in `400/` inside it; `bdo-ui chars` lists them, last played
  first.
- A skill id is the number in the address of the skill's page on
  bdocodex.com. It must be the id of the rank the character has learned.
- Look at `bdo-ui skills <name> --dry-run` before writing.

## Updates

The installed version is the `VERSION` file of the program folder
(`bdo-ui --version`).

- On start the editor checks for a newer version and shows an "Update to X"
  button when there is one. Nothing is installed without asking. Help → Check
  for updates on start turns the check off.
- By hand: Help → Check for updates, or `bdo-ui update` (`--check` only
  looks).
- The update is downloaded, checked and unpacked over the program folder.
  Replaced files stay in `.update-backup/<old version>/`. The library, the
  settings and the game files are not touched.
- A `git clone` is updated with `git pull --ff-only`, and only on `main`.
  A copy installed with pip is updated with pip.
- Only `raw.githubusercontent.com` and `github.com` are contacted, with no
  data about the user.

## Limits

- On Linux the "Take from the running game window" button of the screen size
  dialog works only under Hyprland. Elsewhere type the size or pick it from
  the list.
- The title bar is drawn by the system and stays light on a light Windows
  theme.

## Troubleshooting

| Symptom | Check |
|---|---|
| `game settings not found` | `bdo-ui docs` shows where it looks; `bdo-ui docs <path>` sets the folder |
| `no UISettingPreset block` | no preset was ever saved in game for this family: save any slot in Edit UI and try again |
| `Black Desert is running` with the game closed | a `blackdesert64.exe` process is left over; end it |
| `... is locked by another program` (Windows) | the game or an antivirus holds the file |
| the slot was written but the game shows the old layout | the preset was not loaded in Edit UI, or the game was running during the write |
| the editor window does not open | PySide6 is missing or Python is older than 3.10 (source install) |
