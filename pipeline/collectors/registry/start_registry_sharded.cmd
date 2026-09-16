@echo off
rem npm registry 4분할 수집 시작·재시작 — 더블클릭 또는 터미널에서 실행 (S15P21A506-366).
rem 수집기 자체는 직렬 그대로다. 대상 CSV 를 SHARDS 등분해 프로세스를 그 수만큼 띄운다.
rem   09-09 직렬 1개 = 17.9시간 실측. 4개 = 약 4.5시간.
rem 샤드마다 자기 run 폴더·체크포인트·Writer 를 갖는다. 중간에 죽어도 다시 더블클릭하면
rem 죽은 샤드만 골라 이어서 띄운다(살아 있는 샤드는 건드리지 않는다).
setlocal enabledelayedexpansion
chcp 65001 >nul
rem 리포 루트 = 이 파일의 세 단계 상위
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
set RUN=2026-09-16
set SHARDS=4
rem 샤드 1개의 요청 간격(초). 4개가 동시에 도니 전체는 초당 약 8건이다.
rem 실측(순위를 섞은 1,000건 지속 부하, 동시 4)에서 초당 10건·429 0건이었다.
rem 429 가 보이면 INTERVAL 을 늘린다. SHARDS 를 줄이면 안 된다 — 대상 분배가 통째로 바뀌는데
rem run 이름은 그대로라, 이미 받아 둔 샤드와 대상이 겹쳐 같은 패키지를 두 번 받고
rem to_parquet 의 이름 중복 검사에 걸려 변환이 멈춘다. SHARDS 를 바꿔야 하면 RUN 도 새 이름으로 잡는다.
set INTERVAL=0.5
set TARGETS=%ROOT%\datasets\targets\rank_top100k_20260902.csv
rem 샤드 CSV 이름은 shard_targets.py 가 --targets 의 파일명으로 짓는다. 여기서 따로 적으면
rem TARGETS 만 바꿨을 때 없는 파일을 가리키므로, 적지 말고 TARGETS 에서 파생한다.
for %%I in ("%TARGETS%") do set BASENAME=%%~nI
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

rem 이 RUN 의 샤드가 아닌 수집기가 돌고 있으면 아무것도 띄우지 않는다.
rem 같은 IP 에서 예정보다 많이 돌면 429 만 늘어난다(직렬 start_registry.cmd 가 떠 있는 경우 등).
powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*registry*collect.py*' -and $_.CommandLine -notlike '*--run %RUN%-s*' } | Measure-Object).Count -gt 0) { exit 3 } else { exit 0 }"
set RC=%ERRORLEVEL%
if "%RC%"=="3" (
  echo [start_registry_sharded] 이 RUN 의 샤드가 아닌 registry 수집기가 이미 돌고 있습니다. 그것이 끝난 뒤 시작하세요.
  pause
  exit /b 0
)
if not "%RC%"=="0" (
  echo [start_registry_sharded] 실행 중 검사가 실패했습니다. errorlevel=%RC% - 이미 도는 수집기가 있는지 알 수 없어 아무것도 띄우지 않습니다.
  pause
  exit /b 1
)

rem 대상 CSV 를 순위로 돌아가며 나눈다(결정적이라 다시 돌려도 같은 결과).
"%PY%" "%SRC%\shard_targets.py" --targets "%TARGETS%" --shards %SHARDS% --out "%SHARDDIR%"
if errorlevel 1 (
  echo [start_registry_sharded] 대상 분할에 실패했습니다.
  pause
  exit /b 1
)

set STARTED=0
set SKIPPED=0
for /L %%i in (1,1,%SHARDS%) do call :start_one %%i

echo [start_registry_sharded] %DATE% %TIME%  새로 띄움 !STARTED!개 · 이미 돌고 있어 건너뜀 !SKIPPED!개  샤드당 간격 %INTERVAL%s
echo [start_registry_sharded] 진행 상황은 status_watch_sharded.cmd (더블클릭) 로 봅니다.
timeout /t 8 >nul
"%PY%" "%SRC%\status.py" --run %RUN% --shards %SHARDS%
pause
exit /b 0

rem ── 샤드 하나를 띄운다. 이미 그 run 을 돌리고 있으면 건드리지 않는다 ──
rem 검사를 샤드별로 하는 이유: 4개 중 하나만 죽었을 때 다시 더블클릭해 그 하나만 살리기 위해서다.
rem 전체를 한 번에 검사하면 살아 있는 3개 때문에 죽은 1개를 되살릴 수 없다.
:start_one
set IDX=%1
set SRUN=%RUN%-s%IDX%
set SCSV=%SHARDDIR%\%BASENAME%-s%IDX%of%SHARDS%.csv
set SLOG=%RAWDIR%\registry_%RUN%-s%IDX%.log
powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*registry*collect.py*' -and $_.CommandLine -like '*--run %SRUN% *' } | Measure-Object).Count -gt 0) { exit 3 } else { exit 0 }"
set RC=%ERRORLEVEL%
if "%RC%"=="3" (
  echo [start_registry_sharded] 샤드 %IDX%/%SHARDS%  run=%SRUN%  이미 실행 중 — 건너뜁니다
  set /a SKIPPED+=1
  exit /b 0
)
if not "%RC%"=="0" (
  echo [start_registry_sharded] 샤드 %IDX%/%SHARDS%  실행 중 검사 실패 errorlevel=%RC% - 두 번 띄우지 않으려고 건너뜁니다
  set /a SKIPPED+=1
  exit /b 0
)
if not exist "%SCSV%" (
  echo [start_registry_sharded] 샤드 %IDX%/%SHARDS%  대상 파일이 없습니다: %SCSV%
  exit /b 0
)
echo [start_registry_sharded] 샤드 %IDX%/%SHARDS%  run=%SRUN%  로그: %SLOG%
start "npm-registry-collect-s%IDX%" /MIN cmd /c ""%PY%" -u "%SRC%\collect.py" --targets "%SCSV%" --run %SRUN% --out "%RAWDIR%" --interval %INTERVAL% >> "%SLOG%" 2>&1"
set /a STARTED+=1
exit /b 0
