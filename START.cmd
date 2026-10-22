@echo off
setlocal
cd /d "%~dp0"
set "PORTFOLIO_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PORTFOLIO_PY%" goto bundled
where py >nul 2>nul
if not errorlevel 1 goto pylauncher
python app.py
goto finish
:pylauncher
py -3 app.py
goto finish
:bundled
"%PORTFOLIO_PY%" app.py
:finish
pause
