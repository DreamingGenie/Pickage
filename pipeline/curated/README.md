# Pickage package·version Curated 전처리

## 현재 상태와 범위

이 문서는 구현 전에 합의한 데이터 처리 규칙이다.
현재 전처리 코드, Curated 파일 생성 및 PostgreSQL 적재는 아직 구현하지 않았다.

이번 작업은 승인된 Bronze 실행의 `versions_full`, `requirements` 등을 읽어
`package`·`version` 적재용 Parquet를 만들고 검증하는 범위다.
PostgreSQL 실제 적재와 `dependents_count` 계산은 별도 작업이다.
원본의 `is_release=true`인 모든 버전을 대상으로 한 뒤 아래 제외 규칙을 적용하며,
최신 ERD에는 `version.is_release` 컬럼이 없으므로 결과에는 저장하지 않는다.

## 확정: 스냅샷 시각 이후 배포된 버전 제외

- `published_at > SnapshotAt`인 버전은 정책상 데이터 오류로 간주하여
  해당 실행의 Curated `version` 결과에서 제외한다.
  업스트림에서 발생한 원인 자체를 확인했다는 뜻은 아니다.
- 비교 기준은 원본 행의 실제 `SnapshotAt` 시각이다.
  폴더의 스냅샷 날짜를 자정이나 일말로 변환한 값과 비교하지 않는다.
- 두 시각이 같은 버전은 이 규칙으로 제외하지 않는다.
  `published_at`이 NULL인 경우도 아래 규칙에 따라 포함한다.
- 제외는 패키지 목록 생성과 대표 저장소 선정 전에 적용한다.
  제외된 버전의 저장소 주소와 표시용 의존성은 결과 생성에 사용하지 않는다.
- 유효한 대상 버전이 하나도 남지 않은 패키지는 이번 실행의 `package` 결과에 넣지 않는다.
  단, 과거에 부여한 패키지 ID 매핑은 삭제하거나 재사용하지 않는다.
- Bronze 원본은 변경하지 않는다. 제외 건수와 `(Name, Version, SnapshotAt, published_at)`을
  사유 `PUBLISHED_AFTER_SNAPSHOT`과 함께 검증 결과에 기록하도록 구현한다.

## 확정: 배포일 누락 버전 유지

- `published_at`이 NULL이어도 릴리스 버전이면 Curated `version`에 포함한다.
- 배포일은 SQL `NULL`로 보존한다. 스냅샷 날짜나 다른 버전의 배포일로 채우지 않는다.
- 해당 버전도 패키지 목록 생성과 대표 저장소 선정 후보에 포함한다.
  대표 저장소의 우선순위는 배포일이 아니라 `ordinal`을 기준으로 한다.
- 배포일 누락 건수는 검증 결과에 기록하되, 누락만으로 버전이나 실행을 실패 처리하지 않는다.
- 향후 시점별 dependents 계산에서는 배포 시점을 알 수 없는 버전으로 별도 취급한다.
  Curated에 저장됐다는 이유로 특정 과거 시점에 이미 배포됐다고 가정하지 않는다.
  계산 단계의 구체적인 포함·제외 정책은 그 작업에서 정한다.

현재 합의한 릴리스·배포일 필터는 다음과 같다. NULL 배포일이 SQL 비교에서
의도치 않게 탈락하지 않도록 명시적으로 포함한다.

```sql
WHERE is_release = TRUE
  AND (published_at IS NULL OR published_at <= SnapshotAt)
```

## 확정: package_id 생성·유지

`package_id`는 패키지명을 기준으로 유지하는 식별자이며, 배포 버전이나 스냅샷의 순번이 아니다.

