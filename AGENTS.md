# bdo-ui for scripts and AI assistants

How to drive `bdo-ui` from a terminal without the editor window. Everything
here works through the command line; nothing needs the GUI.

`bdo-ui` below stands for `python3 main.py` (Linux) or `bdo-ui.bat` (Windows)
in the program folder. `bdo-ui --help` lists the commands and
`bdo-ui <command> --help` describes the options of one.

Setting the tool up for someone, the editor and troubleshooting are in
[docs/guide.md](docs/guide.md); the source layout is in
[CONTRIBUTING.md](CONTRIBUTING.md).

## What the pieces are

- **Game slot** — one of the three UI presets (Edit UI) the game keeps per
  family. Lives in the game's settings file.
- **Library preset** — a layout kept by `bdo-ui` on disk, any number of them.
  One entry is two files with the same name in the library folder:
  `<name>.xml` (the layout) and `skills/<name>.json` (optional skill profile).
- **Skill profile** — what sits in the cooldown slots and quick slots of one
  character, plus the hotkey captions under the cooldown slots.
- **Family** — a game account; the most recently played one is the default,
  `--family <id>` (before the command) picks another.

The layout says where the panels are. The skill profile says which skill is in
which slot. They are written separately.

## Rules

1. **The game must be closed** for `load` and for `skills` (writing). The game
   rewrites its settings while it runs, so both commands refuse to write then.
   `list --json` reports it as `game_running`.
2. `list`, `show`, `save`, `set`, `chars`, `skills --dry-run` and
   `skills --capture` are safe while the game runs: they read the game files or
   change the library only.
3. Every write to a game file makes a copy first, in `.backups` inside the
   library folder. `set` changes only the library and makes no backup — copy
   the `<name>.xml` yourself, or `bdo-ui save <other name> <slot>` first, if
   the layout matters.
4. Do not edit the game's `gamevariable.xml` by hand. Go through the library.
5. A preset loaded into a game slot is not active yet: the player loads it in
   game with Edit UI -> preset button.

Exit code 0 means success; anything else comes with a message on standard
error that starts with `bdo-ui:`.

## Reading

```
bdo-ui list --json            library, game slots, families, game_running
bdo-ui show "<name>" --json   panels of a library preset
bdo-ui show --slot 2 --json   panels of a game slot
bdo-ui chars --json           characters: id, class, spec, last played
```

`show --json`:

```json
{
 "source": "library", "name": "my layout", "saved": "2026-01-31T12:00:00",
 "screen": [2766, 2101],
 "panels": [
  {"ref": "C0", "index": 128, "name": "Cooldown slot 0",
   "x": 1024, "y": 1094, "w": 50, "h": 50, "shown": true,
   "skill": 4592, "skill_name": "Prime: Midnight Stinger"},
  {"ref": "2", "index": 2, "name": "EXP gauge",
   "x": null, "y": null, "w": null, "h": null, "shown": true}
 ],
 "profile": {"family": "...", "char": "...", "cooldown": {}, "quick": {}, "memo": {}}
}
```

- `screen` is the size of the game screen in **UI units**: window pixels
  divided by the game's UI scale. All positions and sizes use these units.
- `x`, `y` is the top left corner of a panel; the origin is the top left
  corner of the screen.
- `ref` is the name `set` takes: `C0`..`C19` cooldown slots, `Q1`..`Q20` quick
  slots (numbered as the game shows them), `chat1`.. chat windows, otherwise
  the panel index. The full `name` is accepted too.
- Panels with `x: null` have no position in the preset; they can only be shown
  or hidden.
- `skill` / `skill_name` appear when the entry has a skill profile.
- `profile` is the skill profile, or `null`.

## Changing a layout

```
bdo-ui set "<name>" C0 --x 900 --y 1500        absolute position
bdo-ui set "<name>" Q1 Q2 Q3 --dy -40          relative move
bdo-ui set "<name>" 55 chat2 --hide            visibility (--show / --hide)
bdo-ui set "<name>" --from changes.json        many changes at once
```

