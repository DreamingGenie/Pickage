# Source Index

이 package의 문서들은 서로 다른 증거 수준의 자료다. **아래 경로가 이 ZIP 안의 실제 경로이며, Agent는 이 경로를 기준으로 읽는다.**

## Project Sources

| 실제 package 경로 | 원래 파일명 | 역할 | 우선도 |
|---|---|---|---|
| `sources/project/01_bus_eta_reliability.pdf` | 버스_ETA_신뢰도_데이터_API_분석_보고서.pdf | 실제 서울 버스 API 1시간 PoC / Feasibility | **Highest evidence** |
| `sources/project/02_bus_api_scenario.pdf` | 버스_API_및_시나리오_구축.pdf | 버스 상태/feature/UX/Monte Carlo 아이디어 | Medium-High, verify |
| `sources/project/03_journey_probability_research.pdf` | 실제_도착지까지_특정시간에_도착하는_확률_계산_방법의_연구.pdf | Journey Probability 논리 | High design |
| `sources/project/04_journey_probability_ai_design.pdf` | 전체_경로_도착확률_및_AI_적용_설계.pdf | LightGBM+Monte Carlo 고도화안 | Conditional |
| `sources/project/05_subway_detail.pdf` | 지하철 detail.pdf | Subway data catalog / 참고 | Support |
| `sources/project/06_subway_reliability_metric.pdf` | 지하철_연착_확률_메트릭.pdf | 원래 RailOdds 철학/streaming/reliability 설계 | High baseline |

## Quality References

| 실제 package 경로 | 원래 파일명 | 역할 |
|---|---|---|
| `sources/reference_quality/90_oss_shift_proposal.pdf` | OSS_Shift_Proposal_2026-08-20.pdf | Data Feasibility, Contract, Distributed Proof 수준 참고 |
| `sources/reference_quality/91_service_plan_reference.md` | 깃든_서비스기획서_최종본.md | 제품/UX/정책/데이터/인프라 Gate와 추적성 참고 |

## Text Extracts

`source/project` PDF 6개와 OSS Shift PDF는 `sources/text_extracted/`에 동일 번호의 `.txt` 추출본이 있다. 검색 편의용이며 원본 대체물이 아니다.

## Precedence
1. 실제 API Spike 결과
2. 공식 최신 API/Data 명세
3. handoff에서 PM이 확정한 원칙
4. 실제 PoC 보고서
5. 팀 설계/연구 문서
6. Agent의 추론/아이디어

문서와 실제 데이터가 충돌하면 1~2가 우선이며 반드시 Decision Log에 남긴다.
