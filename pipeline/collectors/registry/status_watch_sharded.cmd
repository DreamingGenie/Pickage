@echo off
rem registry 4분할 수집 현황 창 — 더블클릭. 60초마다 갱신. 이 창을 닫아도 수집기는 계속 돕니다.
rem 전체 진행률·남은 시간(가장 늦는 샤드 기준)과 샤드별 상태를 같이 보여 줍니다.
setlocal
chcp 65001 >nul
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
rem start_registry_sharded.cmd 와 같은 값이어야 합니다.
set RUN=2026-09-16
set SHARDS=4
set PY=%ROOT%\.venv-bq\Scripts\python.exe
"%PY%" "%ROOT%\pipeline\collectors\registry\status.py" --run %RUN% --shards %SHARDS% --watch
pause
