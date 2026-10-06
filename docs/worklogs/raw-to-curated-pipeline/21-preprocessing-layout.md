# 전처리 디렉터리 통합 작업

## 변경 범위·계획
- 승인된 `.omx/plans/preprocessing-layout.md`에 따라 전처리 코드/테스트/실험을 `pipeline/preprocessing`에 모은다.
- 혼합 영역의 DB 전용 파일은 `pipeline/postgresql` 하위로 구분하고, 루트 DB 이관 테스트8개는 `tests/service_data_migration`에 모은다.
- 수집기·weekly 입고·MinIO 설정과 서버 배포는 유지한다. DuckDB 운영 연결/알고리즘 개선은 별도다.
- 경로/의존 경계만 수정한다. 기존 안전장치/실패 정책을 보존하며 포괄적인 import alias·오류 무시는 추가하지 않는다.
- 테스트 기준선 → 이동표 확정 → import/리소스/코드 해시 수정 → 실행/출력 회귀 검증 → 독립 검토 순으로 진행한다.

## 검증 기준선
- HEAD d71ed81의 전체 추적 파일을 로컬 임시 snapshot에 보존했다. frozen 서버 코드/증거는 수정하지 않는다.
- 기존 런타임 이미지에서172개 테스트 모듈을 수집/실행 중이다. 로컬 전용 컨테이너 `pickage-layout-before`, network none/CPU2/7680MiB, 소스 readonly, 운영 자격증명 및 Docker socket 미제공.
- PySpark 없는 Windows Python의 이전88/89 결과와 이번 격리 런타임 결과를 구분한다. DB/GPU 등 외부 조건 skip은 따로 집계한다.

## 진행·이슈·결과
- 전처리·실험·테스트와 DB 적재 영역의 파일 332개를 이동했다. [파일별 이동표](evidence/21-layout/moves.csv)를 정본으로 남긴다.
- `common/paths.py`를 기준으로 저장소 루트, Node worker, Docker mount, SQL 및 계약 해시 경로를 수정했다.
- 공통 Parquet schema/path helper를 분리하고 PostgreSQL의 기존 helper 인터페이스는 유지했다. 관련 생성 코드 해시에도 새 helper를 포함했다.
- 공통 request fixture와 전처리 unittest 실행 진입점을 추가했다. 기존 `python -m pipeline.orchestration` 명령은 얇은 위임 진입점으로 유지했다.
- 활성 README·호출 스크립트 경로를 갱신했다. 과거 실험 보고서·manifest·서버 실행 증거는 변경하지 않았다.
- 기존 수집기/weekly 배치 실행, 서버 배포, DB 접속 및 MinIO 쓰기는 하지 않았다. 검증 중 PUBLISHED 출력은 로컬 합성 S3 fixture에 대한 것이다.

### 발견한 문제와 해결
- 디렉터리 깊이에 의존하던 루트 계산, Node worker와 코드 해시의 동적 파일 목록을 새 경로에 맞췄다.
- DB 정합성 검증기의 snapshot 정책·package snapshot loader 경로도 함께 갱신했다.
- 실험 lifecycle 테스트가 실제 daemon 감시 스레드를 남겨 같은 프로세스의 후속 테스트를 exit 70으로 중단시키는 기존 문제가 있었다. 해당 lifecycle 단위 테스트에서 Thread를 mock 처리해 시험 범위를 격리했다. 운영 감시 기능은 변경하지 않았다.
- GPU 관련 NumPy/PyTorch 및 수집기 requests 누락, 폴더 안에서 실행하도록 작성된 기존 MinIO 테스트 등은 이동 전에도 발생한 별도 환경/실행 방식 제한이다.

### 검증
- 마지막 격리 회귀 시험: **527개 실행, 487개 통과, 실패/오류0, 조건부 skip40**. [집계와 skip 사유](evidence/21-layout/regression-summary.json).
- 별도 실제 로컬 Spark 검증: repository/requirements transform, package-version, dependents **21개 통과**. 첫 명령에서 존재하지 않는 모듈명2개를 잘못 지정한 수집 오류는 실제 실행된21개 결과와 구분한다.
- 최종 경계 점검에서 DB 적재를 포함한 `package_snapshot/history.py`와 resume 시험도 PostgreSQL 영역으로 옮겼다. 관련 history contract/resume/layout **19개 시험 통과**.
- Python compileall, git diff --check, 신규 README 상대 링크 검사, 새/구 CLI --help 확인 통과.
- 원래 작업트리의 기존 미추적 파일2개는 그대로 보존했다. 커밋·서버 변경은 수행하지 않았다.
- 전후 전체 단일 프로세스 시험은 기존 감시 스레드 누수와 선택 라이브러리 누락 때문에 전체 통과라고 판정하지 않는다. 정상 테스트 누락 여부는 동일 런타임의 수집 ID를 별도로 비교했다.

 전후 수집 목록 비교에서 기존 정상 테스트 ID 누락은 없었다. 이전에 import 실패하던 Curated 모듈 3개가 정상 수집되면서 20개 시험이 추가로 수집됐다.
