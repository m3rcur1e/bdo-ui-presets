@echo off
rem bdo-ui launcher for Windows.
rem The portable package has its own Python in the "python" folder. Without it
rem Python 3.10+ must be installed, and once: pip install -r requirements.txt
rem No arguments opens the editor; "bdo-ui.bat --help" lists the commands.
rem Settings are read from Documents\Black Desert; set BDO_DOCS to override.
setlocal
set "HERE=%~dp0"
if not exist "%HERE%python\python.exe" goto system
if "%~1"=="" goto window
"%HERE%python\python.exe" "%HERE%main.py" %*
exit /b %errorlevel%

:window
rem pythonw: the editor without a console window behind it.
start "" "%HERE%python\pythonw.exe" "%HERE%main.py"
exit /b 0

:system
python "%HERE%main.py" %*
exit /b %errorlevel%
