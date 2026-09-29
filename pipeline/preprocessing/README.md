# Raw → Curated 전처리

MinIO raw 입력을 검증하고 Curated 데이터를 만드는 코드·테스트·실험을 모은다.
원천 수집은 `pipeline/collectors`, `pipeline/weekly`, `pipeline/downloads`에,
DB 적재는 `pipeline/postgresql`에 둔다. 과거 이력 생성과 DB 적재를 함께 실행하는 명령도
`pipeline.postgresql.package_snapshot.history`에 둔다.

| 위치 | 역할 |
| --- | --- |
| `orchestration/` | 입력 고정, 단계 실행, 재개, 검증 후 게시 |
| `curated/` | 패키지·버전, 변경 목록, 주간 메타데이터 보완 |
| `snapshot/` | 스냅샷 입력과 기준 검증 |
| `downloads_interval/` | 스냅샷 구간 다운로드 집계 |
| `repository_metrics/` | 저장소 연결·지표·품질 기록 |
| `package_snapshot/` | 패키지 스냅샷 계산과 이력 지원 |
| `requirements_resolution/`, `version_dependents/` | 의존성 해석·역의존 계산 |
| `common/` | 공통 경로·Parquet 스키마 유틸 |
| `experiments/spark/`, `experiments/dependents/` | 비교 실험·측정 도구 |
| `tests/` | 위 영역에 대응하는 테스트와 공용 fixture |

저장소 루트에서 실행한다.

```sh
python -m pipeline.preprocessing.orchestration --help
python -m pipeline.preprocessing.tests --list
python -m pipeline.preprocessing.tests
python -m unittest discover -s tests/service_data_migration -t . -v
```

주간 입력·실행·재개 옵션은 [실행기 안내](orchestration/README.md)를 따른다.
기존 `python -m pipeline.orchestration`도 같은 실행기로 연결된다.
각 단계의 직접 실행 명령은 해당 README의 새 모듈 경로를 사용한다.

테스트 의존성은 각 단계의 requirements와 실험 런타임을 따른다. 전체 테스트에는
PySpark/Java/Node가 필요하며, GPU·DB·MinIO 통합 시험은 별도 환경 조건을 요구한다.
`--list`도 import 실패가 있으면 오류로 종료한다. 목록 출력만으로 시험 통과를 뜻하지 않는다.

파일 위치 이동은 생성 코드 계약 해시를 바꾼다. 이전 결과·manifest의 해시를 덮어써서
재사용하지 않는다. 과거 실험 기록과 실행 당시 경로는 `docs/worklogs`에 보존한다.
현재 일반 실행기의 repository 단계는 DuckDB가 기본이며, native/docker Spark는 명시적 비교 경로로 유지한다.
