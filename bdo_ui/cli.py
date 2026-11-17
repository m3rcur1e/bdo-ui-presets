#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""bdo-ui: library and editor for Black Desert UI presets.

    bdo-ui                       open the editor
    bdo-ui edit <name>           open the editor on a library preset
    bdo-ui list                  library presets and the game slots
    bdo-ui show <name>           panels of a library preset: position, size,
                                 visibility, skill in the slot (--slot <n> for
                                 a game slot)
    bdo-ui set <name> <panel>..  move, show or hide panels of a library preset
                                 (--x/--y, --dx/--dy, --show/--hide), or apply
                                 a list of changes with --from <file>
    bdo-ui save <name> <slot>    copy game slot 1..3 into the library, together
                                 with what sits in the slots of the character
                                 played last (--char <id> for another one)
    bdo-ui load <name> <slot>    put a library preset into game slot 1..3;
                                 --with-skills also restores the slot contents
    bdo-ui skills <profile>      put a skill profile (cooldown slots, quick slots,
                                 hotkey captions) into its character file;
                                 --dry-run to preview, --only memo to limit,
                                 --capture to re-read it from the character
    bdo-ui chars                 characters of the family, last played first
    bdo-ui icons <profile>       download skill icons of a profile (bdocodex.com)
                                 so the editor can draw them in the slots
    bdo-ui docs [path]           show, or set and remember, the game's
                                 'Black Desert' documents folder
    bdo-ui update                install the newest version from GitHub;
                                 --check only says whether there is one
    bdo-ui --version             the installed version

