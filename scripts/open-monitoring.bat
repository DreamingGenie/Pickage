@echo off
REM 서버 모니터링 화면 열기 (Windows)
REM
REM   scripts\open-monitoring.bat
REM
REM SSH 터널을 열고 브라우저로 "지금 어때" 화면을 띄웁니다.
REM 리눅스를 몰라도 이 파일만 더블클릭하면 됩니다.
REM
REM 끝낼 때: 이 검은 창을 닫으면 터널이 끊깁니다.
REM 설명: deploy\prod\monitoring\README.md

setlocal
chcp 65001 >nul

set "SSH_TARGET=%~1"
if "%SSH_TARGET%"=="" set "SSH_TARGET=%PICKAGE_SSH_TARGET%"
if "%SSH_TARGET%"=="" set "SSH_TARGET=ubuntu@j15a506.p.ssafy.io"

set "KEYOPT="
if not "%PICKAGE_SSH_KEY%"=="" set "KEYOPT=-i "%PICKAGE_SSH_KEY%""

where ssh >nul 2>&1
if errorlevel 1 (
  echo [오류] ssh 를 찾을 수 없습니다.
  echo        Windows 설정 ^> 앱 ^> 선택적 기능에서 "OpenSSH 클라이언트"를 설치하세요.
  pause
  exit /b 1
)

REM 19999 를 이미 누가 쓰고 있으면 터널이 조용히 실패하고 남의 화면이 열립니다.
netstat -ano | findstr /R /C:"127.0.0.1:19999 .*LISTENING" >nul
if not errorlevel 1 (
  echo [알림] 19999 번이 이미 열려 있습니다. 터널이 이미 떠 있는 것 같습니다.
  echo        브라우저만 엽니다.
  start "" "http://127.0.0.1:19999/status.html"
  pause
  exit /b 0
)

echo 서버에 연결합니다: %SSH_TARGET%
echo.
echo  - 잠시 뒤 브라우저가 열립니다. 처음 몇 초는 빨간 화면일 수 있는데,
echo    연결되면 저절로 바뀝니다.
echo  - 다 보셨으면 ^*^*이 창을 닫으세요^*^*. 그래야 터널이 끊깁니다.
echo.

start "" "http://127.0.0.1:19999/status.html"
ssh -N -L 127.0.0.1:19999:127.0.0.1:19999 %KEYOPT% %SSH_TARGET%

echo.
echo 터널이 끊겼습니다.
pause
