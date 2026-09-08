@echo off
rem ecosyste.ms keywords 수집 시작/재시작 — 더블클릭. 완료된 페이지(part 파일 존재)는 건너뛴다.
rem 이미 돌고 있으면 새로 띄우지 않는다.
setlocal
rem 리포 루트 = 이 파일의 세 단계 상위 (pipeline\collectors\keywords\ 아래에 있다)
for %%I in ("%~dp0..\..\..") do set ROOT=%%~fI
set RUN=2026-09-08
set LOG=%ROOT%\data\keywords\raw\keywords_%RUN%.log
if not exist "%ROOT%\data\keywords\raw" mkdir "%ROOT%\data\keywords\raw"
if "%OSS_SHIFT_UA_CONTACT%"=="" (
  echo [start_keywords] 환경변수 OSS_SHIFT_UA_CONTACT 가 없습니다. collect_keywords.py 는 User-Agent 연락처 없이 시작하지 않습니다.
  echo   setx OSS_SHIFT_UA_CONTACT ^<이메일 또는 URL^>  실행 후 새 창에서 다시 시작하세요.
  pause
  exit /b 1
)

powershell -NoProfile -Command "if ((Get-CimInstance Win32_Process -Filter \"Name like 'python%%'\" | Where-Object { $_.CommandLine -like '*collect_keywords.py*' } | Measure-Object).Count -gt 0) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo [start_keywords] 이미 실행 중입니다. 로그: %LOG%
  pause
  exit /b 0
)

echo [start_keywords] 시작 %DATE% %TIME%  로그: %LOG%
start "ecosystems-keywords" /MIN cmd /c ""%ROOT%\.venv-bq\Scripts\python.exe" -u "%ROOT%\pipeline\collectors\keywords\collect_keywords.py" --run %RUN% --pages 1000 --out "%ROOT%\data\keywords\raw" >> "%LOG%" 2>&1"
