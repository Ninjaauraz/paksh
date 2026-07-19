@echo off
REM ============================================================
REM  Paksh REFRAME batch (Windows Task Scheduler, 07:30).
REM  Fills missing L/C/R framing on the top-tier backlog (300/run,
REM  newest-first) via Gemini, then rebuilds and guard-pushes the
REM  site. Gemini-only is intentional: if Gemini is down it skips
REM  (fails safe) rather than degrading. Interlocked with refresh.
REM  Logs to reframe_log.txt here.
REM ============================================================
cd /d "C:\paksh_project\paksh"
REM force UTF-8 so Devanagari (Hindi) titles never crash a cp1252-redirected log
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PAKSH_LLM_BACKEND=gemini
echo. >> reframe_log.txt
echo ===================================================== >> reframe_log.txt
echo Run started:  %date% %time% >> reframe_log.txt
py runlocked.py reframe -- cmd /c "py reframe.py --apply --top-tier --limit 300 && py export_static.py && py safe_autopush.py reframe" >> reframe_log.txt 2>&1
echo Run finished (exit %ERRORLEVEL%): %date% %time% >> reframe_log.txt
