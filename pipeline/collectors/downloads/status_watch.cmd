@echo off
rem npm downloads 수집 현황 창 — 더블클릭. 60초마다 갱신, 닫아도 수집기에는 영향 없음.
title npm downloads 수집 현황
chcp 65001 >nul
rem 리포 루트 = 이 파일의 세 단계 상위 (pipeline\collectors\downloads\ 아래에 있다)
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
"%ROOT%\.venv-bq\Scripts\python.exe" "%ROOT%\pipeline\collectors\downloads\status.py" --run 2026-09-02 --watch --interval 60
pause
