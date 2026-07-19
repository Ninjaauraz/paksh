@echo off
REM ============================================================
REM  Paksh NIGHTLY refresh (Windows Task Scheduler, 05:30).
REM  Full pipeline from the project dir; hybrid LLM backend; logs
REM  to refresh_log.txt here so a silent failure is visible.
REM  Interlocked (runlocked.py) so it can never write paksh.db at
REM  the same time as the reframe job. Guarded auto-deploy of the
REM  generated _site/ only, and only if the pipeline+export succeed.
REM ============================================================
cd /d "C:\paksh_project\paksh"
REM force UTF-8 so Devanagari (Hindi) titles never crash a cp1252-redirected log
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PAKSH_LLM_BACKEND=hybrid
echo. >> refresh_log.txt
echo ===================================================== >> refresh_log.txt
echo Run started:  %date% %time% >> refresh_log.txt
py runlocked.py refresh -- cmd /c "py refresh.py --gdelt && py safe_autopush.py nightly" >> refresh_log.txt 2>&1
echo Run finished (exit %ERRORLEVEL%): %date% %time% >> refresh_log.txt
