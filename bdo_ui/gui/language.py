# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 m3rcur1e
"""Interface language of the editor: the remembered choice and switching."""

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from .. import core, i18n

LANG_AUTO = "auto"          # config value: follow the system locale
_qt_translator = None


def system_language():
    """Catalog code for the system locale; English when there is no such catalog."""
    locale = QLocale.system()
    return i18n.match([*locale.uiLanguages(), locale.name()]) or i18n.SOURCE


def configured_language():
    """The remembered choice: a catalog code, or LANG_AUTO."""
    choice = core.load_config().get("language")
    return choice if choice in i18n.names() else LANG_AUTO


def apply_language(choice):
    """Switch the texts to a catalog code or LANG_AUTO; returns the code in use."""
    global _qt_translator
    code = i18n.set_language(system_language() if choice == LANG_AUTO else choice)
    # Best effort for the texts Qt draws itself (context menu of an edit field,
    # the non-native file dialog); Qt builds without this translation stay English.
    app = QApplication.instance()
    if app:
        if _qt_translator:
            app.removeTranslator(_qt_translator)
            _qt_translator = None
        translator = QTranslator(app)
        if code != i18n.SOURCE and translator.load(
                "qtbase_" + code, QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
            app.installTranslator(translator)
            _qt_translator = translator
    return code
