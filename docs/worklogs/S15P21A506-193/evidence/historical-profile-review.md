# H5-A 독립 검토 기록

범위: 고정 H1/원본의 workload 프로필과 독립 실행. 229일 resolution/count 실행은 범위 밖이다.
독립 검토 판정은 parent-death/자원/최종 영수증 테스트 통과를 조건으로 CLEAR WITH WATCH였다.

최종 조치와 근거:

- source 배열의 중복 전수 스캔 제거, H1 추가 컬럼 허용·필수 타입 검증, NULL/중복 조건 보존.
- source/lookup/package 합계와 파일의 양방향 EXCEPT ALL 대조.
- active 후보 100,000개 초과 및 후보 JSON 추정 크기 표기. 요청/응답 전체 byte의 정확한
  측정과 worker의 실행 가능 판정은 후속 표본 단계에 남긴다.
- RSS 감시는 sampled soft limit으로 표시하고 0회 관측을 미측정 NULL로 기록한다.
- DuckDB 설정과 감시 예산 교차검증, immutable job_receipt, 감시 프로세스 종료 시 worker 종료.
- Windows venv 실행용 프로세스와 실제 interpreter PID가 달랐다. base interpreter를 직접
  실행하고 기존 module path를 전달해 실제 PID/RSS/종료 대상을 맞췄다. 별도 실행에서
  Popen PID와 실제 PID 일치 및 같은 DuckDB 1.5.5 import를 확인했다.
- 실제 supervisor 강제 종료 시 SUPERVISOR_LOST 실패 기록, 정상 profile 별도 프로세스 완료,
  시간·RSS·출력 한도·오류 exit·잘못된 완료 SHA 회귀 테스트를 통과했다.

[최종 전체 회귀](historical-profile-validation.json): 177개/57.357초, 실패·오류·skip 0,
AST 30개. 이전 H4 Python 24개 파일 SHA 보존. 이 근거로 H5-A 독립 실행 조건은 충족했다.
H3의 날짜별 counts 중간 확장과 실제 worker frame 경계 해결 전 전체 229일 계산은 시작하지 않는다.
