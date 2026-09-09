@echo off
rem npm registry 버전 이력 수집 시작·재시작 — 더블클릭 또는 터미널에서 실행. 체크포인트부터 이어간다.
rem 이미 돌고 있으면 새로 띄우지 않는다(같은 IP에서 두 개가 돌면 429만 늘어남).
setlocal
chcp 65001 >nul
rem 리포 루트 = 이 파일의 세 단계 상위 (pipeline\collectors\registry\ 아래에 있다)
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
set RUN=2026-09-09
rem 요청 간격(초). 스모크 결과(수집계획 §7)로 확정. 429 가 나오면 수집기가 스스로 늘린다.
set INTERVAL=0.5
set TARGETS=%ROOT%\datasets\targets\rank_top100k_20260902.csv
set PY=%ROOT%\.venv-bq\Scripts\python.exe
set LOG=%ROOT%\data\registry\raw\registry_%RUN%.log
if "%OSS_SHIFT_UA_CONTACT%"=="" (
  echo [start_registry] 환경변수 OSS_SHIFT_UA_CONTACT 가 없습니다. collect.py 는 User-Agent 연락처 없이 시작하지 않습니다.
  echo   setx OSS_SHIFT_UA_CONTACT ^<이메일 또는 URL^>  실행 후 새 창에서 다시 시작하세요.
  pause
  exit /b 1
)
if not exist "%PY%" (
  echo [start_registry] %PY% 가 없습니다. 리포 루트의 .venv-bq 가 있는 트리에서 실행하세요.
  pause
  exit /b 1
)
if not exist "%ROOT%\data\registry\raw" mkdir "%ROOT%\data\registry\raw"

powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*registry*collect.py*' } | Measure-Object).Count -gt 0) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [start_registry] 이미 실행 중입니다. 상태 확인: python pipeline\collectors\registry\status.py --run %RUN%
  pause
  exit /b 0
)

echo [start_registry] 시작 %DATE% %TIME%  간격 %INTERVAL%s  로그: %LOG%
start "npm-registry-collect" /MIN cmd /c ""%PY%" -u "%ROOT%\pipeline\collectors\registry\collect.py" --targets "%TARGETS%" --run %RUN% --out "%ROOT%\data\registry\raw" --interval %INTERVAL% >> "%LOG%" 2>&1"
timeout /t 5 >nul
"%PY%" "%ROOT%\pipeline\collectors\registry\status.py" --run %RUN%
pause
