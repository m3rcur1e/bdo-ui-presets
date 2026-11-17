#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""bdo-ui: library and editor for Black Desert UI presets.

    bdo-ui                       open the editor
    bdo-ui edit <name>           open the editor on a library preset
    bdo-ui list                  library presets and the game slots
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
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

import core  # noqa: E402


def pick_family(arg):
    fams = core.families()
    if arg:
        if arg not in fams:
            raise core.BdoUiError(f"unknown family {arg}; have: {', '.join(fams)}")
        return arg
    if not fams:
        raise core.BdoUiError(f"no families found under {core.BDO_DIR}")
    return fams[0]


def cmd_list(args):
    family = pick_family(args.family)
    print("Library:", core.LIB_DIR)
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
    for c in core.char_cards(family):
        if c["order"] is None and not args.all:
            continue
        kind = " / ".join(p for p in (c["class"], c["spec"]) if p) or "?"
        print(f"{c['char']}  {time.strftime('%Y-%m-%d %H:%M', time.localtime(c['mtime']))}  "
              f"{c['name'] or '-':<16} {kind:<24} {c['cooldown']:>2} cooldown, "
              f"{c['quick']:>2} quick  {', '.join(c['entries'])}")


def cmd_icons(args):
    profile = core.skills_profile(args.profile)
    fetched, failed = core.fetch_profile_icons(
        profile, progress=lambda skill: print(f"  {skill}", flush=True))
    have = sum(1 for s in set(core.slot_skills(profile).values()) if core.icon_path(s))
    print(f"{fetched} downloaded, {have} cached in {core.ICON_DIR}")
    for skill, err in failed:
        print(f"  failed {skill}: {err}", file=sys.stderr)
    return 1 if failed else 0


def cmd_docs(args):
    if args.path:
        print(f"saved: {core.set_docs(args.path)}")
    else:
        state = "ok" if core.docs_valid() else "NOT FOUND"
        print(f"{core.BDO_DIR}  [{state}]")
        print(f"config: {core.CONFIG_PATH}")


def cmd_update(args):
    import updater
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
    import gui
    return gui.run(getattr(args, "name", None))


def main():
    ap = argparse.ArgumentParser(prog="bdo-ui", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="store_true", help="print the installed version")
    ap.add_argument("--family", help="family id (default: most recently played)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("save")
    p.add_argument("name")
    p.add_argument("slot", type=int, choices=[1, 2, 3])
    p.add_argument("--force", action="store_true", help="overwrite an existing preset")
    p.add_argument("--char", help="character whose slot contents to store")
    p.add_argument("--no-skills", action="store_true", help="store the layout only")
    p.set_defaults(fn=cmd_save)
    p = sub.add_parser("load")
    p.add_argument("name")
    p.add_argument("slot", type=int, choices=[1, 2, 3])
    p.add_argument("--with-skills", action="store_true",
                   help="also restore cooldown/quick slot contents and captions")
    p.set_defaults(fn=cmd_load)
    p = sub.add_parser("chars")
    p.add_argument("--all", action="store_true", help="include characters no longer in the game")
    p.add_argument("--char", help="character id to name")
    p.add_argument("--name", help="name to remember for --char")
    p.set_defaults(fn=cmd_chars)
    p = sub.add_parser("skills")
    p.add_argument("profile")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--only", help="comma list of: cooldown, quick, memo")
    p.add_argument("--capture", action="store_true",
                   help="re-read the profile from the character instead of writing")
    p.add_argument("--char", help="character id for --capture")
    p.set_defaults(fn=cmd_skills)
    p = sub.add_parser("icons")
    p.add_argument("profile")
    p.set_defaults(fn=cmd_icons)
    p = sub.add_parser("docs")
    p.add_argument("path", nargs="?")
    p.set_defaults(fn=cmd_docs)
    p = sub.add_parser("update")
    p.add_argument("--check", action="store_true", help="only look, do not install")
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("edit")
    p.add_argument("name")
    p.set_defaults(fn=cmd_gui)
    args = ap.parse_args()
    if args.version:
        import updater
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
