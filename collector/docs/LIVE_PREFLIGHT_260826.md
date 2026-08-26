# Collector live preflight — 2026-08-26

> 실행 시각: 2026-08-26 KST  
> 범위: HTTPS provider만 1회 단위로 호출  
> 비밀정보 처리: API key 값과 완성 요청 URL은 출력·문서화하지 않음

## 1. 환경 점검

- `DATA_GO_BUS_API_KEY`: 설정됨
- `SEOUL_OPEN_API_KEY`: 설정됨
- `SEOUL_SUBWAY_REALTIME_KEY`: 설정됨
- `T_DATA_API_KEY`: 설정됨
- `DATA_GO_KMA_API_KEY`: 설정됨
- Kakao·TMAP 키: 비어 있음. 현재 `sources.json`의 어떤 source도 이 두 환경변수를 사용하지 않으므로 이번 점검에는 영향 없음.
- data.go 버스 키는 percent-encoded 형태이고 KMA 키는 decoded 형태였으며, 버스 키를 한 번 decode한 값과 KMA 키가 일치했다. 현재 HTTP client가 query를 URL-encode하므로 data.go 계열 환경변수에는 decoded 키를 사용하는 것이 안전하다.

## 2. 실제 호출 결과

| Source | Run ID | 요청 범위 | HTTP / body | 판정 | 해석 |
| --- | --- | --- | --- | --- | --- |
| `kma-asos-hourly` | `c6f61fb80732414d806dced89421014c` | 2026-08-25 00~01시, 서울 ASOS 108 | `403`, code `30`, `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | `UNUSABLE` | `15057210` 서비스 활용신청·활성 키 상태 확인 필요 |
| `kma-ultra-short-nowcast` | `a30d03dc827e4c908186f68d9369f1b9` | 2026-08-25 23:00, grid `60,127` | `403`, code `30`, `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | `UNUSABLE` | `15084084` 서비스 활용신청·활성 키 상태 확인 필요 |
| `tdata-bis-history` | `718c23fcbc3749b3a28c19a123df3ea6` | `20260824`, route `100100001` | `200`, 2-byte JSON `[]` | `UNUSABLE` | 인증·endpoint는 통과했지만 행과 성공 envelope가 없어 계약 검증 불가 |
| `tdata-bis-history` | `ad8c839bfd3c414ebdb236e3d0310169` | 공식 샘플 `20211219`, route `100100012` | `200`, 2-byte JSON `[]` | `UNUSABLE` | 공식 샘플도 현재는 빈 배열. 실제 조회 가능 기준일 확인 필요 |
| `tdata-road-hourly` | `b1d609ba47614e4d99c8fe23f63baec2` | `20260824` | `404`, 80-byte gateway JSON | `UNUSABLE` | 현재 키의 `T-DATA-1015` 활용신청·권한 상태 확인 필요 |

`COMPLETE`는 요청 실행이 종료됐다는 뜻이고 `UNUSABLE`은 요청 목적에 쓸 데이터 계약을 확보하지 못했다는 뜻이다. 위 실행은 모두 report와 quota ledger에 기록됐다.

## 3. 공식 계약과 설정 반영

- [data.go.kr 15084084](https://www.data.go.kr/data/15084084/openapi.do)의 개발계정 트래픽 10,000회를 초단기실황·초단기예보의 하나의 보수적 공유 pool로 등록했다.
- [data.go.kr 오류코드 안내](https://www.data.go.kr/tcs/dss/selectErrCodePopupView.do)에서 code `30`은 등록되지 않은 서비스키이며, 키 정확성과 해당 서비스 활용신청 완료 여부를 확인해야 한다.
- [T-DATA 1068](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1068)과 [T-DATA 1015](https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1015)는 데이터셋별 활용신청 상태를 확인해야 한다.

## 4. 다음 재검증 조건

1. data.go.kr `15057210`, `15084084` 활용신청 현황에서 사용 중인 키가 승인·활성 상태인지 확인한다.
2. `collector/.env.local`에는 data.go.kr의 decoded 키를 넣는다. 이미 encoded된 키는 collector가 다시 encode하므로 사용하지 않는다.
3. T-DATA 신청관리에서 `T-DATA-1068`, `T-DATA-1015`가 모두 승인됐는지 확인한다.
4. T-DATA-1068 포털에서 실제 조회 가능한 최초·최종 `stdrDe` 또는 최신 배포 기준일을 확인한다.
5. 승인 상태가 반영된 뒤 각 source를 `--count 1 --purpose CONTRACT_SMOKE`로 다시 실행하고, 성공 전에는 장기 polling을 시작하지 않는다.

