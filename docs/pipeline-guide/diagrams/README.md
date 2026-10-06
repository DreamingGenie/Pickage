# 파이프라인 안내서 그림

문서에서 사용하는 독립 SVG 그림 모음입니다. 각 SVG는 외부 글꼴·스크립트·이미지에 의존하지 않으며, 브라우저에서 직접 열거나 `<img>`로 삽입할 수 있습니다. `*-mobile.svg`는 작은 화면에서 세로로 읽도록 배치한 변형입니다.

## 그림 목록

| 파일 | 설명 | 읽는 핵심 |
| --- | --- | --- |
| `overview.svg` | raw 입고부터 Curated 게시와 PostgreSQL 적재까지 | 수집 완료 → 전처리 → DB 적재의 큰 흐름 |
| `stages.svg` | 전처리 6개 단계 | snapshot, package/version, downloads, repository, package snapshot, dependents |
| `records.svg` | raw 행이 Curated 결과가 되는 변화 | 식별자와 NULL/0 처리의 의미 |
| `loading.svg` | Curated bundle의 PostgreSQL 적재 | manifest 검증 → TSV 변환 → 트랜잭션 반영 |
| `recovery.svg` | 실패·재시도·재개 상태 | 입력 대기, 실행, 완료, 실패, 차단의 관계 |
| `storage.svg` | 저장소별 역할 | raw·작업 디렉터리·Curated·PostgreSQL의 보관 경계 |

`stages.svg`는 실행 순서(좌→우, 다음 줄은 우→좌)를, `recovery.svg`는 dispatcher의 대표 상태 전이만 보여줍니다. 두 그림은 모든 예외 분기와 잠금 구현을 한 장에 표현하지 않으므로, 실제 재시도 간격·차단 조건은 실행기 계약을 기준으로 확인합니다. `storage.svg`의 49.5GB는 처리용 공간 배정 합계이며 영구 raw·Curated·DB 데이터와 별개입니다.

## 다시 생성하기

저장소 루트에서 Python 표준 라이브러리만으로 실행합니다.

```sh
python docs/pipeline-guide/diagrams/generate_diagrams.py
```

생성기는 이 디렉터리의 SVG 12개를 덮어씁니다. SVG에는 각 역할에 맞는 고유한 `title`·`desc` ID와 `aria-labelledby`가 포함되어 있어 보조 기술이 그림의 제목과 의미를 읽을 수 있습니다.
