# H5-A 완료 기록 독립 검토

2026-09-11 사용자 재확인 요청에 따라 독립 검토자가 작은 메타데이터·생성 코드 연결을
읽기 전용으로 검사했다. 결과는 PASS다. 대형 Parquet 내용은 별도
[실제 파일 후속 검사](historical-profile-completion-postcheck.json)에서 검증했다.

- 최초 launch → config SHA → status/job_receipt → profile_plan → profile_manifest/result의 지문과 값이 일치한다.
- status의 receipt SHA를 제외한 내용은 최종 job_receipt와 정확히 같다.
- 최초 supervisor 311328, worker 308232가 완료 기록의 PID와 일치한다.
- COMPLETE·exit_code=0·PROFILE_COMPLETE가 일치한다.
- launch와 manifest에 기록된 12개 생성 코드 지문이 현재 파일과 모두 일치한다.
- 입력 pin, 실제 실행 인자, plan의 필드와 manifest 값이 일치한다.
- count_status=NOT_COMPUTED, ready_for_load=false는 모든 단계에 보존됐다.
- 최종 프로세스 RSS 0은 종료 이후 값이다. 실행 중 최고치는 peak_rss_bytes=8,279,429,120이다.

이 결과는 H5-A 입력 측정 완료의 검토다. 전체 229개 날짜의 count 완료나 DB 적재 가능
판정을 의미하지 않는다. 원본 요구조건 전개·전체 날짜 해석을 다시 실행하지 않았다.
