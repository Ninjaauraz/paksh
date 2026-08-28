@echo off
setlocal
REM ============================================================
REM  Paksh REFRAME batch (Windows Task Scheduler, 07:30).
REM  Fills missing L/C/R framing on the backlog (300/run, ranked
REM  top-tier-first with a reserved slice for single-lane events -
REM  see reframe.py's SINGLE_LANE_RESERVE, Paksh 7B) via Gemini,
REM  then rebuilds and guard-pushes the site. Gemini-only is
REM  intentional: if Gemini is down it skips (fails safe) rather
REM  than degrading. Interlocked with refresh.
REM  Paksh 7B: dropped --top-tier so single-lane events are no
REM  longer PERMANENTLY excluded from this job - _rank_key() still
REM  puts top-tier events first, SINGLE_LANE_RESERVE just guarantees
REM  single-lane events a bounded slice of the same 300/day cap.
REM  Now EXITS WITH THE REAL RESULT (no trailing echo masking a
REM  failure). No article-grow check here: reframe fills framing,
REM  it never ingests, so "articles didn't grow" is expected.
REM  Logs to reframe_log.txt.
REM ============================================================
cd /d "C:\paksh_project\paksh"
REM force UTF-8 so Devanagari (Hindi) titles never crash a cp1252-redirected log
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PAKSH_LLM_BACKEND=gemini
echo. >> reframe_log.txt
echo ===================================================== >> reframe_log.txt
echo Run started:  %date% %time% >> reframe_log.txt
py runlocked.py reframe -- cmd /c "py reframe.py --apply --limit 300 && py export_static.py && py safe_autopush.py reframe" >> reframe_log.txt 2>&1
set RC=%ERRORLEVEL%
echo Run finished (exit %RC%): %date% %time% >> reframe_log.txt
endlocal & exit /b %RC%
