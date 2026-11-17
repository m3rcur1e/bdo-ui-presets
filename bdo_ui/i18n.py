# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Interface languages: one JSON catalog per language, picked at run time.

    lang/en.json    the source catalog: every key the program uses
    lang/<code>.json  a translation; whatever it lacks falls back to English

A catalog is a flat JSON object of key -> text. Texts take str.format
placeholders ("{name}"). A counted text is a list of plural forms, chosen by
the catalog's "@plural" rule, which is a gettext Plural-Forms expression of n.
"@language" is the language's own name, shown in the Language menu.

Nothing here needs Qt, so the core package and the command line can use it too. Until
set_language() is called everything is English, which is what the CLI gets.

    python3 -m bdo_ui.i18n [code ...]     check the catalogs (all of them by default)
"""

import gettext
import json
import re
import string
import sys
from pathlib import Path

LANG_DIR = Path(__file__).resolve().parent / "lang"
SOURCE = "en"
DEFAULT_PLURAL = "n != 1"
# Keys that are built at run time, so the checker cannot see them in the code.
DYNAMIC_PREFIXES = ("panel.", "tip.", "btn.")
DYNAMIC_SUFFIXES = (".tip",)

_catalogs = None
_current = SOURCE


def _plural_rule(expr):
    try:
        return gettext.c2py(expr or DEFAULT_PLURAL)
    except Exception:               # a broken rule must not take the catalog down
        return gettext.c2py(DEFAULT_PLURAL)


class Catalog:
    def __init__(self, code, data):
        self.code = code
        self.name = str(data.get("@language") or code)
        self.plural_expr = data.get("@plural") or DEFAULT_PLURAL
        self.plural = _plural_rule(data.get("@plural"))
        self.texts = {k: v for k, v in data.items() if not k.startswith("@")}

    def form(self, key, n=None):
        """The text of `key` for the count `n`, or None if the catalog has none."""
        value = self.texts.get(key)
        if isinstance(value, list) and value:
            try:
                i = self.plural(abs(int(n))) if n is not None else len(value) - 1
            except (TypeError, ValueError):
                i = len(value) - 1
            value = value[min(max(int(i), 0), len(value) - 1)]
        return value if isinstance(value, str) else None


def read_catalog(path):
    """Parse one catalog file; raises OSError / ValueError if it is unusable."""
    # utf-8-sig: explicit UTF-8 (the Windows default is not), tolerating a BOM.
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("a catalog must be a JSON object")
    return data


def catalogs(reload=False):
    """{code: Catalog} of every readable catalog in LANG_DIR."""
    global _catalogs
    if _catalogs is None or reload:
        found = {}
        for path in sorted(LANG_DIR.glob("*.json")) if LANG_DIR.is_dir() else []:
            try:
                found[path.stem] = Catalog(path.stem, read_catalog(path))
            except (OSError, ValueError):
                continue            # a damaged catalog is simply not offered
        _catalogs = found
    return _catalogs


def names():
    """{code: the language's own name}, English first."""
    cats = catalogs()
    codes = sorted(cats, key=lambda c: (c != SOURCE, cats[c].name.lower()))
    return {code: cats[code].name for code in codes}


def match(locales):
    """The catalog code that suits the first of some locale names, or None.

    Accepts what QLocale gives: "ru-UA", "uk_UA", "en-Latn-US", "pt_BR".
    """
    codes = {code.lower().replace("-", "_"): code for code in catalogs()}
    for locale in locales:
        parts = [p for p in re.split(r"[-_.@]", str(locale).lower()) if p]
        for cand in ("_".join(parts[:2]), parts[0] if parts else ""):
            if cand in codes:
                return codes[cand]
    return None


def set_language(code):
    """Switch to a catalog; an unknown code means English. Returns the code in use."""
    global _current
    _current = code if code in catalogs() else SOURCE
    return _current


def language():
    return _current


def _chain():
    cats = catalogs()
    return [cats[code] for code in dict.fromkeys((_current, SOURCE)) if code in cats]


def has(key):
    """True if the source catalog knows the key."""
    cat = catalogs().get(SOURCE)
    return bool(cat) and key in cat.texts


def keys(prefix):
    """Source catalog keys that start with `prefix`, numbered ones in numeric order."""
    cat = catalogs().get(SOURCE)
    found = [k for k in (cat.texts if cat else ()) if k.startswith(prefix)]
    return sorted(found, key=lambda k: [int(p) if p.isdigit() else p
                                        for p in re.split(r"(\d+)", k)])


def tr(key, **values):
    """The text of `key` in the current language, with placeholders filled in.

    Falls back to English when the catalog lacks the key or its text does not
    format; never raises.
    """
    raw = None
    for cat in _chain():
        text = cat.form(key, values.get("n"))
        if text is None:
            continue
        raw = text
        try:
            return text.format(**values) if values else text
        except (KeyError, IndexError, ValueError):
            continue                # wrong placeholder in a translation
    return raw if raw is not None else key


def trn(key, n, **values):
    """tr() for a counted text: picks the plural form for `n` (also given as {n})."""
    return tr(key, n=n, **values)


# ---------------------------------------------------------------- checker

_KEY_RE = re.compile(r"^[a-z_]+(\.[a-z0-9_]+)+$")


def _fields(text):
    """Placeholder names of a format string, or None if it does not parse."""
    try:
        return {name.split(".")[0].split("[")[0]
                for _, name, _, _ in string.Formatter().parse(text) if name is not None}
    except ValueError:
        return None


def _forms(value):
    return value if isinstance(value, list) else [value]


def _plural_count(rule):
    return max(int(rule(n)) for n in range(0, 201)) + 1


def code_keys(root=None):
    """Every string literal of the program's .py files (catalog keys are among them)."""
    import ast
    strings = set()
    for path in sorted(Path(root or Path(__file__).resolve().parent).rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                strings.add(node.value)
    return strings


def check_source(source):
    """Problems of the English catalog against the program's source code."""
    problems = []
    strings = code_keys()
    spaces = {key.split(".")[0] for key in source}
    for key in sorted(source):
        value = source[key]
        if not all(isinstance(f, str) for f in _forms(value)) or not _forms(value):
            problems.append(f"bad value: {key}")
        elif any(_fields(f) is None for f in _forms(value)):
            problems.append(f"bad placeholder syntax: {key}")
        if key in strings or key.startswith(DYNAMIC_PREFIXES) or any(
                key.endswith(end) and key[:-len(end)] in strings for end in DYNAMIC_SUFFIXES):
            continue
        problems.append(f"unused (not named in the code): {key}")
    for text in sorted(strings):
        if _KEY_RE.match(text) and text.split(".")[0] in spaces and text not in source:
            problems.append(f"used in the code but missing: {text}")
    return problems


def check_translation(data, source):
    """Problems of one translated catalog against the English one."""
    problems = []
    if not data.get("@language"):
        problems.append('no "@language" (the language\'s own name)')
    expr = data.get("@plural")
    try:
        rule = gettext.c2py(expr or DEFAULT_PLURAL)
        forms = _plural_count(rule)
    except Exception as e:
        problems.append(f'bad "@plural" rule: {e}')
        rule, forms = None, None
    texts = {k: v for k, v in data.items() if not k.startswith("@")}
    for key in sorted(source):
        if key not in texts:
            problems.append(f"missing (shown in English): {key}")
    for key in sorted(texts):
        if key not in source:
            problems.append(f"unknown key (not in {SOURCE}.json): {key}")
            continue
        value, original = texts[key], source[key]
        if not _forms(value) or not all(isinstance(f, str) for f in _forms(value)):
            problems.append(f"bad value (text or list of texts expected): {key}")
            continue
        if isinstance(value, list) and not isinstance(original, list):
            problems.append(f"plural forms given for a text that is not counted: {key}")
            continue
        if isinstance(value, list) and forms and len(value) != forms:
            problems.append(f"{len(value)} plural forms, the rule needs {forms}: {key}")
        wanted = set().union(*(_fields(f) or set() for f in _forms(original)))
        for text in _forms(value):
            got = _fields(text)
            if got is None:
                problems.append(f"bad placeholder syntax: {key}")
                break
            extra, lost = got - wanted, wanted - got
            # One form of a counted text may spell the number out ("one panel").
            if isinstance(value, list):
                lost -= {"n"}
            if extra or lost:
                problems.append(
                    f"placeholders differ: {key}"
                    + (f"  unknown {{{'}, {'.join(sorted(extra))}}}" if extra else "")
                    + (f"  lost {{{'}, {'.join(sorted(lost))}}}" if lost else ""))
                break
        edges = {(f[:1].isspace(), f[-1:].isspace()) for f in _forms(original)}
        if any((f[:1].isspace(), f[-1:].isspace()) not in edges for f in _forms(value)):
            problems.append(f"leading / trailing space differs: {key}")
    return problems


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")    # language names on a legacy console
    try:
        source = {k: v for k, v in read_catalog(LANG_DIR / f"{SOURCE}.json").items()
                  if not k.startswith("@")}
    except (OSError, ValueError) as e:
        print(f"{SOURCE}.json: cannot be read: {e}")
        return 1
    wanted = argv or sorted(p.stem for p in LANG_DIR.glob("*.json"))
    failed = False
    for code in wanted:
        path = LANG_DIR / f"{code}.json"
        try:
            data = read_catalog(path)
        except (OSError, ValueError) as e:
            print(f"{path.name}: cannot be read: {e}")
            failed = True
            continue
        problems = check_source(source) if code == SOURCE else check_translation(data, source)
        count = sum(1 for k in data if not k.startswith("@"))
        state = "ok" if not problems else f"{len(problems)} problem(s)"
        print(f"{path.name}  {data.get('@language', '?')}  {count} of {len(source)} keys  {state}")
        for line in problems:
            print("  " + line)
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
