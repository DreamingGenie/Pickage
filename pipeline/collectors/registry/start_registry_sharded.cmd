@echo off
rem npm registry 4분할 수집 시작·재시작 — 더블클릭 또는 터미널에서 실행 (S15P21A506-366).
rem 수집기 자체는 직렬 그대로다. 대상 CSV 를 SHARDS 등분해 프로세스를 그 수만큼 띄운다.
rem   09-09 직렬 1개 = 17.9시간 실측. 4개 = 약 4.5시간.
rem 샤드마다 자기 run 폴더·체크포인트·Writer 를 갖는다. 중간에 죽여도 같은 명령으로 이어간다.
setlocal enabledelayedexpansion
chcp 65001 >nul
rem 리포 루트 = 이 파일의 세 단계 상위
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
set RUN=2026-09-16
set SHARDS=4
rem 샤드 1개의 요청 간격(초). 4개가 동시에 도니 전체는 초당 약 8건이다.
rem 실측(순위를 섞은 1,000건 지속 부하, 동시 4)에서 초당 10건·429 0건이었다. 429 가 보이면 SHARDS 를 줄인다.
set INTERVAL=0.5
set BASENAME=rank_top100k_20260902
set TARGETS=%ROOT%\datasets\targets\%BASENAME%.csv
set SHARDDIR=%ROOT%\data\registry\targets
set RAWDIR=%ROOT%\data\registry\raw
set PY=%ROOT%\.venv-bq\Scripts\python.exe
set SRC=%ROOT%\pipeline\collectors\registry
if "%OSS_SHIFT_UA_CONTACT%"=="" (
  echo [start_registry_sharded] 환경변수 OSS_SHIFT_UA_CONTACT 가 없습니다. collect.py 는 User-Agent 연락처 없이 시작하지 않습니다.
  echo   setx OSS_SHIFT_UA_CONTACT ^<이메일 또는 URL^>  실행 후 새 창에서 다시 시작하세요.
  pause
  exit /b 1
)
if not exist "%PY%" (
  echo [start_registry_sharded] %PY% 가 없습니다. 리포 루트의 .venv-bq 가 있는 트리에서 실행하세요.
  pause
  exit /b 1
)
if not exist "%RAWDIR%" mkdir "%RAWDIR%"

rem 이미 돌고 있으면 새로 띄우지 않는다. 같은 IP 에서 예정보다 많이 돌면 429 만 늘어난다.
powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*registry*collect.py*' } | Measure-Object).Count -gt 0) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [start_registry_sharded] 이미 실행 중입니다. 상태 확인은 status_watch_sharded.cmd
  pause
  exit /b 0
)

rem 대상 CSV 를 순위로 돌아가며 나눈다(결정적이라 다시 돌려도 같은 결과).
"%PY%" "%SRC%\shard_targets.py" --targets "%TARGETS%" --shards %SHARDS% --out "%SHARDDIR%"
if errorlevel 1 (
  echo [start_registry_sharded] 대상 분할에 실패했습니다.
  pause
  exit /b 1
)

for /L %%i in (1,1,%SHARDS%) do (
  set SRUN=%RUN%-s%%i
  set SCSV=%SHARDDIR%\%BASENAME%-s%%iof%SHARDS%.csv
  set SLOG=%RAWDIR%\registry_%RUN%-s%%i.log
  echo [start_registry_sharded] 샤드 %%i/%SHARDS%  run=!SRUN!  로그: !SLOG!
  start "npm-registry-collect-s%%i" /MIN cmd /c ""%PY%" -u "%SRC%\collect.py" --targets "!SCSV!" --run !SRUN! --out "%RAWDIR%" --interval %INTERVAL% >> "!SLOG!" 2>&1"
)

echo [start_registry_sharded] 시작 %DATE% %TIME%  샤드 %SHARDS%개  샤드당 간격 %INTERVAL%s
echo [start_registry_sharded] 진행 상황은 status_watch_sharded.cmd (더블클릭) 로 봅니다.
timeout /t 8 >nul
"%PY%" "%SRC%\status.py" --run %RUN% --shards %SHARDS%
pause
