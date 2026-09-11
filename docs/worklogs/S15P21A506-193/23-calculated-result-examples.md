# 23. 실제 계산 결과 미리보기

원본 Parquet에서 조회한 실제 값입니다. 아래 버전은 예시로 지어낸 값이 아닙니다.

## 이번 GPU 실험이 비교한 값

이번 실험은 `패키지 이름 + 버전 요구조건 + 기준일 → 선택된 버전·해석 상태`를 계산했습니다.
CPU/GPU 결과는 매번 기존 정답과 대조한 뒤 메모리에서 해제했고, 실험 보고서에는 시간·검사 결과·해시를 남겼습니다.
아래 표는 그때 일치 여부를 검증한 기존 CPU production Parquet에서 조회했습니다. GPU가 새 count 파일을 만든 것은 아닙니다.

### 최신 기준일: 2026-08-31

| 대상 패키지 | 선언된 요구조건 | 선택된 버전 | 해석 상태 |
| --- | --- | --- | --- |
| lodash | `^4.17.21` | 4.18.1 | RESOLVED |
| react | `^18.0.0` | 18.3.1 | RESOLVED |
| axios | `~1.6.0` | 1.6.8 | RESOLVED |
| semver | `^7.0.0` | 7.8.5 | RESOLVED |
| lodash | `latest` | 선택 없음 | UNSUPPORTED_TAG |
| @material-ui/lab | `^4.0.0-alpha.60` | 선택 없음 | UNMAPPED_TARGET_PACKAGE |

`RESOLVED`는 해당 기준일의 후보 중 조건을 만족하는 버전이 선택되었다는 뜻입니다.
`UNSUPPORTED_TAG`는 latest 같은 tag를 현재 해석 정책에서 처리하지 않는다는 뜻입니다.
`UNMAPPED_TARGET_PACKAGE`는 현재 입력에서 대상 패키지와 연결하지 못했다는 뜻입니다. 참조 수 0이라는 뜻은 아닙니다.

### 같은 조건도 날짜에 따라 선택 버전이 달라집니다

`react: ^18.0.0`의 실제 결과입니다. 표시한 처음/마지막 기준일을 모두 포함하며 그 사이 calendar에 있는 스냅샷에 적용합니다.

| 첫 기준일 | 마지막 기준일 | 선택된 버전 | 상태 |
| --- | --- | --- | --- |
| 2022-05-08 | 2022-06-13 | 18.1.0 | RESOLVED |
| 2022-06-20 | 2024-04-21 | 18.2.0 | RESOLVED |
| 2024-04-29 | 2026-08-31 | 18.3.1 | RESOLVED |

매일 한 행씩 저장하는 대신, 선택 버전이 같은 날짜 범위를 한 행으로 저장한 형태입니다.
`react: ^18.0.0`은 229개 기준일의 선택 결과가 위 3개 구간으로 표현됩니다.

### 원본 구간 행의 필드

```json
{
  "lookup_id": 10280592,
  "start_index": 105,
  "end_index": 229,
  "status": "RESOLVED",
  "normalized_range": ">=18.0.0 <19.0.0-0",
  "target_package_id": 9633488,
  "target_version": "18.3.1"
}
```

`lookup_id`는 패키지 이름과 요구조건 조합을 가리킵니다. `target_package_id`와 `target_version`이 선택된 대상 키입니다.
`start_index`는 시작 포함, `end_index`는 끝 제외입니다. 이 행은 calendar의 105~228번 기준일에 적용됩니다.

## 최종 목표인 dependents_count는 이런 값입니다

**이 표는 이전 32개 CPU 집계에서 이미 저장한 값입니다. 이번 GPU 실험에서 새로 집계하거나 DB에 넣은 값이 아닙니다.**

2026-08-31 기준, 성공적으로 해석한 관계만 센 PARTIAL 결과입니다. 서로 다른 source 패키지·버전의 수를 셉니다. 같은 이름의 서로 다른 source 버전은 각각 계산합니다.

| 패키지 이름 | 대상 버전 | 스냅샷 날짜 | dependents_count |
| --- | --- | --- | ---: |
| axios | 1.20.0 | 2026-08-31 | 1,132,689 |
| axios | 0.21.4 | 2026-08-31 | 330,074 |
| lodash | 4.18.1 | 2026-08-31 | 2,606,910 |
| lodash | 4.17.21 | 2026-08-31 | 288,288 |
| react | 18.3.1 | 2026-08-31 | 802,275 |
| react | 16.14.0 | 2026-08-31 | 530,228 |

예를 들어 react 18.3.1의 802,275는 이 기준일에 성공적으로 해석된 관계 중 서로 다른 source 패키지·버전 802,275개가 react 18.3.1을 직접 참조한다는 뜻입니다. 서로 다른 패키지 이름만 센 값이 아닙니다.

이전 CPU 결과 파일은 `package_id`, `version`, `snapshot_at`, `snapshot_timestamp`, `dependents_count`를 저장합니다. 표의 패키지 이름은 target_names.parquet와 package_id로 연결해 붙였습니다. 최신 날짜 파일에는 양수 count 15,500행이 들어 있습니다. 0인 버전은 이 양수 파일에서 생략되므로 파일에 없다는 사실만으로 미해석과 0을 구분할 수는 없습니다.

- [실제 count 예시 JSON](evidence/gpu-count-examples.json)
- [2026-08-31 원본 counts.parquet](../../../data/vd-pilot-a/32/run/finalizations/35ced51784d54985872d79b7a294f072/history/snapshot=2026-08-31/attempts/9e176250b59145b08f89250068ae6746/counts.parquet)

## 원본을 직접 확인할 위치

- [32개 CPU/GPU 속도 비교 보고서](22-gpu-32-package-comparison.md)
- [측정 원본 JSON](evidence/gpu-32-package-results.json)
- [요구조건·calendar·실제 구간 예시 JSON](evidence/gpu-resolver-examples.json)
- [요구조건 목록 Parquet](../../../data/vd-pilot-a/32/input/lookups.parquet)
- [react가 포함된 실제 해석 구간 Parquet](../../../data/vd-pilot-a/32/run/partitions/118/attempts/9e5e5a04f50c47eb808d4f9e8a4cc090/lookup_intervals.parquet)

Parquet는 텍스트 편집기로 바로 읽는 형식이 아닙니다. 위 미리보기와 JSON은 사람이 확인하기 쉽게 뽑은 것이고, 원본 전체 조회에는 DuckDB 같은 Parquet 조회 도구를 사용합니다.

Parquet 원본은 로컬 data 폴더에 있으며 Git 커밋에는 포함하지 않습니다. 원본을 보유하지 않은 환경에서도 위 예시 JSON과 표는 확인할 수 있습니다.
