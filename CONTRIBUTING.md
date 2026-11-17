# Contributing to bdo-ui

Bug reports, translations and pull requests are welcome.

## Reporting a problem

Open an issue with the version (`bdo-ui --version`), the system (Windows, or
Linux with Steam + Proton), what was done and what happened. For a layout
that is read or written wrongly, the output of `bdo-ui list` helps.

## Sending a change

1. Fork the repository and branch off `main`.
2. Make the change and try it on copies of the data (see below).
3. Open a pull request against `main`. Say what it changes and what was run
   to check it; there is no test suite yet.

For anything larger than a fix, open an issue first so the work is not wasted.

Contributions are accepted under the project's licence, GPL-3.0-or-later.
New source files start with the same two header lines as the existing ones.

## Rules

- **Linux and Windows both.** Whatever differs between them goes into
  `bdo_ui/core` behind the `WINDOWS` flag. No icon themes, system styles or
  shell commands that exist on one system only.
- **No new dependencies.** PySide6 for the editor, the standard library for
  the rest. Python 3.10 and PySide6 6.5 are the oldest versions supported.
- **Game files are written only through `bdo_ui.core`**, which makes a backup
  first and refuses while the game runs. Keep both.
- **Texts of the editor come from the catalogs.** A new text is a key in
  `bdo_ui/lang/en.json`; add the Russian and Ukrainian ones if you can, or
  say in the pull request that they are missing. The command line prints
  English only.
- **Comments and commit messages in English.**
- **Leave `VERSION` alone.** Raising it offers the update to every installed
  copy; that is done at release time.
- Run `python3 -m bdo_ui.i18n` before sending: it checks the catalogs against
  each other and against the code.

## Running from source

Needs Python 3.10 or newer.

```
pip install -r requirements.txt
python3 main.py            # the editor
python3 main.py --help     # the command line
```

## Trying things safely

Point the program at copies, never at the real files:

- `BDO_DOCS` — a copy of the game's `Black Desert` folder;
- `BDO_UI_LIB` — a copy of the library, or an empty folder;
- `QT_QPA_PLATFORM=offscreen` — the editor without a display;
- in code, set `core.config.CONFIG_PATH` to a scratch file before creating
  the window, so the real config is not rewritten.

## Source layout

```
main.py                 starts the program from its folder
bdo_ui/cli.py           command line
bdo_ui/core/            game files, library, skill profiles; no Qt
    config              where the game folder, the library and the config are
    layout              panels of a preset and their geometry
    game                families, preset slots of a family file, backups
    library             presets kept on disk
    skills              skill profiles of a character
    skilldb             skill names, icons and classes from bdocodex.com
    characters          characters of a family
bdo_ui/gui/             the editor (PySide6)
    app, window         start-up and the main window
    canvas              the game screen with the panels
    dialogs, delegates, widgets, watch, language
    theme               colours, stylesheet, icons drawn in code
bdo_ui/panels.py        panel indices, known sizes, slot labels
bdo_ui/i18n.py          interface languages and the catalog checker
bdo_ui/lang/*.json      one catalog per language; en.json is the source
bdo_ui/updater.py       self-update from GitHub
tools/build_windows.py  build of the portable Windows package
```

`core.lib_load`, `core.write_slot` and the rest of the public names are
available from `bdo_ui.core` itself. The folders are the exception: they can
change at run time and are read as `core.config.BDO_DIR`,
`core.config.LIB_DIR`, `core.config.CONFIG_PATH`.

Everything that differs between Linux and Windows is in `bdo_ui/core` behind
the `WINDOWS` flag. The look of the editor does not depend on the system:
Qt's Fusion style, own colours, icons drawn in code.

`pip install .` works and adds a `bdo-ui` command; `python3 -m bdo_ui` runs
the program as well.

## Languages

A new language is one file, no code.

1. Copy `bdo_ui/lang/en.json` to `bdo_ui/lang/<code>.json`. The code is that
   of the locale: `de`, `pl`, `pt_BR`. It is how the language is matched to
   the system.
2. `"@language"` is the name of the language in that language, shown in the
   menu. `"@plural"` is the plural rule: a gettext `Plural-Forms` expression
   of `n`, without `nplurals=` and `plural=`. Examples: `n != 1` (English,
   German), `0` (Japanese),
   `n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2`
   (Russian, Ukrainian).
3. Translate the values. Leave the keys and the placeholders in braces
   (`{name}`, `{n}`) alone. A list is the plural forms, as many as the rule
   gives. `&` in a menu name marks the Alt letter.
4. Check: `python3 -m bdo_ui.i18n <code>` from the program folder. It lists
   missing and extra keys and mismatched placeholders or plural forms.
   Without arguments it checks every catalog, and for `en.json` also that the
   keys match the code.
5. Save the file as UTF-8, start the editor and pick the language.

Whatever a catalog lacks is shown in English. A catalog that is not valid
JSON does not appear in the menu.

A new text in the program is a key in `en.json` and a call of `tr("key")`, or
`trn("key", n)` for a counted text. Tips in the status bar are the keys
`tip.N`, panel names `panel.<index>`; for those the catalog entry is enough.

## Where help is wanted

- **Real Windows.** The Windows package has only been run under Wine. Worth
  checking: the Documents folder lookup (`SHGetKnownFolderPath`), the game
  process check (`tasklist`), the game window size (`EnumWindows`), entry
  names in non-Latin scripts, button widths with the system font.
- **Other Linux desktops.** The "Take from the running game window" button
  works only under Hyprland.
- **Translations** into more languages.
- **Panel names.** Panels the game added after 2022 (index 160 and up) are
  shown as "Panel N"; names for them go into `bdo_ui/lang/en.json` as
  `panel.<index>`.
