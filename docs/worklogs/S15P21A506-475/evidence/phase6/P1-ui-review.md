# P1 반영 후 서비스 사용 점검 (2026-09-25, 브라우저)

`https://j15a506.p.ssafy.io/` 에서 검색 → `/analyze?base=<패키지>` 후보 화면을 사람처럼 확인. 35개 기준 패키지.
인기도 = package_text `downloads_last_month`(ecosyste.ms, 인지도 관문이 쓰는 값). 기능 판정은 점검자 판단.

## 요약
- 후보 93개 중 월 50만 미만 2개 — **인지도 조건은 지켜진다.**
- 기능 관련성: 좋음 15 · 일부 13 · 나쁨 3(+ 후보 0개 4) — 아래 표.
- 후보 0개("비교에 쓸 자료가 부족해요"): moment(월 1.4억) · redux(1.7억) · node-fetch(7.3억) · bcrypt(2,280만) — 모두 12개월 필터.

## 판정
| 판정 | 기준 → 후보 |
| --- | --- |
| 좋음 | ws → pusher·partysocket·rpc-websockets / express → fastify·@tinyhttp/app·@hapi/hapi / koa → hono·express·fastify / jest → mocha·ava·jasmine-core / zod → joi·ajv·@redocly/ajv / jsonwebtoken → fast-jwt·@fastify/jwt·jws / chalk → yoctocolors·@colors/colors·colors-option / uuid → short-uuid·@bugsnag/cuid·uuidv7 / cheerio → htmlparser2·node-html-parser·sax-wasm / pino → bole·roarr·winston / zustand → jotai·@nanostores/react·constate / yargs → command-line-args·cmd-ts·type-flag / js-yaml → @zkochan/js-yaml·yaml·yaml-eslint-parser / yaml → js-yaml·@zkochan/js-yaml·read-yaml-file / socket.io → ws·fastify·pusher (fastify 는 관련 약함) |
| 일부 | axios(undici ○, @algolia/requester-* ×2 내부 어댑터) / winston(roarr ○, 프레임워크 내장 로거 2) / commander(command-line-args ○) / dayjs(react-moment ×) / date-fns(chrono-node 는 파서) / lodash(rollup ×) / mongoose(instrumentation ×) / sequelize(@mikro-orm 하위 3개) / jsdom(@types/web ×) / puppeteer(@types ×) / prettier(*-prettier-config ×2, dprint ○) / vue(@modern-js/utils ×) / react(@modern-js ×2) |
| 나쁨 | webpack(@textlint/module-interop·mlly·current-module-paths) / vite(@web/dev-server-core·@web/dev-server·@esbuild/android-arm) / eslint(ts-pattern·@eslint-community/regexpp·@ast-grep/cli-linux-x64-gnu) |

## 원인 (`P1-ui-review-rootcause.txt`)
- **A. 모델 순위** — 진짜 대안이 코퍼스에 있는데 top-20 에 없다: webpack(rollup·esbuild·vite·parcel·@rspack/core), react(preact·vue·svelte·solid-js), vue(react·svelte), puppeteer(playwright), lodash(underscore·ramda·lodash-es), eslint(@biomejs/biome). 아깝게 밀림: axios(ky 4·superagent 5·got 9), jest(vitest 5), sequelize(typeorm 10·drizzle-orm 12), date-fns(dayjs 8), dayjs(date-fns 7)
- **B. 필터** — 12개월: moment·luxon·node-fetch·bcrypt·redux·cross-fetch·jshint·standard. dependents<5: oxlint(월 6,800만)·es-toolkit(1.7억) — ecosyste.ms dependents 값이 실제보다 작게 잡힌 것으로 보인다(미확인)
- **C. 관문 빈틈** — 플랫폼 바이너리(@esbuild/android-arm, @ast-grep/cli-linux-x64-gnu), `@types/*`, `*-prettier-config`, `@opentelemetry/instrumentation-*`, 같은 스코프 독점(@mikro-orm ×3, @modern-js ×2, @algolia ×2)

## C 규칙 시뮬레이션 (`P1-ui-review-diversity-sim.txt`)
top-3 에 같은 스코프 1개·`@types/*`·플랫폼 바이너리 제외를 운영 산출물(top-20)에 적용: axios → ky 진입, sequelize → mikro-orm·typeorm, jsdom → domino, vite → esbuild-wasm. 전체 기준의 20.8% 에서 top-3 변경, 3개 미만 955 → 1,599 (top-20 안에서만 다시 고른 값 — 배치의 검색 30개에서 적용하면 줄어든다).
