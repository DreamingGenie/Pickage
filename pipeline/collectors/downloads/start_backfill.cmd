@echo off
rem npm downloads 백필 재시작 — 더블클릭 또는 터미널에서 실행. 체크포인트부터 이어간다.
rem 이미 돌고 있으면 새로 띄우지 않는다(같은 IP에서 두 개가 돌면 429만 늘어남).
setlocal
rem 리포 루트 = 이 파일의 세 단계 상위 (pipeline\collectors\downloads\ 아래에 있다)
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
set RUN=2026-09-02
set LOG=%ROOT%\data\downloads\raw\backfill_%RUN%.log
if "%OSS_SHIFT_UA_CONTACT%"=="" (
  echo [start_backfill] 환경변수 OSS_SHIFT_UA_CONTACT 가 없습니다. collect.py 는 User-Agent 연락처 없이 시작하지 않습니다.
  echo   setx OSS_SHIFT_UA_CONTACT ^<이메일 또는 URL^>  실행 후 새 창에서 다시 시작하세요.
  pause
  exit /b 1
)

powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*downloads*collect.py*' } | Measure-Object).Count -gt 0) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [start_backfill] 이미 실행 중입니다. 상태 확인: python pipeline\collectors\downloads\status.py --run %RUN%
  pause
  exit /b 0
)

echo [start_backfill] 시작 %DATE% %TIME%  로그: %LOG%
start "npm-downloads-backfill" /MIN cmd /c ""%ROOT%\.venv-bq\Scripts\python.exe" -u "%ROOT%\pipeline\collectors\downloads\collect.py" --targets "%ROOT%\data\downloads\targets_top100k_%RUN:-=%.csv" --run %RUN% --end 2026-08-31 --mode backfill --out "%ROOT%\data\downloads\raw" >> "%LOG%" 2>&1"
timeout /t 5 >nul
"%ROOT%\.venv-bq\Scripts\python.exe" "%ROOT%\pipeline\collectors\downloads\status.py" --run %RUN%
pause
