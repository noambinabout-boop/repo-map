@echo off
REM Lance la viz repo-map sur un dossier. Usage : viz.bat C:\chemin\vers\projet
cd /d "%~dp0"
".venv\Scripts\python.exe" viz_serve.py %*
