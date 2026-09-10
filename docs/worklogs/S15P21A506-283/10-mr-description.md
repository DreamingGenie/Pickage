## 개요

동일 snapshot의 Bronze requirements와 Curated package/version을 연결해 모든 eligible source 릴리스의 일반 dependencies 선언을 보존하고 npm semver 기준 target 버전을 해석합니다. 실제 전체 계산 결과와 PARTIAL 품질 상태를 확인할 수 있도록 실행·검증 문서를 정리했습니다.

### 관련 이슈

이슈 번호 : S15P21A506-283

### 변경 영역

- [x] 데이터 수집/파이프라인 (배치·스트리밍·스케줄러)
- [ ] 데이터 저장소 (스키마·테이블·마이그레이션)
- [ ] 분석/모델 (AI, 피처, 학습·추론)
- [ ] 백엔드 API
- [ ] 프론트엔드 / 시각화
- [ ] 인프라·설정·CI
- [x] 문서

## 작업 상세 내용

- 일반 `dependencies`만 계산하고 peer/optional 선언은 계산에서 제외한 수와 사유를 보존했습니다.
- 배포일이 NULL인 source/target 릴리스는 제외하고, 미해석 선언은 품질 사유와 함께 PARTIAL 결과로 보존했습니다.
- 모든 eligible source 릴리스 버전을 유지하고 npm `semver.maxSatisfying`으로 target을 선택했습니다.
- 07 코드와 검증 증거 파일의 줄바꿈을 LF로 고정해 Windows 체크아웃이 기록된 파일 해시를 바꾸지 않도록 했습니다.
- 실제 전체 계산 결과를 기록했습니다: source 47,172,949개, 선언 289,214,123건, 해석 280,232,217건, 미해석 8,981,906건, edge 280,232,217건.
- 결과는 `PARTIAL`, `ready_for_dependents=false`이며 MinIO 게시와 08 dependents 집계·DB 적재는 수행하지 않았습니다.

## 데이터·파이프라인 영향 (해당 시)

- 스키마/테이블 변경 : 없음
- 기존 적재 데이터 재처리(backfill) 필요 여부 : 없음. 07 결과는 로컬에만 보존했습니다.
- 외부 API 호출량·키 사용 변화 : 없음. 승인된 로컬 Bronze/Curated 입력을 사용했습니다.
- 배치 주기·실행 시간 변화 : 새 배치 주기 변경은 없습니다. 실제 전체 계산은 제한된 로컬 실행에서 약 7시간 13분이 걸렸습니다.

## 실행·검증 방법

- [x] 로컬에서 실행/테스트 확인
- [x] 샘플 데이터로 결과 검증 (건수·형식 등)

최신 develop 반영 후 호스트 테스트 28개가 5.836초에 통과했습니다. Spark 테스트 3개와 실제 소규모 Spark·Node 통합 검증은 기존 증거로 확인했으며 이번에 다시 실행하지 않았습니다. 실행 환경과 전체 재현 방법은 `pipeline/requirements_resolution/README.md`에 있습니다.

```powershell
python -m unittest pipeline.requirements_resolution.test_input pipeline.requirements_resolution.test_bridge pipeline.requirements_resolution.test_build -v
```

실제 전체 계산은 finalize `result.json`과 2,520개 Parquet 산출물을 생성했고, 재부팅 후 footer 행 수 대조와 승인 입력 전체 SHA 재검증을 통과했습니다. 별도 DuckDB 2GB 전수 unique-key 검사는 메모리 한도로 중단됐으며 데이터 오류 발견을 의미하지 않습니다. 검증 로그와 실제 결과·실패 기록 사본은 `docs/worklogs/S15P21A506-283/evidence/`에 보존했습니다. 이 사본은 표준 완료 manifest를 대체하지 않습니다.

## 스크린샷 (선택)

해당 없음.

## 리뷰 요청 사항

- source·declaration·edge의 행 단위와 PARTIAL 처리, NULL 배포일 제외 정책이 08 소비 계약과 맞는지 확인해주세요.
- host 제어 프로세스의 후속 단계가 완료되지 않아 표준 `run_manifest.json`과 `_SUCCESS`가 없습니다. 실행 시작 시점의 코드·런타임 기록도 일부 누락되어, 현재 값을 원래 실행 기록으로 대체하지 않고 결과를 보존한 범위를 확인해주세요.
- 전체 결과의 raw `DependenciesProcessed` 완전성은 입력에 해당 필드가 없어 검증하지 못했습니다.

## 체크리스트

- [ ] 브랜치명이 `<part>/<type>/<이슈키>-작업내용` 규칙에 맞습니다 (AGENTS.md 4번 항목). 사용자가 이미 만든 원격 브랜치 이름을 유지하는 예외입니다.
- [x] API 키·계정 정보 등 시크릿이 커밋에 포함되지 않았습니다
- [ ] 리뷰어와 라벨을 지정했습니다
- [ ] 관련 Jira 이슈 상태를 갱신했습니다
