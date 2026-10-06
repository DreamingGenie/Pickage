# 07 push 전 로컬 준비

2026-09-10 사용자 요청: "작업 푸시 전까지만 진행해". 최신 develop 반영, 문서 정리, 검증, 07 전용 커밋까지 수행하고 push/MR 생성은 수행하지 않는다.

## 변경 범위와 계획

- 기준 이슈: 기존 `S15P21A506-283`. Jira connector 도구가 없고 브라우저 JQL 검색은 로그아웃 상태에서 접근이 거부됐다. 사용자가 직접 접근에 이의를 제기해 추가 접근을 중단했다. 새 이슈 생성, 댓글·상태 갱신은 하지 않았다. 이후 작업은 사용자 요청대로 로컬 준비에 한정한다.
- `pipeline/requirements_resolution/`와 `docs/worklogs/S15P21A506-283/`만 이번 커밋에 포함한다. 04/05/288, 공통 모듈, 팀 AGENTS.md는 수정하지 않는다.
- 원격 develop `fa71c5a`를 확인하고 기존 07 HEAD `fb2f838`에서 fast-forward한다. 원격 07 브랜치는 기존 이름을 유지하며 강제 push나 새 브랜치 생성은 필요 없다.
- 기존 07 파일 28개를 `data/requirements-resolution/prepush-20260910/before/`에 백업하고 SHA 목록을 보존했다. 실제 계산 산출물은 변경하거나 다시 계산하지 않는다.
- 오래된 현재형 실행 설명을 갱신하고, PARTIAL·초기 실행 기록 누락·추가 검증 OOM을 코드 검증과 구분해 문서화한다.
- 최신 기반에서 호스트 테스트와 필요한 정적 검사를 실행한다. 기존 Spark/Node 통합 증거를 점검하고 공통 코드 변경의 영향이 있는지 검토한다.
- 최신 MR 템플릿의 한국어 본문을 로컬 파일로 준비한다. 일반 MR을 전제로 하되 MR 생성·리뷰어/라벨 지정은 이번 범위 밖이다.
- 파일 목록을 명시하여 stage하고 시크릿·변경 범위·diff를 확인한 후 규칙에 맞는 07 커밋을 만든다.

## 실제 진행과 검증 결과

- fast-forward 완료: `fb2f838 → fa71c5a`. 최신 팀 AGENTS.md가 07 worktree에도 들어왔다. 07 파일 28개는 그대로 보존됐고 기존 추적 파일의 로컬 변경은 없다.
- 재사용 코드 중 `pipeline/minio/ingest_raw.py`의 환경 선택 부분이 develop에서 변경됐다. 이번 커밋에서 수정하지 않으며, 과거 실행의 코드 hash를 현재 hash로 덮어쓰지 않는다.
- 최신 develop 기준 호스트 테스트 28개가 5.836초에 통과했다(프로세스 전체 6.344초). 입력·Node bridge·lifecycle 검사이며 Spark 호출은 lifecycle 단위 테스트에서 대역으로 격리한다.
- Python 17개 파일 AST 파싱과 Node worker 1개 구문 검사, 코드 trailing whitespace 검사가 통과했다.
- `README.md`를 제외한 기존 07 production/test 파일은 백업 SHA와 모두 일치한다. 이번 준비에서 동작 코드를 변경하지 않았다.
- 기존 실제 Spark 테스트 3개와 소규모 Spark→Node→Spark lifecycle 통합 `PASSED` 기록을 확인했다. 이번에는 해당 작업을 다시 실행하지 않았으며 최신 기반의 호스트 테스트 결과와 구분한다. 공통 `ingest_raw.py` 변경은 client 환경 선택 부분이고 07이 호출하는 기존 입력·변환 함수는 변경되지 않았다.
- 독립 코드 검토에서 커밋을 차단할 정확성·데이터 손상·시크릿 노출·최신 develop 호환 문제를 찾지 못했다. 사용하지 않는 함수의 변경도 전체 code fingerprint를 바꾸는 범위는 운영 비용 WATCH로 남겼으며 이번에 정책을 변경하지 않았다.
- 실제 테스트 로그와 결과는 [prepush-validation.json](evidence/prepush-validation.json), 실제 전체 prepare/finalize 요약과 후속 검증 실패 기록은 같은 `evidence/` 폴더에 사본으로 보존한다. 결과 사본은 원본 바이트와 일치하며 표준 완료 manifest를 대신하지 않는다.
- 일반 MR의 한국어 본문을 [10-mr-description.md](10-mr-description.md)에 준비했다. 이전부터 존재한 원격 브랜치 이름을 유지하며, 최신 템플릿의 브랜치명 규칙 체크박스에는 예외를 명시한다. 리뷰어·라벨·Jira 상태 갱신은 수행하지 않았다.
- 커밋은 `core.hooksPath=.githooks`를 해당 명령에만 지정해 팀 commit-msg 훅을 적용한다. 다른 worktree의 Git 설정은 변경하지 않는다.
- stage 과정에서 Windows 자동 줄바꿈 변환 경고를 확인했다. 07 폴더 내부 `.gitattributes`로 실행 코드·검증 helper·해시가 기록된 evidence 파일의 LF를 고정했다. 공통 속성 파일이나 다른 파이프라인을 변경하지 않고 현재 코드 바이트도 유지한다.
- 이번 준비 파일은 07 소유 범위 37개다. stage 목록, 최종 변경 범위와 커밋·원격 미변경 확인 결과는 로컬 `data/requirements-resolution/prepush-20260910/`의 검사 기록에 보존한다. push와 MR 생성은 수행하지 않는다.