list, show, set and chars take --json for machine-readable output.
"bdo-ui <command> --help" describes the options of a command; AGENTS.md is a
guide for scripts and AI assistants.
"""

import argparse
import json
import sys

from . import core, panels


def pick_family(arg):
    fams = core.families()
    if arg:
        if arg not in fams:
            raise core.BdoUiError(f"unknown family {arg}; have: {', '.join(fams)}")
        return arg
    if not fams:
        raise core.BdoUiError(f"no families found under {core.config.BDO_DIR}")
    return fams[0]


def emit(data):
    print(json.dumps(data, indent=1, ensure_ascii=False))


def cmd_list(args):
    family = pick_family(args.family)
    if args.json:
        library = []
        for name in core.lib_list():
            meta = core.lib_meta(name)
            profile = core.profile_for_preset(name)
            library.append({"name": name, "screen": meta.get("screen"),
                            "saved": meta.get("saved"),
                            "char": profile.get("char") if profile else None})
        slots = core.read_slots(family)
        game = []
        for i, tag in enumerate(core.SLOT_TAGS):
            els = slots.get(tag, [])
            empty = core.slot_is_empty(els)
            game.append({"slot": i + 1, "empty": empty,
                         "panels": sum(1 for e in els if e.index is not None),
                         "screen": None if empty else list(core.estimate_screen(els))})
        emit({"library_dir": str(core.config.LIB_DIR), "library": library, "family": family,
              "families": core.families(), "game_slots": game,
              "game_running": bool(core.game_running())})
        return
    print("Library:", core.config.LIB_DIR)
    names = core.lib_list()
    for name in names:
        p = core.lib_load(name)
        print(f"  {name:<24} {p.screen[0]}x{p.screen[1]}  saved {p.meta.get('saved', '?')}")
    if not names:
        print("  (empty)")
    print(f"Game slots, family {family}:")
    slots = core.read_slots(family)
    for i, tag in enumerate(core.SLOT_TAGS):
        els = slots.get(tag, [])
        if core.slot_is_empty(els):
            print(f"  slot {i + 1}: empty")
        else:
            scr = core.estimate_screen(els)
            n = sum(1 for e in els if e.index is not None)
            print(f"  slot {i + 1}: {n} panels, screen {scr[0]}x{scr[1]}")
    print("Game:", "running (slots are read-only)" if core.game_running() else "closed")


# ---------------------------------------------------------------- show / set

def panel_ref(el):
    """The name `set` accepts for a panel: C0, Q1, chat1 or the panel index."""
    if el.index == panels.CHAT:
        return f"chat{int(el.get('WindowIndex', '0')) + 1}"
    return panels.SHORT.get(el.index) or str(el.index)


def find_panels(preset, ref):
    """Elements a panel reference stands for: a ref of `show`, or a panel name."""
    wanted = str(ref).strip().lower()
    found = [el for el in preset.els if el.index is not None
             and wanted in (panel_ref(el).lower(), el.label().lower())]
    if not found:
        hint = " (chat windows are chat1, chat2, ...)" if wanted == str(panels.CHAT) else ""
        raise core.BdoUiError(f"no panel {ref!r} in this preset{hint}; "
                              f"'bdo-ui show' lists the panels")
    return found


def describe_panel(el, screen, skills=None, profile=None):
    out = {"ref": panel_ref(el), "index": el.index, "name": el.label(),
           "x": None, "y": None, "w": None, "h": None, "shown": el.shown}
    if el.positioned:
        out["x"], out["y"] = int(float(el.get("PosX"))), int(float(el.get("PosY")))
        out["w"], out["h"] = core.panel_size(el, screen)
    skill = (skills or {}).get(el.index)
    if skill:
        out["skill"] = skill
        out["skill_name"] = str(core.skill_name(skill, profile))
    return out


def open_source(args):
    """(preset, profile, header) of what `show` was pointed at."""
    if args.slot:
        if args.name:
            raise core.BdoUiError("give a preset name or --slot, not both")
        family = pick_family(args.family)
        preset = core.preset_from_slot(family, core.SLOT_TAGS[args.slot - 1])
        return preset, None, {"source": "game slot", "slot": args.slot, "family": family}
    if not args.name:
        raise core.BdoUiError("which preset? give a library name or --slot <1-3>")
    preset = core.lib_load(args.name)
    return preset, core.profile_for_preset(args.name), {
        "source": "library", "name": args.name, "saved": preset.meta.get("saved")}


def cmd_show(args):
    preset, profile, head = open_source(args)
    skills = core.slot_skills(profile) if profile else {}
    rows = [describe_panel(el, preset.screen, skills, profile)
            for el in preset.els if el.index is not None]
    if args.json:
        head["screen"] = list(preset.screen)
        head["panels"] = rows
        head["profile"] = profile
        emit(head)
        return
    title = head.get("name") or f"game slot {head['slot']}"
    print(f"{title}: screen {preset.screen[0]}x{preset.screen[1]} UI units, "
          f"{len(rows)} panels")
    print(f"{'panel':<7} {'x':>5} {'y':>5} {'w':>5} {'h':>5}  shown  name")
    for r in rows:
        pos = "".join(f" {'-' if r[k] is None else r[k]:>5}" for k in "xywh")
        name = r["name"] + (f"  [{r['skill_name']}]" if "skill_name" in r else "")
        print(f"{r['ref']:<7}{pos}  {'yes' if r['shown'] else 'no':<5}  {name}")
    if profile:
        print(f"slot contents: character {profile.get('char')}")


def read_changes(args):
    """[(panel ref, {x, y, dx, dy, shown})] asked for on the command line and in --from."""
    changes = []
    if args.source:
        text = sys.stdin.read() if args.source == "-" else open(
            args.source, encoding="utf-8").read()
        try:
            data = json.loads(text)
        except ValueError as e:
            raise core.BdoUiError(f"--from: not JSON: {e}")
        if isinstance(data, dict):
            data = data.get("panels")
        if not isinstance(data, list):
            raise core.BdoUiError("--from: expected a list of panel changes, "
                                  "or the output of 'bdo-ui show --json'")
        for item in data:
            ref = item.get("panel", item.get("ref")) if isinstance(item, dict) else None
            if ref is None:
                raise core.BdoUiError(f"--from: entry without \"panel\": {item!r}")
            changes.append((ref, {k: item[k] for k in ("x", "y", "dx", "dy", "shown")
                                  if item.get(k) is not None}))
    flags = {k: getattr(args, k) for k in ("x", "y", "dx", "dy", "shown")
             if getattr(args, k) is not None}
    if args.panels and not flags:
        raise core.BdoUiError("nothing to change: add --x, --y, --dx, --dy, --show or --hide")
    if flags and not args.panels:
        raise core.BdoUiError("which panels? name them before the options")
    changes.extend((ref, flags) for ref in args.panels)
    if not changes:
        raise core.BdoUiError("nothing to change: name panels and options, or use --from")
    return changes


def cmd_set(args):
    preset = core.lib_load(args.name)
    screen = preset.screen
    report, warnings = [], []
    for ref, want in read_changes(args):
        for el in find_panels(preset, ref):
            before = describe_panel(el, screen)
            moves = any(k in want for k in ("x", "y", "dx", "dy"))
            if moves and not el.positioned:
                raise core.BdoUiError(f"panel {before['ref']} ({before['name']}) has no "
                                      f"position in the preset; it can only be shown or hidden")
            if moves:
                x = int(want.get("x", before["x"])) + int(want.get("dx", 0))
                y = int(want.get("y", before["y"])) + int(want.get("dy", 0))
                if (x, y) != (before["x"], before["y"]):
                    core.set_position(el, x, y, (before["w"], before["h"]), screen)
                if not (0 <= x and 0 <= y and x + before["w"] <= screen[0]
                        and y + before["h"] <= screen[1]):
                    warnings.append(f"{before['ref']} ({before['name']}) reaches outside "
                                    f"the {screen[0]}x{screen[1]} screen")
            if "shown" in want:
                el.set("IsShow", "true" if want["shown"] else "false")
            after = describe_panel(el, screen)
            if after != before:
                report.append({"ref": after["ref"], "name": after["name"],
                               "before": {k: before[k] for k in ("x", "y", "shown")},
                               "after": {k: after[k] for k in ("x", "y", "shown")}})
    saved = bool(report) and not args.dry_run
    if saved:
        core.lib_save(preset, args.name)
    if args.json:
        emit({"name": args.name, "saved": saved, "dry_run": args.dry_run,
              "changes": report, "warnings": warnings})
        return
    for c in report:
        b, a = c["before"], c["after"]
        parts = []
        if (b["x"], b["y"]) != (a["x"], a["y"]):
            parts.append(f"({b['x']}, {b['y']}) -> ({a['x']}, {a['y']})")
        if b["shown"] != a["shown"]:
            parts.append("shown" if a["shown"] else "hidden")
        print(f"  {c['ref']:<7} {c['name']}: {', '.join(parts)}")
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if not report:
        print("nothing to change")
    elif args.dry_run:
        print(f"{len(report)} change(s), not saved (--dry-run)")
    else:
        print(f"{len(report)} change(s) saved to {args.name!r}; "
              f"'bdo-ui load \"{args.name}\" <slot>' puts it into the game")


def cmd_save(args):
    family = pick_family(args.family)
    preset = core.preset_from_slot(family, core.SLOT_TAGS[args.slot - 1])
    if core.lib_path(args.name).exists() and not args.force:
        raise core.BdoUiError(f"preset {args.name!r} already exists (use --force)")
    path = core.lib_save(preset, args.name)
    print(f"saved slot {args.slot} of family {family} -> {path}")
    if args.no_skills:
        return
    chars = core.characters(family)
    char = args.char or (chars[0][1] if chars else None)
    if not char:
        print("no characters found; slot contents not stored")
        return
    profile = core.capture_profile(family, char)
    core.save_profile(args.name, profile)
    print(f"slot contents of character {char}: {len(profile['cooldown'])} cooldown, "
          f"{len(profile['quick'])} quick-slot skills")
    if not args.char:
        print("(that is the character played last; use --char <id> if it is the wrong one)")


def cmd_load(args):
    family = pick_family(args.family)
    preset = core.lib_load(args.name)
    backup = core.write_slot(family, args.slot - 1, preset.els)
    print(f"wrote {args.name!r} into slot {args.slot} of family {family}")
    print(f"backup: {backup}")
    profile = core.profile_for_preset(args.name)
    if profile:
        _, _, _, changes = core.plan_skills(profile)
        if changes and args.with_skills:
            core.apply_skills(profile)
            print(f"restored {len(changes)} slot content change(s) on character {profile['char']}")
        elif changes:
            print(f"note: character {profile['char']} differs from the stored slot contents "
                  f"in {len(changes)} place(s); add --with-skills to restore them")
    print(f"in game: Edit UI -> load preset {args.slot}")


def cmd_skills(args):
    if args.capture:
        old = core.profile_for_preset(args.profile)
        family = (old or {}).get("family") or pick_family(args.family)
        char = args.char or (old or {}).get("char")
        if not char:
            raise core.BdoUiError("which character? pass --char <id> (see: bdo-ui chars)")
        profile = core.capture_profile(family, char, keep=old)
        core.save_profile(args.profile, profile)
        print(f"captured character {char}: {len(profile['cooldown'])} cooldown, "
              f"{len(profile['quick'])} quick-slot skills, {len(profile['memo'])} captions")
        return
    profile = core.skills_profile(args.profile)
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    if args.dry_run:
        path, old, new, changes = core.plan_skills(profile, only)
        print(f"{path}\n{len(changes)} change(s):")
        for c in changes:
            print("  " + c)
        return
    backup, changes = core.apply_skills(profile, only=only)
    for c in changes:
        print("  " + c)
    print(f"{len(changes)} change(s) written; backup: {backup}" if backup
          else "nothing to change")


def cmd_chars(args):
    import time
    family = pick_family(args.family)
    if args.name:
        if not args.char:
            raise core.BdoUiError("--name needs --char <id>")
        core.set_char_name(args.char, args.name)
    if not core.skill_db():
        try:
            core.fetch_skill_db()
        except Exception as e:
            print(f"(class list not available: {e})", file=sys.stderr)
    cards = [c for c in core.char_cards(family) if c["order"] is not None or args.all]
    if args.json:
        emit([{**c, "portrait": str(c["portrait"]) if c["portrait"] else None,
               "played": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(c["mtime"]))}
              for c in cards])
        return
    for c in cards:
        kind = " / ".join(p for p in (c["class"], c["spec"]) if p) or "?"
        print(f"{c['char']}  {time.strftime('%Y-%m-%d %H:%M', time.localtime(c['mtime']))}  "
              f"{c['name'] or '-':<16} {kind:<24} {c['cooldown']:>2} cooldown, "
              f"{c['quick']:>2} quick  {', '.join(c['entries'])}")


def cmd_icons(args):
    profile = core.skills_profile(args.profile)
    fetched, failed = core.fetch_profile_icons(
        profile, progress=lambda skill: print(f"  {skill}", flush=True))
    have = sum(1 for s in set(core.slot_skills(profile).values()) if core.icon_path(s))
    print(f"{fetched} downloaded, {have} cached in {core.config.ICON_DIR}")
    for skill, err in failed:
        print(f"  failed {skill}: {err}", file=sys.stderr)
    return 1 if failed else 0


def cmd_docs(args):
    if args.path:
        print(f"saved: {core.set_docs(args.path)}")
    else:
        state = "ok" if core.docs_valid() else "NOT FOUND"
        print(f"{core.config.BDO_DIR}  [{state}]")
        print(f"config: {core.config.CONFIG_PATH}")


def cmd_update(args):
    from . import updater
    try:
        newer = updater.check()
        if not newer:
            print(f"bdo-ui {updater.local_version()} is the latest version")
            return 0
        print(f"version {newer} is available (installed: {updater.local_version()})")
        if args.check:
            return 0
        print(f"now at version {updater.install()}")
    except updater.UpdateError as e:
        print(f"bdo-ui: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_gui(args):
    from .gui.app import run
    return run(getattr(args, "name", None))


def main():
    ap = argparse.ArgumentParser(prog="bdo-ui", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="store_true", help="print the installed version")
    ap.add_argument("--family", help="family id (default: most recently played)")
    sub = ap.add_subparsers(dest="cmd", metavar="<command>")

    def command(name, fn, text, epilog=None):
        p = sub.add_parser(name, help=text, description=text, epilog=epilog,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        p.set_defaults(fn=fn)
        return p

    as_json = dict(action="store_true", help="print JSON instead of text")

    p = command("list", cmd_list, "Library presets and the three game slots of the family.")
    p.add_argument("--json", **as_json)

    p = command("show", cmd_show,
                "Panels of a library preset or of a game slot: position, size, visibility.",
                "Positions and sizes are in UI units; the origin is the top left corner of\n"
                "the screen, whose size is printed first. The first column is the name the\n"
                "'set' command takes: C0..C19 are cooldown slots, Q1..Q20 quick slots,\n"
                "chat1.. chat windows, a number is the panel index.")
    p.add_argument("name", nargs="?", help="library preset")
    p.add_argument("--slot", type=int, choices=[1, 2, 3], help="read a game slot instead")
    p.add_argument("--json", **as_json)

    p = command("set", cmd_set,
                "Move, show or hide panels of a library preset. Works while the game runs:\n"
                "only the library is changed, 'load' then puts the preset into a game slot.",
                "examples:\n"
                "  bdo-ui set \"my layout\" C0 --x 900 --y 1500\n"
                "  bdo-ui set \"my layout\" Q1 Q2 Q3 --dy -40\n"
                "  bdo-ui set \"my layout\" 55 chat2 --hide\n"
                "  bdo-ui set \"my layout\" --from changes.json --dry-run\n\n"
                "--from takes a JSON list such as\n"
                "  [{\"panel\": \"C0\", \"x\": 900, \"y\": 1500}, {\"panel\": \"Q1\", \"shown\": false}]\n"
                "with the keys x, y, dx, dy, shown; the edited output of 'show --json' is\n"
                "accepted too, panels that did not change are skipped.")
    p.add_argument("name", help="library preset")
    p.add_argument("panels", nargs="*", metavar="panel",
                   help="panel as 'show' names it (C0, Q1, chat1, an index) or its full name")
    p.add_argument("--x", type=int, help="left edge, UI units")
    p.add_argument("--y", type=int, help="top edge, UI units")
    p.add_argument("--dx", type=int, help="move right by this much (negative: left)")
    p.add_argument("--dy", type=int, help="move down by this much (negative: up)")
    p.add_argument("--show", dest="shown", action="store_true", default=None,
                   help="make the panels visible in game")
    p.add_argument("--hide", dest="shown", action="store_false",
                   help="hide the panels in game")
    p.add_argument("--from", dest="source", metavar="FILE",
                   help="JSON file with a list of changes, '-' for standard input")
    p.add_argument("--dry-run", action="store_true", help="report the changes, save nothing")
    p.add_argument("--json", **as_json)

    p = command("save", cmd_save,
                "Copy a game slot into the library, together with what sits in the cooldown\n"
                "and quick slots of a character. Works while the game runs.")
    p.add_argument("name", help="name of the library preset to create")
    p.add_argument("slot", type=int, choices=[1, 2, 3], help="game slot to copy")
    p.add_argument("--force", action="store_true", help="overwrite an existing preset")
    p.add_argument("--char", help="character whose slot contents to store "
                                  "(default: the one played last)")
    p.add_argument("--no-skills", action="store_true", help="store the layout only")

    p = command("load", cmd_load,
                "Put a library preset into a game slot. The game must be closed; the game\n"
                "file is backed up first. In game: Edit UI -> load that preset.")
    p.add_argument("name", help="library preset")
    p.add_argument("slot", type=int, choices=[1, 2, 3], help="game slot to overwrite")
    p.add_argument("--with-skills", action="store_true",
                   help="also restore cooldown/quick slot contents and captions")

    p = command("chars", cmd_chars, "Characters of the family, in the game's own order.")
    p.add_argument("--all", action="store_true", help="include characters no longer in the game")
    p.add_argument("--char", help="character id to name")
    p.add_argument("--name", help="name to remember for --char")
    p.add_argument("--json", **as_json)

    p = command("skills", cmd_skills,
                "Write a skill profile (cooldown slots, quick slots, hotkey captions) into\n"
                "its character file. The game must be closed; the file is backed up first.",
                "The profile is <library>/skills/<profile>.json; AGENTS.md describes it.")
    p.add_argument("profile", help="name of the library entry")
    p.add_argument("--dry-run", action="store_true",
                   help="list what would change, write nothing")
    p.add_argument("--only", help="comma list of: cooldown, quick, memo")
    p.add_argument("--capture", action="store_true",
                   help="re-read the profile from the character instead of writing")
    p.add_argument("--char", help="character id for --capture")

    p = command("icons", cmd_icons,
                "Download the skill icons of a profile from bdocodex.com for the editor.")
    p.add_argument("profile", help="name of the library entry")

    p = command("docs", cmd_docs,
                "Show, or set and remember, the game's 'Black Desert' documents folder.")
    p.add_argument("path", nargs="?", help="folder with GameOption.txt and UserCache")

    p = command("update", cmd_update, "Install the newest version from GitHub.")
    p.add_argument("--check", action="store_true", help="only look, do not install")

    p = command("edit", cmd_gui, "Open the editor on a library preset.")
    p.add_argument("name", help="library preset")
    args = ap.parse_args()
    if args.version:
        from . import updater
        print(updater.local_version())
        return 0
    try:
        return (args.fn if args.cmd else cmd_gui)(args) or 0
    except core.BdoUiError as e:
        print(f"bdo-ui: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"bdo-ui: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
