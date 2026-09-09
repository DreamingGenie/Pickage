@echo off
REM 팀 규칙에 맞는 작업 브랜치를 origin/develop 에서 만든다.
REM 실제 로직은 scripts/new-branch.sh 에 하나만 두고 여기서는 위임한다.
REM
REM 사용: scripts\new-branch.bat <part> <type> <이슈번호> <설명...>
REM   예) scripts\new-branch.bat data feat 290 downloads bronze ingest

setlocal

if "%~4"=="" goto usage

set "SH="
for /f "delims=" %%i in ('where sh 2^>nul') do if not defined SH set "SH=%%i"
if not defined SH if exist "%ProgramFiles%\Git\bin\sh.exe" set "SH=%ProgramFiles%\Git\bin\sh.exe"
if not defined SH if exist "%ProgramFiles(x86)%\Git\bin\sh.exe" set "SH=%ProgramFiles(x86)%\Git\bin\sh.exe"
if not defined SH if exist "%LOCALAPPDATA%\Programs\Git\bin\sh.exe" set "SH=%LOCALAPPDATA%\Programs\Git\bin\sh.exe"
if not defined SH goto nosh

pushd "%~dp0.."
"%SH%" scripts/new-branch.sh %*
set "RC=%ERRORLEVEL%"
popd
exit /b %RC%

:usage
echo 사용: scripts\new-branch.bat ^<part^> ^<type^> ^<이슈번호^> ^<설명...^>
echo.
echo   part : frontend api data ai worker infra docs
echo   type : feat fix refactor test chore docs style config
echo.
echo   예^) scripts\new-branch.bat data feat 290 downloads bronze ingest
echo       -^> data/feat/S15P21A506-290-downloads-bronze-ingest
exit /b 2

:nosh
echo sh.exe 를 찾을 수 없습니다. Git for Windows 가 설치되어 있어야 합니다.
echo Git Bash 를 열어 다음을 실행해 주세요:
echo   sh scripts/new-branch.sh %*
exit /b 2
