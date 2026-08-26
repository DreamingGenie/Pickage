@echo off
REM ============================================================================
REM  실시간 수집기 백그라운드 감시 루프 (Windows, 관리자 승격 불필요)
REM
REM  Windows 작업 스케줄러(schtasks / Register-ScheduledTask)에 등록하려면
REM  관리자 승격이 필요하다. 승격을 쓸 수 없는 환경에서는 이 스크립트를
REM  시작프로그램 폴더에서 띄워 같은 효과를 낸다.
REM
REM    - 로그온 시 자동 시작   : 시작프로그램 폴더의 JR-Collector.vbs
REM    - 비정상 종료 시 재시작 : 아래 루프가 60초 뒤 다시 띄운다
REM    - 콘솔 창 숨김          : start_collector.vbs 가 창 없이 실행한다
REM
REM  단일 프로세스 원칙: 이 루프를 두 개 이상 띄우면 안 된다. quota 원장에
REM  파일 락이 없어 카운터가 깨지고 일일 상한을 넘겨 호출하게 된다.
REM
REM  정지 방법 (둘 다 해야 완전히 멈춘다)
REM    1) data\STOP_COLLECTOR 파일을 만든다  ->  루프가 재시작하지 않는다
REM    2) taskkill /F /IM python.exe          ->  실행 중인 수집기를 끝낸다
REM  다시 시작할 때는 STOP_COLLECTOR 파일을 지운다.
REM ============================================================================

cd /d "%~dp0..\.."
set STOPFILE=%CD%\data\STOP_COLLECTOR

if exist "%STOPFILE%" (
    echo [%DATE% %TIME%] STOP_COLLECTOR 가 있어 시작하지 않습니다.
    exit /b 0
)

:loop
REM run_scheduler 는 대상 단위로 예외를 흡수하므로 스스로 죽는 일은 드물다.
REM 그래도 파이썬 프로세스 자체가 사라지는 경우(강제 종료 등)를 위해 되살린다.
python -m collector.run_scheduler

if exist "%STOPFILE%" goto end

REM timeout 은 입력이 리다이렉트된 숨김 창에서 실패한다. ping 을 sleep 으로 쓴다.
ping -n 61 127.0.0.1 >nul
goto loop

:end
echo [%DATE% %TIME%] STOP_COLLECTOR 를 확인해 루프를 종료합니다.
exit /b 0
