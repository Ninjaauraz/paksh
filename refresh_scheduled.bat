@echo off
setlocal
REM ============================================================
REM  Paksh NIGHTLY refresh (Windows Task Scheduler, 05:30).
REM  Hardened: runlocked interlock + guarded auto-deploy of the
REM  generated _site/ only. The batch now EXITS
REM  WITH THE REAL RESULT (no trailing echo masking failure), and a
REM  ground-truth data check (verify_fresh.py) makes a run that
REM  ingested nothing while the catalogue is stale fail RED even if
REM  every process returned 0. Logs to refresh_log.txt.
REM ============================================================
cd /d "C:\paksh_project\paksh"
REM force UTF-8 so Devanagari (Hindi) titles never crash a cp1252-redirected log
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
REM Phase 30C-C: hybrid -> pool (Groq openai/gpt-oss-120b -> Gemini -> extractive)
REM while Gemini's billing/dunning denial is pending Google's side (Phase 30C-A/B).
REM Same fallback safety net either way - only which provider is tried FIRST changed.
set PAKSH_LLM_BACKEND=pool

echo. >> refresh_log.txt
echo ===================================================== >> refresh_log.txt
echo Run started:  %date% %time% >> refresh_log.txt

REM 1) baseline: how many articles exist BEFORE the run (ground-truth)
py verify_fresh.py snapshot >> refresh_log.txt 2>&1

REM 2) the interlocked pipeline; capture its TRUE exit code
py runlocked.py refresh -- cmd /c "py refresh.py --gdelt && py safe_autopush.py nightly" >> refresh_log.txt 2>&1
set RC=%ERRORLEVEL%
echo Pipeline exit: %RC% >> refresh_log.txt

REM 3) ground-truth: did articles actually grow / is the catalogue fresh?
py verify_fresh.py check --max-age-hours 36 >> refresh_log.txt 2>&1
set VRC=%ERRORLEVEL%

REM 4) final result = worst of the two -> non-zero shows RED in Task Scheduler
set FINAL=%RC%
if not "%VRC%"=="0" set FINAL=%VRC%
echo Run finished (exit %FINAL%): %date% %time% >> refresh_log.txt
endlocal & exit /b %FINAL%
