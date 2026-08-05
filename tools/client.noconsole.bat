@echo off
cd /d "%~dp0.."
set PYTHONPATH=%~dp0..\src
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
start "" pythonw -m client.main