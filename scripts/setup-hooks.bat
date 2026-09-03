@echo off
REM 저장소 git hook 활성화 (클론 후 1회만 실행)
pushd "%~dp0.."
git config core.hooksPath .githooks
if errorlevel 1 (
  echo git hook 활성화 실패
  popd
  exit /b 1
)
echo git hook 활성화 완료 ^(core.hooksPath = .githooks^)
popd