1. 최초 실행에서는 대상 패키지명을 중복 제거하고 정렬한 뒤 1부터 ID를 부여한다.
2. 이후 실행에서는 이전에 확정된 `name → package_id` 매핑을 읽어 기존 ID를 재사용한다.
3. 새 패키지만 이름순으로 정렬하여, 보존된 전체 매핑의 최대 ID 다음부터 부여한다.
4. 과거에 부여한 ID는 변경하거나 다른 패키지에 재사용하지 않는다.
5. 이번 입력에서 보이지 않는 패키지의 매핑도 보존한다. 나중에 다시 등장하면 같은 ID를 사용한다.

예를 들어 기존 매핑이 `b-package → 1`, `c-package → 2`라면,
다음 실행에 `a-package`가 추가돼도 기존 ID를 밀지 않고 `a-package → 3`을 부여한다.

매 실행마다 전체 이름을 다시 정렬해 ID를 재계산하지 않는다.
기존 매핑 보존이 필요하며, 이 규칙을 위해 PostgreSQL 테이블을 추가하는 것은 아니다.
매핑의 저장 경로·게시 방식과 동시 실행 방지는 구현 시 구체화한다.

## 확정: version.dependency 표시용 JSON

`requirements`의 일반·peer·optional 의존성을 구분하여 다음 형태로 저장한다.

```json
{
  "dependencies": {
    "loose-envify": "^1.1.0"
  },
  "peerDependencies": {},
  "optionalDependencies": {}
}
```

| 원본 배열 | JSON 키 |
| --- | --- |
| `Dependencies` | `dependencies` |
| `PeerDependencies` | `peerDependencies` |
| `OptionalDependencies` | `optionalDependencies` |

- 각 배열 원소의 `Name`을 객체 키로, `Requirement`를 값으로 사용한다.
- 버전과 requirements는 같은 입력 스냅샷의 `(Name, Version)`으로 연결한다.
- 범위 문자열과 이름은 원본대로 보존한다. 표시용 데이터에 semver 해석을 적용하지 않는다.
- requirements 행이 있고 해당 배열이 비어 있으면 해당 종류는 `{}`로 표현한다.
- requirements 행 자체가 없으면 `dependency`는 SQL `NULL`로 저장한다.
  이를 의존성 없음으로 간주하여 세 개의 빈 객체로 바꾸지 않는다.
- requirements 누락 때문에 정상적인 version 행을 제거하지 않는다.
- dependents 계산은 이 JSON을 입력으로 사용하지 않는다.

배열 값 자체가 NULL이거나 같은 이름에 서로 다른 Requirement가 있는 등
비정상 원본은 구현 시 실제 발생 여부부터 확인한다. 확인되지 않은 값을 빈 객체로 단정하지 않는다.

## 앞서 확정한 대표 저장소 규칙

- 제외 규칙을 통과한 릴리스 버전을 `ordinal` 내림차순으로 확인한다.
- 사용할 수 있는 GitHub·GitLab 저장소 주소를 처음 찾으면 `package.repo_url`로 선택한다.
- 없으면 이전 버전으로 계속 내려가고, 끝까지 없으면 SQL `NULL`을 사용한다.
- 주소는 `https://github.com/{owner}/{project}` 또는
  `https://gitlab.com/{group}/{subgroup...}/{project}` 형태로 정규화한다.
- GitLab 하위 그룹 경로는 유지한다. GitHub·GitLab 외 주소는 임의 변환하지 않는다.
- URL 형식 정규화는 저장소의 실제 존재·공개 여부나 리디렉션 확인과 별개다.

## 구현 시 확인할 방어 처리와 검증

- 저장소 후보 선정 시 ordinal 동률의 처리
- 정규화 후에도 ERD의 `repo_url VARCHAR(200)` 길이를 초과하는 경우의 처리
- requirements의 비정상 배열·원소·중복 키 처리

위 항목은 실제 발생 여부부터 확인하고 재현 가능한 방어 처리와 테스트로 다룬다.
충돌하는 값을 임의로 고르거나 긴 URL을 잘라 저장하지 않는다.
합의된 규칙으로 처리할 수 없는 경우는 사유를 기록하고 필요한 정책을 명확히 한다.
