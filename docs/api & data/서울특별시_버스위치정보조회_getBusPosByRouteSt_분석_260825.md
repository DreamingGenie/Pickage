# 서울특별시 버스위치정보조회 서비스 (`getBusPosByRouteSt`)

> 조사·검증 기준: 2026-08-25 KST  
> 대상 데이터셋: 공공데이터포털 15000332  
> 문서 범위: 서비스 전체 5개 상세기능을 확인하되, 요청·응답 명세는 포털에서 선택된 `getBusPosByRouteSt`를 기준으로 작성  
> 검증 범위: 최신 공공데이터포털 명세, 2023-05-30 제공기관 활용가이드, 현재 무키·오류키 호출, 저장소의 2026-08-21~22 정상 호출 증거  
> 검증 한계: 이번 조사에서는 운영키를 읽거나 노출하지 않았으므로, **현재 시점의 정상 JSON 응답·운영계정 잔여 한도·전체 노선 coverage는 직접 재검증하지 않음**

## 0. 조사 근거와 판정 기준

### 공식 자료

- [공공데이터포털 15000332 — 서울특별시 버스위치정보조회 서비스](https://www.data.go.kr/data/15000332/openapi.do)
- [공공데이터포털 카탈로그 JSON](https://www.data.go.kr/catalog/15000332/openapi.json)
- [제공기관 활용가이드 DOCX, 2023-05-30](https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003552007&fileDetailSn=1)
- [서울 열린데이터광장 OA-1093 활용가이드 게시물](https://data.seoul.go.kr/dataList/OA-1093/F/1/datasetView.do)
- [공공누리 제1유형 이용조건](https://www.kogl.or.kr/info/licenseType1.do)

### 프로젝트 내부 실측·계약 근거

- [API 상세기능·호출량 확인](../history/transit_journey_handoff_FINAL_v3/docs/03_API_SPIKE_CHECKLIST.md)
- [노선 753 정상 호출·중복·상태전이 결정 기록](../history/transit_journey_handoff_FINAL_v3/docs/05_DECISION_LOG.md)
- [수집기 응답시간 실측](../history/journey_reliability_docs_v2/evidence/phase2/EV2-01_COLLECTOR_TIMESTAMP/README.md)
- [응답시간 통계 원본](../history/journey_reliability_docs_v2/evidence/phase2/EV2-01_COLLECTOR_TIMESTAMP/derived/latency_summary.json)
- [01A 목표 구간 수집 결과](../history/journey_reliability_docs_v2/evidence/phase2/BUS_01A_TARGET_LEG/README.md)
- [실제 관측값·잔차 생성 계약](../history/journey_reliability_docs_v2/docs/40_data_probability/41_OBSERVATION_ACTUAL_RESIDUAL.md)
- [ID 매핑 근거](../history/journey_reliability_docs_v2/baseline/phase0/docs/data-contract/ID_MAPPING.md)

### 표기 원칙

- **공식**: 최신 포털 또는 제공기관 활용가이드에 명시된 내용
- **관측**: 실제 API 응답이나 저장된 프로젝트 증거에서 확인한 내용이며 SLA가 아님
- **설계안**: Journey Reliability 프로젝트에서 적용할 수집·저장·전처리 제안
- 최신 포털과 2023년 활용가이드가 다르면 최신 포털을 우선하되, 차이를 데이터 품질 항목에 남긴다.
- 공식 문서에서 확인되지 않은 값은 추정하지 않고 **미공개**, **미확인** 또는 **실측 필요**로 표시한다.

## 1. 개요

- 제공기관: **서울특별시**
  - 관리부서: 미래첨단교통과
  - 연락처: 공공데이터포털 최신 카탈로그 기준 `02-2133-4969`
- 공식 문서: [공공데이터포털 API 상세](https://www.data.go.kr/data/15000332/openapi.do)
- 데이터 분류: **교통및물류 - 도로 / Open API / REST**
- 데이터 유형: **실시간**
  - 서울 시내 운행 버스의 호출 시점 위치·운행상태 스냅샷이다.
  - 정적 노선 기준정보, 운행시각표, 과거 운행이력 또는 확정 도착 이벤트 API가 아니다.
- 프로젝트 활용 목적:
  - 현재 운행 중인 차량의 노선·구간순번·위치·정류장 도착상태·혼잡도 후보를 현재 상태 feature로 사용
  - 반복 관측으로 정류장 도착 후보, 구간 운행시간, 정차시간, 실제 배차간격을 추정
  - 버스도착정보 API의 Prediction과 결합해 예측 오차 및 residual을 생성
  - 현재 출발 분석 및 이동 중 재예측에서 실시간 운행상태를 보정 변수로 사용
- 적용 기능:
  - [x] 현재 출발 시 도착확률 — **실시간 상태 보정용 보조 입력으로 조건부 적용**
  - [ ] 목표 도착시각 기준 출발 추천 — 이 API만으로는 불가하며 장기 이력, 노선·정류장 topology, 시간표, 환승·보행 분포가 추가로 필요

> 이 API는 ETA나 확정 도착시각을 직접 제공하지 않는다. `dataTm`은 차량별 제공시각이고, `stopFlag=1`은 해당 관측에서 정류장 도착 상태임을 뜻할 뿐 정확한 도착 이벤트 시각이 아니다.

## 2. 제공 범위

- 지역 범위: **서울 시내 운행 버스**
  - 공식 설명은 “서울 시내 운행 버스”까지이며, 행정구역 경계·서울 진출입 구간·노선별 포함률은 별도 공개하지 않는다.
  - 카탈로그의 공간·시간 범위 필드는 `-`로 표시돼 있다.
- 노선·운영기관 범위:
  - 정확한 운수회사 목록, 전체 노선 목록, 제외 노선은 공식 명세에 없다.
  - 노선 ID 또는 차량 ID를 입력하는 다음 5개 상세기능이 제공된다.

| 상세기능 | Endpoint suffix | 조회 범위 | 핵심 입력 |
| --- | --- | --- | --- |
| `getBusPosByRouteSt` | `/buspos/getBusPosByRouteSt` | 노선 내 시작~종료 정류장 순번 구간 | `busRouteId`, `startOrd`, `endOrd` |
| `getBusPosByRtid` | `/buspos/getBusPosByRtid` | 노선 전체 차량 | `busRouteId` |
| `getBusPosByVehId` | `/buspos/getBusPosByVehId` | 차량 1대 | `vehId` |
| `getLowBusPosByRouteSt` | `/buspos/getLowBusPosByRouteSt` | 구간 내 저상버스 | `busRouteId`, `startOrd`, `endOrd` |
| `getLowBusPosByRtid` | `/buspos/getLowBusPosByRtid` | 노선 전체 저상버스 | `busRouteId` |

  - 이 문서는 첫 번째 상세기능인 `getBusPosByRouteSt`의 요청·응답 계약을 중심으로 한다.
  - 전 노선 차량 상태가 필요하면 `getBusPosByRtid`가 더 직접적이지만, 추가 필드의 단위와 현재 스키마를 별도로 검증해야 한다.
- 제공 기간:
  - API 등록일: 2011-12-03
  - API는 현재 스냅샷만 반환하며 날짜·시각 범위 조회 파라미터가 없다.
- 과거 이력 제공 여부: **공식 API로는 제공되지 않음**
  - 과거 조회 endpoint나 archive 다운로드가 문서화돼 있지 않다.
  - 모델 학습용 이력은 프로젝트가 호출 시점부터 직접 적재해야 한다.
- 데이터 갱신 주기:
  - **[공식·2023 활용가이드] 5초마다 갱신**
  - 최신 포털에는 갱신 SLA 또는 차량별 최대 stale 허용시간이 없다.
  - 5초보다 빠르게 호출해도 동일 `vehId + dataTm`이 반복될 수 있다.
- 실제 데이터 지연시간:
  - **[공식] 미공개** — `dataTm`의 생성 지점, 제공기관 내부 처리시간, 최대 지연 SLA가 없다.
  - **[관측]** 2026-08-22 버스 147 단일 차량 스냅샷은 수집시각보다 약 12.3초 이전, 01A 단일 차량은 약 16.5초 이전이었다.
  - **[관측]** 2026-08-21 노선 753 한 번의 응답에 포함된 13대는 차량별 `dataTm`이 수집시각보다 약 **4.9~895.9초 이전**이었다.
  - 위 차이는 네트워크 응답시간이 아니라 `received_at - dataTm`으로 본 **피드 나이(feed age)**이며, 제공기관·수집기 시계 오차가 보정되지 않아 전달 지연 SLA로 해석할 수 없다.

## 3. 인증 및 호출 제한

- 인증 방식:
  - 공공데이터포털에서 발급받은 일반 인증키를 query parameter `serviceKey`로 전달한다.
  - OAuth 또는 Header 인증 방식이 아니다.
  - 최신 포털은 `serviceKey`, 2023 활용가이드 일부 표기는 `ServiceKey`로 대소문자가 다르므로 최신 포털 표기인 `serviceKey`를 사용한다.
- API 키 발급처: [공공데이터포털 활용신청](https://www.data.go.kr/data/15000332/openapi.do)
- 기본 일일 호출 한도: **개발계정 1,000회/일**
  - 포털은 선택된 상세기능에 `개발계정 1,000`을 표시하고, 오류코드 `22`를 일일 허용량 초과로 정의한다.
  - 기존 프로젝트 계정에서는 상세기능별 1,000회로 관측됐으나, 발급된 키의 실제 quota 화면을 운영 전 다시 확인한다.
- 초당 호출 한도: **최대 30 TPS**
  - 2023 제공기관 활용가이드의 상세기능별 최대값이다.
  - 최신 포털은 숫자를 재표시하지 않고 초당 한도 초과 오류 `23`만 안내하므로, 현재 계정에 보장된 처리량이나 SLA로 간주하지 않는다.
- 호출량 증액 가능 여부: **가능**
  - 운영계정 활용신청은 자동승인으로 표시되며, 활용사례 등록 후 운영 트래픽 증액을 요청할 수 있다.
  - 승인 트래픽, 처리기간, 보장 TPS는 미공개다.
- 이용요금: **무료**
- 이용약관·라이선스:
  - 공공데이터포털 표시: **공공저작물 출처표시 제1유형**, 제3자 권리 포함
  - 출처를 표시해야 하며 제3자 권리가 포함된 항목은 별도 권리 확인이 필요하다.
  - API 키는 저장소, 브라우저, 로그, 분석 문서에 노출하지 않는다.
  - 호출량·지속 제공·정확성 SLA는 라이선스와 별개의 운영 조건이다.

## 4. 요청 방법

- HTTP Method: `GET`
- Endpoint:

```text
http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt
```

- 응답 형식: **JSON / XML**
  - 선택 파라미터 `resultType=json|xml`로 지정한다.
  - 운영 파서는 형식을 명시해 호출하고, `Content-Type`도 함께 검증한다.
- 필수 파라미터:

| 파라미터 | 설명 | 예시 | 필수 여부 |
| --- | --- | --- | --- |
| `serviceKey` | 공공데이터포털 인증키. URL encoding 후 전달 | `{URL_ENCODED_SERVICE_KEY}` | 필수 |
| `busRouteId` | 버스 노선 ID | `100100118` (753번 프로젝트 관측값) | 필수 |
| `startOrd` | 조회 시작 정류장 순번 | `1` | 필수 |
| `endOrd` | 조회 종료 정류장 순번 | `110` | 필수 |
| `resultType` | 응답 형식 | `json` 또는 `xml` | 선택 |

> 최신 포털 표에는 `startOrd`·`endOrd` 길이가 2로 표시되지만, 프로젝트의 정상 응답 증거에서는 `endOrd=110`이 성공했다. 두 자리 문자열로 제한하지 말고 노선 정류장 순번 정수로 검증한다.

### 요청 예시

```http
GET http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt?serviceKey={URL_ENCODED_SERVICE_KEY}&busRouteId=100100118&startOrd=1&endOrd=110&resultType=json
```

PowerShell에서 키를 URL encoding하면서 호출하는 예시는 다음과 같다.

```powershell
$serviceKey = '<MASKED_DATA_GO_SERVICE_KEY>'
curl.exe --get --silent --show-error `
  --data-urlencode "serviceKey=$serviceKey" `
  --data-urlencode 'busRouteId=100100118' `
  --data-urlencode 'startOrd=1' `
  --data-urlencode 'endOrd=110' `
  --data-urlencode 'resultType=json' `
  'http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt'
```

> 공식 endpoint는 현재 `HTTP`만 안내한다. 2026-08-25 이 환경에서 `HTTPS:443`은 연결되지 않았다. query string에 인증키가 포함되므로 브라우저가 직접 호출하지 말고, backend 수집기에서만 호출하며 운영 배포 전에 전송구간 보안·프록시 정책을 별도 승인해야 한다.

## 5. 응답 데이터

XML 정상 응답은 `ServiceResult > msgHeader + msgBody > itemList[]` 구조다. XML leaf 값은 모두 text로 관측됐으므로, 원문을 먼저 저장한 뒤 명시적으로 type casting한다. 공공데이터포털은 JSON도 지원한다고 안내하지만, 이 조사에서는 운영키로 성공한 JSON 원문을 확보하지 않았다.

| 필드 | 의미 | 원문 타입 / 권장 타입 | 관측 예시 | 저장 여부 |
| --- | --- | --- | --- | --- |
| `ServiceResult.comMsgHeader` | 공통 메시지 헤더. 정상 XML에서는 빈 요소로 관측 | object/null | `<comMsgHeader/>` | 원문만 |
| `msgHeader.headerCd` | 제공기관 업무 결과코드. `0`이면 성공 | string / string | `0` | 예 |
| `msgHeader.headerMsg` | 제공기관 업무 결과메시지 | string | `정상적으로 처리되었습니다.` | 예 |
| `msgHeader.itemCount` | 제공기관 응답 건수 표기 | string / integer | `0` | 예, 단 신뢰 금지 |
| `msgBody.itemList[]` | 차량 위치 레코드 목록 | array | 13개 차량 | 예 |
| `busType` | 버스 유형. 최신 포털 `0` 일반, `1` 저상; 2023 가이드는 `2` 굴절도 명시 | string / smallint | `1` | 예 |
| `congetion` | 혼잡도. 계약상 오탈자 그대로 사용. `0` 정보없음, `3` 여유, `4` 보통, `5` 혼잡, `6` 매우혼잡 | string / smallint | `3` | 예 |
| `dataTm` | 차량별 제공시각 | string / local datetime + raw | `20260822123922` | 예 |
| `isFullFlag` | 만차 여부 후보. 실제 응답에는 있으나 현재 해당 상세기능 출력표에는 없음 | string / nullable boolean | `0` | 원문 저장, feature 사용 보류 |
| `lastStnId` | 종점 정류장 ID | string | `122000165` | 예 |
| `plainNo` | 차량번호판 표시값 | string | `서울70사6876` | 예, 식별키로는 사용 금지 |
| `posX` | GRS80 맵매칭 X 좌표 | string / decimal | `203075.629...` | 예 |
| `posY` | GRS80 맵매칭 Y 좌표 | string / decimal | `445075.612...` | 예 |
| `routeId` | 노선 ID | string | `100100026` | 예 |
| `sectDist` | 구간 offset 거리. 공식 단위 표기와 표본 크기가 불일치 | string / decimal + unit flag | `143` | 예, 단위 검증 전 원값 유지 |
| `sectOrd` | 현재 구간 순번 | string / integer | `47` | 예 |
| `sectionId` | 구간 ID | string | `122600644` | 예 |
| `stopFlag` | `1` 정류장 도착 상태, `0` 운행 중 | string / smallint | `0` | 예 |
| `tmX` | WGS84 경도 | string / decimal | `127.034789` | 예 |
| `tmY` | WGS84 위도 | string / decimal | `37.505091` | 예 |
| `vehId` | 버스 차량 ID | string | `110052281` | 예 |

### 응답 예시

아래 성공 데이터는 **검증된 XML 성공 응답의 필드와 값을 JSON으로 전사한 예시**다. 공식 지원 형식에 JSON이 포함되지만, exact JSON success envelope는 운영키로 한 번 더 캡처해 확정해야 한다.

```json
{
  "ServiceResult": {
    "comMsgHeader": null,
    "msgHeader": {
      "headerCd": "0",
      "headerMsg": "정상적으로 처리되었습니다.",
      "itemCount": "0"
    },
    "msgBody": {
      "itemList": [
        {
          "busType": "1",
          "congetion": "3",
          "dataTm": "20260822123922",
          "isFullFlag": "0",
          "lastStnId": "122000165",
          "plainNo": "서울70사6876",
          "posX": "203075.629...",
          "posY": "445075.612...",
          "routeId": "100100026",
          "sectDist": "143",
          "sectOrd": "47",
          "sectionId": "122600644",
          "stopFlag": "0",
          "tmX": "127.034789",
          "tmY": "37.505091",
          "vehId": "110052281"
        }
      ]
    }
  }
}
```

검증된 성공 XML 원문의 핵심 구조는 다음과 같다. 이 표본에서는 `itemCount=0`인데 실제 `itemList`는 1개였으므로 `itemCount`를 신뢰하지 않고 배열 원소를 직접 센다.

```xml
<ServiceResult>
  <comMsgHeader/>
  <msgHeader>
    <headerCd>0</headerCd>
    <headerMsg>정상적으로 처리되었습니다.</headerMsg>
    <itemCount>0</itemCount>
  </msgHeader>
  <msgBody>
    <itemList>
      <busType>1</busType>
      <congetion>3</congetion>
      <dataTm>20260822123922</dataTm>
      <isFullFlag>0</isFullFlag>
      <lastStnId>122000165</lastStnId>
      <plainNo>서울70사6876</plainNo>
      <routeId>100100026</routeId>
      <sectDist>143</sectDist>
      <sectOrd>47</sectOrd>
      <sectionId>122600644</sectionId>
      <stopFlag>0</stopFlag>
      <tmX>127.034789</tmX>
      <tmY>37.505091</tmY>
      <vehId>110052281</vehId>
    </itemList>
  </msgBody>
</ServiceResult>
```

현재 무키 호출에서 직접 확인한 gateway JSON 오류 응답은 다음과 같다. 비정상 HTTP 응답은 위 성공 envelope가 아니다.

```json
{
  "error": "Unauthorized",
  "message": "serviceKey 파라미터가 필요합니다.",
  "status": 401
}
```

처리 순서는 반드시 `HTTP status/Content-Type` 확인 → 2xx이면 `msgHeader.headerCd == "0"` 확인 → `itemList` 정규화 순으로 한다.

## 6. 시간 데이터 해석

- 제공기관 데이터 생성시각 필드: **`dataTm`**
  - 공식 의미는 `제공시간`이다.
  - 관측 표본에서 차량별 `dataTm`은 14자리 `YYYYMMDDHHMMSS` 형태였다. 차량 간 값이 다른 응답도 있었지만, 항상 서로 달라야 하는 계약은 아니다.
  - 최신 포털의 필드 길이 22 표기와 실제 14자리 값이 다르므로 원문 문자열을 보존한다.
- 예측시각 또는 실제시각 여부:
  - **예측시각이 아니다.** 다음 정류장 ETA나 목적지 ETA가 아니다.
  - **확정 실제 도착시각도 아니다.** 차량 위치·상태를 제공한 관측시각이다.
  - 동일 차량의 `stopFlag: 0 → 1` 전이는 실제 도착의 후보 구간을 만들 수 있지만, 정확한 한 시점으로 단정하지 않는다.
- 시간대:
  - 공식 문서에 timezone offset이 없다.
  - 프로젝트에서는 서울 데이터라는 근거로 `Asia/Seoul`을 **명시적 가정**해 parsing하되, `dataTm_raw`, `timezone_assumption`, `received_at_utc`를 함께 저장한다.
- 자정 이후 운행일 처리 방식: **공식 미공개**
  - `dataTm`의 달력 날짜를 곧바로 서비스 운행일로 사용하지 않는다.
  - 심야 연속운행·막차 처리는 시간표/노선 기준정보와 결합해 별도 `service_date` 규칙을 정의한다.
- 수집시각과 제공시각의 차이:
  - `source_age = received_at - parsed(dataTm)`를 차량별로 계산한다.
  - 이 값은 제공기관 내부 지연, 차량별 송신 지연, 네트워크 지연, 양측 시계 오차가 섞인 값이다.
  - 프로젝트의 180회 실제 성공 호출에서 HTTP 수집기 왕복시간은 p50 약 43ms, p95 약 101ms, p99 약 381ms였지만 `dataTm` 자체의 지연 SLA는 계산하지 못했다.
  - 한 번의 호출에 포함된 차량별 `dataTm`이 크게 달랐으므로 호출 수신시각을 모든 차량의 원천시각으로 덮어쓰지 않는다.
- 시간표 기준인지 실제 관측값인지:
  - 시간표 계획값이 아니라 **실시간 운행상태 관측 스냅샷**이다.
  - 다만 센서 원시시각인지 TOPIS 가공·게시시각인지는 공식 문서에 정의돼 있지 않다.

> 시간값 구분: 이 상세기능에는 **계획 도착시간 없음 / 예측 도착시간 없음 / 확정 실제 도착 이벤트시각 없음**이다. `dataTm`은 차량별 상태 제공시각이고, `stopFlag=1`은 해당 스냅샷의 도착 상태다. 0→1 전이로 생성한 도착시각은 반드시 `arrival_observation_interval` 같은 **추정 관측구간**으로 저장한다.

## 7. 식별자

- 노선 식별자:
  - 요청: `busRouteId`
  - 응답: `routeId`
  - 프로젝트의 제한된 실호출에서는 두 값과 버스도착정보 API의 노선 ID를 직접 join할 수 있었다.
- 차량·열차 식별자:
  - 차량 식별자: `vehId`
  - 표시용 번호판: `plainNo`
  - 노선 753 지속 수집에서 버스도착정보 API와 위치정보 API의 `vehId` join이 2,026/2,026건 성공했지만, 단일 노선·짧은 관측 결과이므로 전 노선 영구 계약으로 승격하지 않는다.
- 정류장·역 식별자:
  - `sectionId`: 현재 구간 ID
  - `lastStnId`: 종점 정류장 ID
  - `sectOrd`: 노선 내 구간 순번
  - 이 상세기능에는 현재 정류장 ID나 `nextStId`가 없다. `sectionId`를 정류장 ID로 사용하면 안 된다.
- 방향 식별 방식: **직접 방향 필드 없음**
  - `startOrd`/`endOrd`, `sectOrd`의 진행, 노선 topology, 회차지 정보를 조합해야 한다.
  - 상·하행 또는 기점·종점 방향을 `routeId`만으로 추정하지 않는다.
- 다른 API와 ID가 동일한지:
  - 공식 문서는 cross-API 동일성·안정성을 보장하지 않는다.
  - 프로젝트 실측에서는 `routeId/busRouteId`와 `vehId`의 위치↔도착 API 직접 join이 제한된 범위에서 성공했다.
  - `sectionId`, `lastStnId`, 도착정보의 `arsId`, 노선 정류장 ID 간 완전한 대응은 아직 확인되지 않았다.
- 내부 표준 ID 매핑 필요 여부: **필요**
  - `internal_route_id ↔ busRouteId/routeId`
  - `internal_vehicle_observation_id ↔ routeId + vehId + dataTm`
  - `internal_segment_id ↔ sectionId + sectOrd + direction/version`
  - `internal_stop_id ↔ 노선정류장 기준정보` crosswalk를 versioned mapping으로 관리한다.

## 8. 수집 계획

- 수집 방식: **주기적 폴링**
  - backend 수집기가 API를 한 번 호출하고 여러 사용자 요청에 cache/fan-out한다.
  - 브라우저나 사용자 기기에서 API를 직접 호출하지 않는다.
- 수집 주기:
  - 제공기관 갱신주기는 5초지만 개발계정 1,000회/일로 24시간 5초 폴링은 불가능하다.
  - 단일 상세기능·단일 노선을 24시간 수집할 때 이론상 최소 평균 주기는 `86,400 / 1,000 = 86.4초`다.
  - **개발 기본안:** 노선당 120초 폴링이면 720회/일로, 재시도·수동 검증용 280회를 남긴다.
  - **단기 실험안:** 20~30초 폴링은 목표 구간·시간창에만 제한한다. 30초를 하루 종일 유지하면 2,880회로 기본 한도를 초과한다.
  - **증액 후 운영안:** 최소 5초 이상에서 route 수, 허용량, 실제 중복률을 반영해 결정한다.
  - 다중 노선은 `N × 86,400 / interval_seconds ≤ 일일 quota`를 admission rule로 사용한다.
- 수집 범위:
  - 1단계: 대표 노선·목표 구간을 `getBusPosByRouteSt`로 수집해 정류장 전이와 ID mapping 검증
  - 2단계: 호출량 증액 및 스키마 검증 후 `getBusPosByRtid`로 route-wide 수집
  - 요청한 `busRouteId`와 각 item의 `routeId`가 같은지 항상 재검증한다.
- 원문 저장 여부: **예**
  - status code, response headers, raw body, 요청 파라미터의 비밀 제외 버전, 수집 시작·수신시각, parser/schema version, payload hash를 저장한다.
  - `serviceKey`는 원문·로그·trace에서 마스킹한다.
- 저장 위치: **[설계안] Bronze/raw object storage**

```text
data/raw/seoul-bus-position/
  ingest_date=YYYY-MM-DD/hour=HH/route_id={busRouteId}/{fetch_id}.{xml|json}
```

  - 정규화 레코드는 Silver 테이블 `bus_position_observation`에 append-only로 저장한다.
  - raw와 정규화 레코드를 `fetch_id`, `payload_sha256`, `item_index`로 연결한다.
- 재시도 정책:
  - 네트워크 timeout, HTTP 429/5xx, gateway `01/04/05/23`, 제공기관 `headerCd=1/6`은 exponential backoff + jitter로 최대 3회 재시도한다.
  - 초당 한도 `23`은 즉시 호출률을 낮추고, 일일 한도 `22`는 무한 재시도하지 않고 quota window 종료까지 수집을 중단한다.
  - HTTP 401, key 오류 `20/30/31`, 잘못된 파라미터 `10`, 정류장·노선 오류 `3/4`는 동일 요청을 재시도하지 않는다.
  - `headerCd=8` 운행종료는 정상적인 빈 상태로 분류한다.
  - 공식 quota reset 시각이 미공개이므로 자정 자동 복구를 보장하지 않고 첫 성공 호출로 복구를 확인한다.
- 중복 판정 기준:
  - raw fetch: `payload_sha256`가 같아도 각 호출의 `fetch_id`와 수집시각을 유지한다.
  - 논리 관측 중복 후보: `routeId + vehId + dataTm + sectionId + sectOrd + stopFlag`
  - 분석용 Silver에서는 위 key와 raw hash로 중복을 표시하되, source가 실제로 반복 제공한 사실을 잃지 않도록 Bronze 원문은 삭제하지 않는다.
  - 동일 `dataTm`인데 위치·상태가 바뀌면 충돌 레코드로 보존하고 `SOURCE_TIMESTAMP_COLLISION` 품질 flag를 붙인다.

## 9. 전처리 및 활용

- 생성할 데이터:
  - [x] 구간 운행시간 — 동일 차량의 연속 구간 전이를 반복 관측해 추정
  - [x] 정차시간 — `stopFlag`의 도착·출발 상태구간으로 추정
  - [x] 실제 배차간격 — 같은 노선·방향·정류장 도착 후보 간 간격으로 추정
  - [x] 계획 대비 지연 — 시간표 API와 결합할 때만 생성
  - [ ] 사고·운행장애 이벤트 — 구조화된 사고·장애 필드가 없어 별도 알림/장애 API 필요
- 전처리 규칙:
  1. HTTP non-2xx와 2xx 업무오류를 분리한다. 2xx에서도 `headerCd != "0"`이면 데이터로 적재하지 않는다.
  2. XML/JSON의 단건 `itemList`와 배열 `itemList[]`를 항상 배열로 정규화한다.
  3. `itemCount`가 아니라 실제 `itemList` 개수를 `observed_item_count`로 기록한다.
  4. 모든 leaf 원값을 보존한 뒤 정수·소수·시간을 명시적으로 cast하고 실패값에 quality flag를 붙인다.
  5. 응답 item의 `routeId`가 요청 `busRouteId`와 같은지 검사한다. 과거 프로젝트 분석에서 요청 route filter가 빠져 다른 노선이 섞인 적이 있어 이를 필수 gate로 둔다.
  6. `dataTm`은 차량별 원천시각으로 parsing하고, `received_at_utc`, `source_age_seconds`, `out_of_order`, `stale`을 계산한다.
  7. 동일 `routeId + vehId`에서 source time이 단조 증가하는 관측만 상태전이 계산에 사용한다. 원문 순서를 그대로 이벤트 순서로 간주하지 않는다.
  8. `stopFlag: 0 → 1`이면 `(이전 source time, 최초 1 source time]`을 `arrival_observation_interval`로 저장한다. 구간 끝을 확정 도착시각으로 승격하지 않는다.
  9. `stopFlag: 1 → 0`은 출발 후보로 저장하고, 연속 1 관측으로 정차시간 구간을 추정한다. 폴링 간격보다 정밀한 점 추정은 하지 않는다.
  10. `tmX/tmY`는 WGS84, `posX/posY`는 GRS80로 분리한다. 좌표계를 섞거나 이름만 보고 자동 변환하지 않는다.
  11. `congetion=0`은 빈 좌석이 아니라 **정보 없음**으로 처리한다. `6`, `99`, 예상 밖 값은 raw 보존 후 `UNKNOWN_CONGESTION_CODE`로 관리한다.
  12. `isFullFlag`는 실제 응답에 존재하지만 현재 해당 상세기능 표에 없으므로 schema drift 필드로 저장하고, 의미·coverage 검증 전 모델 입력에서는 제외한다.
  13. `sectDist`는 단위가 검증될 때까지 raw numeric과 `unit=UNKNOWN`을 함께 저장한다.
- 다른 데이터와 결합할 키:
  - 노선 기준정보: `busRouteId/routeId`
  - 버스도착정보 API: `routeId + vehId`, 필요 시 `dataTm`과 수집시각 근접 조건 추가
  - 노선·정류장 topology: `routeId + sectOrd + sectionId + direction/version`
  - 시간표: `internal_route_id + internal_stop_id + direction + service_date`
  - 날씨·교통상황: 정규화된 WGS84 위치와 관측시간 bucket
- 모델 입력 변수:
  - 원천: `routeId`, `vehId`, `sectOrd`, `sectionId`, `sectDist`, `stopFlag`, `tmX`, `tmY`, `busType`, `congetion`, 검증 후 `isFullFlag`
  - 시간 품질: `source_age_seconds`, `collector_rtt_ms`, `duplicate`, `out_of_order`, `stale`, missingness flags
  - 파생: 최근 구간 운행시간, 정차시간, 동일 정류장 실제 배차간격, 차량 진행속도 후보, 시간대·요일·서비스일
  - 결합: 시간표 대비 지연, 버스도착정보 ETA residual, 환승·보행시간, 기상·교통 feature
  - 실시간 feature가 stale이거나 누락되면 모델이 이를 명시적으로 알 수 있도록 quality/missingness 변수를 함께 전달한다.

## 10. 데이터 품질 및 제약

- 결측값 발생 조건:
  - 조회 구간에 운행 차량이 없거나 운행이 종료된 경우 빈 `msgBody/itemList`가 정상적으로 발생할 수 있다.
  - 좁은 `startOrd~endOrd` 구간에서는 대부분 호출이 빈 결과일 수 있다.
  - 차량 송신 지연·종료, 제공기관 실시간정보 수신 불가 `headerCd=6`, 필드별 미제공으로 결측이 생길 수 있다.
  - `congetion=0`은 측정값 0이 아니라 정보없음으로 취급한다.
- 중복 데이터 가능성: **높음**
  - 제공기관 5초 갱신보다 빠른 호출 또는 차량별 미갱신으로 동일 `vehId + dataTm`이 반복될 수 있다.
  - 과거 route filter가 적용되지 않은 다중 노선 혼합 표본에서는 257개 관측 중 51개, 약 19.8%가 동일 `vehId + dataTm` 반복이었다.
  - 이 수치는 노선 753 고유 중복률로 사용할 수 없으며, 노선별 filter를 적용해 다시 계산해야 한다. 다만 동일 source timestamp 반복 가능성과 dedupe 필요성을 보여주는 품질 경고로만 사용한다.
- 잘못된 값 또는 특수값:
  - 필드명 `congetion`은 오탈자지만 실제 계약이므로 임의로 `congestion`만 기대하면 안 된다.
  - 최신 포털과 2023 가이드의 `busType`, 좌표 필드, `dataTm` 길이, 혼잡도 코드가 일부 다르다.
  - `isFullFlag`는 정상 원문에 존재하지만 최신 `getBusPosByRouteSt` 출력표에는 없다.
  - 정상 응답에서 `itemCount=0`인데 실제 `itemList` 13개가 반환된 사례가 있다.
  - 최신 포털의 `endOrd` 길이 2 표기와 달리 `110`이 정상 처리됐다.
  - 한 호출에 매우 오래된 차량별 `dataTm`이 섞일 수 있어, 응답 성공을 최신성 보장으로 해석하면 안 된다.
- 데이터 제공 제외 구간:
  - 정확한 제외 노선·운수회사·구간은 공식 미공개다.
  - `getBusPosByRouteSt`는 요청한 정류장 순번 구간 밖 차량을 반환하지 않는 것이 정상이다.
  - 저상버스 전용 조회는 별도 상세기능으로도 제공된다.
- 실시간 데이터 과거 보관 여부: **API에서 조회 불가 / 제공기관 보관정책 미공개**
  - 학습·검증 이력은 자체 수집한 원문만 사용할 수 있다.
- API 장애 시 대체 데이터:
  - 버스도착정보 API의 ETA·차량 ID, 노선/정류장 기준정보, 시간표를 사용해 degraded mode로 계산한다.
  - 마지막 정상 위치는 `stale=true`와 age를 노출하는 경우에만 제한적으로 사용한다.
  - freshness threshold를 넘거나 대체 근거가 부족하면 확률·출발추천을 이전 값으로 조용히 유지하지 않고 `INSUFFICIENT`로 전환한다.
- 확인된 문제:
  1. 공식 endpoint가 `HTTP`만 안내되며, 이 환경의 HTTPS 연결은 실패했다.
  2. current success JSON envelope는 아직 검증하지 못했다.
  3. 포털·2023 가이드·실제 payload 사이에 필드 및 코드 drift가 있다.
  4. `itemCount`가 실제 item 수와 다를 수 있다.
  5. 차량별 `dataTm` 최신성 편차와 중복이 크다.
  6. 방향 필드와 현재 정류장 ID가 없어 topology mapping이 필요하다.
  7. 과거 이력, 지연 SLA, 정확한 coverage, ID 안정성 계약이 공개돼 있지 않다.
  8. `dataTm` timezone과 센서시각/게시시각의 정확한 의미가 미공개다.

## 11. 테스트 결과

- 테스트 일시:
  - **현재 endpoint·인증 오류 확인:** 2026-08-25 KST
  - **정상 호출 저장 증거:** 2026-08-21~2026-08-22 KST
  - **응답시간 지속 수집 증거:** 2026-08-22 KST
- 정상 호출 여부:
  - **현재 조사:** 운영키를 읽지 않았으므로 정상 호출은 재실행하지 않음
  - **저장된 증거:** HTTP 200, `headerCd=0`, 정상 XML 응답 확인
  - **현재 무키/오류키:** 각각 HTTP 401 JSON 오류를 확인
- 실제 응답 건수:
  - 노선 753, `busRouteId=100100118`, `startOrd=1`, `endOrd=110` 단일 호출: **13개 차량 item**
  - 버스 147 목표 구간 단일 호출: **1개 차량 item**
  - 01A 30분 목표 구간 실험: **90회 위치 호출, 44개 차량 관측, 6대 차량, 51회 빈 결과, API 오류 0회**
- 응답시간:
  - 정상 성공 호출 180회: `n=180`, min 약 4.7ms, p50 약 **43ms**, p95 약 **101ms**, p99 약 **381ms**, max 약 384ms
  - 2026-08-25 무키 HTTP 401: 약 87.5ms
  - 2026-08-25 오류키 HTTP 401: 약 79.9ms
  - 위 수치는 특정 실행환경의 collector 왕복시간이며 제공기관 SLA가 아니다.
- 확인한 특이사항:
  1. 단일 응답의 13대 차량 `dataTm` age가 약 4.9~895.9초로 크게 달랐다.
  2. `itemCount=0`인데 실제 item이 13개인 성공 응답이 있었다.
  3. `endOrd=110`이 성공해 포털의 길이 2 metadata와 달랐다.
  4. 실제 payload에 최신 출력표에 없는 `isFullFlag`가 존재했다.
  5. route filter 미적용 과거 혼합 표본에서 동일 `vehId + dataTm` 반복이 약 19.8%였으며, 노선별 중복률은 재계산이 필요하다.
  6. 포털은 JSON을 지원하지만, 이번 조사에서 확인한 성공 원문은 XML이며 JSON은 401 오류 envelope만 현재 검증했다.
  7. HTTPS 443은 이 실행환경에서 약 21초 후 timeout됐다. 다른 네트워크에서의 보편적 미지원까지 증명한 것은 아니다.

### 현재 재현 가능한 인증 오류 테스트

```http
GET http://ws.bus.go.kr/api/rest/buspos/getBusPosByRouteSt?busRouteId=100100026&startOrd=41&endOrd=48
```

```json
{
  "error": "Unauthorized",
  "message": "serviceKey 파라미터가 필요합니다.",
  "status": 401
}
```

## 12. 결정 사항 및 TODO

- [x] API 키 발급 — 기존 프로젝트의 정상 호출 증거로 발급·사용 이력 확인; 현재 문서와 로그에는 키를 저장하지 않음
- [ ] 호출 한도 증액 신청 — route 수·목표 폴링주기·일일 예상량을 산정해 활용사례와 함께 신청
- [ ] 원시 데이터 수집기 구현 — 실험 수집기는 존재하지만 운영용 quota admission, cache, raw storage, schema versioning, 관측성까지 완성 필요
- [ ] 내부 ID 매핑 — `routeId`·`vehId` 제한적 join은 검증했으나 `sectionId`↔정류장, 방향, 회차 mapping이 남음
- [ ] 결측·중복 처리 — quality flag와 Bronze 보존 규칙을 코드·테스트로 구현
- [ ] 장기 수집 테스트 — 주중/주말, 주간/심야, 정상/장애, 다중 노선 coverage 및 drift 검증

### 결정 사항

1. `getBusPosByRouteSt`는 **실시간 위치·상태 관측 source**로 채택하되 ETA 또는 확정 Actual source로 표기하지 않는다.
2. `stopFlag 0→1`은 도착 점시각이 아니라 두 관측 사이의 `arrival_observation_interval`로 생성한다.
3. 정상 성공 XML이 이미 검증됐으므로 첫 collector는 XML raw를 안정적으로 보존하고, `resultType=json` 성공 smoke test 후 JSON parser를 활성화한다.
4. 개발계정에서는 120초 baseline과 제한된 20~30초 evidence window를 분리한다. 24시간 고빈도 수집은 증액 승인 전 시작하지 않는다.
5. 사용자가 호출할 때마다 원 API를 재호출하지 않고 backend 공용 collector/cache 결과를 사용한다.
6. `dataTm`, `received_at`, raw body, parser/schema version, payload hash를 함께 저장한다.
7. stale·결측·ID mapping 실패가 품질 기준을 넘으면 확률·추천 결과를 강제로 만들지 않고 `INSUFFICIENT`를 반환한다.

### 추가 TODO

- [ ] 운영키로 `resultType=json` 정상 응답 1건을 캡처해 exact JSON envelope와 단건/복수 `itemList` 형태 확인
- [ ] `dataTm` timezone, 생성 지점, provider clock offset을 문의·실측하고 `source_age` 해석 확정
- [ ] `sectDist` 실제 단위와 `busType`·`congetion`·`isFullFlag` 코드 coverage 검증
- [ ] `getBusPosByRtid`의 현재 payload, `nextStTm`/`lastStTm` 단위·예측 근거 검증 후 route-wide 전환 여부 결정
- [ ] plain HTTP upstream과 query-key 노출 위험에 대한 운영 보안 수용 여부 및 secure proxy 구성 결정
- [ ] 노선별 운수회사·서비스 구간·심야/막차 coverage matrix 작성
- [ ] `itemCount` 불일치, singleton/array, extra field, stale/out-of-order, quota·업무오류에 대한 fixture test 추가
- [ ] 30일 이상 장기 수집으로 시간대·요일·노선별 중복률, 빈 응답률, feed age, 전이 포착률을 측정

## 부록 A. 오류 처리 기준

### 공공데이터포털 gateway 오류

| 코드/상태 | 의미 | 처리 |
| --- | --- | --- |
| HTTP 401 / `20`, `30`, `31` | 키 누락·권한 없음·미등록·만료 | 재시도 금지, secret/권한 점검 |
| `01` | application error | 제한 재시도 후 장애 기록 |
| `04` | HTTP error | status에 따라 제한 재시도 |
| `05` | service timeout | exponential backoff + jitter |
| `10` | invalid request parameter | 요청 validation 수정, 재시도 금지 |
| `12` | service 없음 | endpoint/version 확인 |
| `22` | 일일 호출량 초과 | 수집 중단, quota window/증액 확인 |
| `23` | 초당 호출량 초과 | 호출률 감소 후 재시도 |
| `29` | blacklist IP | 운영자 확인, 자동 우회 금지 |

### 제공기관 `msgHeader.headerCd`

| 코드 | 의미 | 처리 |
| --- | --- | --- |
| `0` | 정상 | item parse |
| `1` | 시스템 오류 | 제한 재시도 |
| `2` | 질의 오류 | 입력 점검, 재시도 금지 |
| `3` | 정류장 없음 | ID mapping 갱신 |
| `4` | 노선 없음 | ID mapping 갱신 |
| `5` | 좌표 오류 | 해당 상세기능 입력 점검 |
| `6` | 실시간 정보 수신 불가 | 제한 재시도, stale/degraded 처리 |
| `7` | 경로 결과 없음 | 정상 no-result 후보로 분리 |
| `8` | 운행 종료 | 정상 terminal 상태로 처리 |

## 부록 B. 호출량 산정 예시

| 시나리오 | 노선 수 | 주기 | 예상 호출/일 | 개발 기본 한도 1,000회 적합성 |
| --- | ---: | ---: | ---: | --- |
| 단일 노선 baseline | 1 | 120초 | 720 | 가능, 280회 여유 |
| 단일 노선 최대 근접 | 1 | 90초 | 960 | 가능하나 재시도 여유 40회뿐 |
| 단일 노선 30초 상시 | 1 | 30초 | 2,880 | 불가 |
| 5개 노선 10분 | 5 | 600초 | 720 | 가능 |
| 10개 노선 15분 | 10 | 900초 | 960 | 가능 |
| 5개 노선 5초 실시간 | 5 | 5초 | 86,400 | 증액·별도 운영계약 없이는 불가 |

> 호출량 표는 상세기능 1개의 호출을 기준으로 한 설계 계산이다. 실제 계정의 상세기능별/서비스별 quota 합산 방식은 공공데이터포털 마이페이지에서 재확인한다.
