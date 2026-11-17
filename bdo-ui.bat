@echo off
rem bdo-ui launcher for Windows. Needs Python 3.10+ and: pip install PySide6
rem Settings are read from Documents\Black Desert; set BDO_DOCS to override.
python "%~dp0main.py" %*
