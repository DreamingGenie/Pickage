@echo off
REM ============================================================================
REM  Realtime collector - foreground launcher (V3 ASD friendly)
REM
REM  This script deliberately does NOT hide its window, does NOT wrap itself in
REM  wscript, and does NOT install itself into autostart. Those three are the
REM  signals AhnLab V3's behavior engine (ASD) treats as malware. A child
REM  process of a visible, user-launched terminal is almost never touched.
REM
REM  Batch files are ASCII-only on purpose: cmd.exe reads them in the OEM code
REM  page (cp949 on Korean Windows), so UTF-8 Korean text breaks parsing. User
REM  facing Korean text lives in the Python logs, not here.
REM
REM  Usage : double-click, or run in a terminal. Keep the window open (you may
REM          minimize it). Stop with Ctrl+C (finishes the in-flight call first).
REM
REM  If V3 still stops python, add this folder to the V3 exclusion list.
REM  See OPERATIONS.md "V3 (AhnLab) 예외 등록". Exclusions are a security
REM  setting change, so the user does that step themselves.
REM
REM  Auto-restart: pass --supervise (revives python 60s after it dies). The
REM  window stays visible either way.
REM ============================================================================

cd /d "%~dp0..\.."

if "%JR_PYTHON%"=="" set JR_PYTHON=python

title JR-Collector - collecting, do not close

if /i "%~1"=="--supervise" goto supervise

echo.
echo   Starting realtime Bronze collector. Closing this window stops it.
echo   Stop: Ctrl+C
echo.
"%JR_PYTHON%" -m collector.run_scheduler
goto :eof

:supervise
set STOPFILE=%CD%\data\STOP_COLLECTOR
if exist "%STOPFILE%" del "%STOPFILE%"
echo.
echo   Supervise mode: revives python 60s after it dies.
echo   Stop: Ctrl+C in this window.
echo.
:loop
"%JR_PYTHON%" -m collector.run_scheduler
if exist "%STOPFILE%" goto done
echo [%DATE% %TIME%] collector exited; restarting in 60s (Ctrl+C to stop)
ping -n 61 127.0.0.1 >nul
goto loop
:done
echo Loop stopped.