Add `--dry-run` to see the result without saving and `--json` for a report:

```json
{"name": "my layout", "saved": true, "dry_run": false,
 "changes": [{"ref": "C0", "name": "Cooldown slot 0",
              "before": {"x": 1024, "y": 1094, "shown": true},
              "after": {"x": 900, "y": 1500, "shown": true}}],
 "warnings": []}
```

`--from` takes a file, or `-` for standard input, with a JSON list:

```json
[{"panel": "C0", "x": 900, "y": 1500},
 {"panel": "Q1", "dx": 10, "shown": false}]
```

Keys: `panel` (or `ref`), `x`, `y`, `dx`, `dy`, `shown`. The output of
`show --json` is accepted as it is, so the simplest way to rearrange a layout
is: `show --json` to a file, change `x` / `y` / `shown` there, feed the file to
`set --from`. Panels that did not change are skipped.

A panel that ends up partly outside the screen is still saved; it is listed in
`warnings`.

Sizes cannot be changed. Useful numbers when lining slots up: a cooldown slot
is 50x50, a quick slot 50x65. The hotkey caption is drawn under the cooldown
icon, so leave room below it — a grid step of about 62x58 keeps captions
readable.

## Typical tasks

Take the current game layout, change it, put it back:

```
bdo-ui save "work" 1               # game slot 1 -> library (game may run)
bdo-ui show "work" --json > w.json
#   ... edit w.json ...
bdo-ui set "work" --from w.json --dry-run
bdo-ui set "work" --from w.json
#   close the game, then:
bdo-ui load "work" 1
```

Make a variant of an existing preset: copy `<name>.xml` (and
`skills/<name>.json` if there is one) under a new name in the library folder,
then `set` the copy. The folder is `library_dir` in `list --json`.

## Skill profiles

`skills/<name>.json` in the library folder:

```json
{
 "family": "1234567",
 "char": "40000000012345678",
 "cooldown": {"0": 4592, "1": 4596},
 "quick": {"1": 4595, "2": null},
 "memo": {"380": "W+F", "348": "SPACE"},
 "names": {"4592": "Prime: Midnight Stinger"}
}
```

- `family`, `char` — where the profile is written; ids come from `chars --json`.
- `cooldown` — cooldown slot (0..19) -> skill id.
- `quick` — quick slot (1..20, as shown in game) -> skill id; `null` empties
  the slot. Items in quick slots are left alone.
- `memo` — skill id -> caption shown under that skill's cooldown slot.
- `names` — optional, skill id -> name, only for readable reports.

Skill ids are the ids of bdocodex.com, one per rank of a skill
(`bdocodex.com/us/skill/<id>/`). Captions are keyed by the id of the base
skill: when a caption is written under a Prime / Succession id, the game moves
it to the base skill the next time it saves. After the game has run, read the
real state back instead of guessing:

```
bdo-ui skills "<name>" --capture            character -> profile
bdo-ui skills "<name>" --dry-run            what writing would change
bdo-ui skills "<name>"                      profile -> character (game closed)
bdo-ui skills "<name>" --only memo          only captions; also cooldown, quick
bdo-ui load "<name>" 2 --with-skills        layout and slot contents together
```

Whether the game accepts the id of a skill the character has not learned is
not known; check in game after writing.

## Where things are

- Library: `~/.bdo/ui-presets` (Windows: `%USERPROFILE%\.bdo\ui-presets`);
  the `BDO_UI_LIB` environment variable moves it. Point it at a scratch folder
  to try commands without touching the real library.
- Game settings: found automatically; `bdo-ui docs` shows the folder,
  `bdo-ui docs <path>` or the `BDO_DOCS` variable sets it.
- Layouts are in `UserCache/<family>/gamevariable.xml`, slot contents in
  `UserCache/<family>/400/<char>/gameVariable.xml`.
