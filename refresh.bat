@echo off
REM ============================================================
REM  refresh.bat  -  double-click to rebuild Paksh
REM  (ingest -> cluster -> analyze -> export_static)
REM  Make sure Ollama is running first.
REM ============================================================
cd /d "%~dp0"
py refresh.py
echo.
echo Done. Review _site, then publish via GitHub Desktop.
pause