@echo off
rem keywords 수집 현황 창 — 더블클릭. 60초마다 갱신, 닫아도 수집기에는 영향 없음.
title ecosyste.ms keywords 수집 현황
chcp 65001 >nul
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
"%ROOT%\.venv-bq\Scripts\python.exe" "%ROOT%\pipeline\collectors\keywords\status.py" --run 2026-09-08 --watch --interval 60
pause
