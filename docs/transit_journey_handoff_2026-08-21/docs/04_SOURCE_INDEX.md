# Source Index

이 package의 문서들은 **내용을 그대로 합치는 대상이 아니라 서로 다른 증거 수준의 자료**다.

## Project Sources

| 파일 | 역할 | 우선도 |
|---|---|---|
| `지하철_연착_확률_메트릭.pdf` | 원래 RailOdds 철학/streaming/reliability 설계 | High baseline |
| `버스_ETA_신뢰도_데이터_API_분석_보고서.pdf` | 실제 서울 버스 API 1시간 PoC / Feasibility | **Highest evidence** |
| `버스_API_및_시나리오_구축.pdf` | 버스 상태/feature/UX/Monte Carlo 아이디어 | Medium-High, verify |
| `실제_도착지까지_특정시간에_도착하는_확률_계산_방법의_연구.pdf` | Journey Probability 논리 | High design |
| `전체_경로_도착확률_및_AI_적용_설계.pdf` | LightGBM+Monte Carlo 고도화안 | Conditional |
| `지하철 detail.pdf` | Subway data catalog / 참고 | Support |

## Quality References

| 파일 | 역할 |
|---|---|
| `OSS_Shift_Proposal_2026-08-20.pdf` | Data Feasibility, Contract, Distributed Proof 수준 참고 |
| `깃든_서비스기획서_최종본.md` | 제품/UX/정책/데이터/인프라 Gate와 추적성 참고 |

## Precedence

1. **실제 API Spike 결과**
2. 공식 최신 API/Data 명세
3. 이 handoff에서 PM이 확정한 원칙
4. 실제 PoC 보고서
5. 팀 설계/연구 문서
6. Agent의 추론/아이디어

문서와 실제 데이터가 충돌하면 1~2가 우선이며, 반드시 Decision Log에 남긴다.

## SHA256

- OSS_Shift_Proposal_2026-08-20.pdf  
  `7d73a770b6441b90dda7bda5b80b7eaec55d645c3c372dde61d9d5b827fcf462`
- 깃든_서비스기획서_최종본.md  
  `366d0f6f6ca702989f24d12521e271985aba51ed8e37860f253ae75112c47426`
- 버스_API_및_시나리오_구축.pdf  
  `9eba5db77b5b9556b7d80b2b6754b8b84a0a3063fa1e415e0108cf5e8ecfd953`
- 버스_ETA_신뢰도_데이터_API_분석_보고서.pdf  
  `395bbd447140ffe4e6bc558cabd96968083c433793a5057e0225ab28178b130f`
- 실제_도착지까지_특정시간에_도착하는_확률_계산_방법의_연구.pdf  
  `aff39e0582da2dfe99c977144a4168baf9945e10822f7aadd054857b3b9061dd`
- 전체_경로_도착확률_및_AI_적용_설계.pdf  
  `d334e197c0a337f974fd8d720ac591b10696c2085d58835578fbf49b140d5adc`
- 지하철 detail.pdf  
  `cfedb62e0c96c97a7dd99465c87074cdd03f83a1584095af8ee9d40c20a89f60`
- 지하철_연착_확률_메트릭.pdf  
  `20d58923e0a524cbcaf016b308f4623adb9344ee1a12a51866f214b212c7a4e7`
