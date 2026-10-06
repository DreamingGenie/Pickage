import { fileURLToPath } from 'node:url'
// `vitest/config`의 defineConfig 는 Vite 설정 타입을 그대로 확장해 `test` 블록만 추가한다.
// 파일을 따로 두면 `@` alias·플러그인을 두 번 적어야 한다.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * dev 프록시가 넘길 곳.
 *
 * **`localhost` 가 아니라 `127.0.0.1` 이다.** Node 18 부터 DNS 결과를 OS 순서대로 쓰는데,
 * Windows 에서 `localhost` 는 `::1`(IPv6) 로 먼저 풀린다. Spring 의 Tomcat 은 IPv4
 * `0.0.0.0` 에만 바인딩되므로 프록시가 연결에 실패하고 **브라우저에는 502 만 보인다.**
 *
 * `curl` 은 실패 시 IPv4 로 폴백해서 잘 되기 때문에, "curl 은 되는데 화면은 502" 라는
 * 헷갈리는 모양이 된다. 주소를 못 박으면 그 경로 자체가 없어진다.
 *
 * 서버를 다른 곳에 띄웠으면 `VITE_DEV_API_TARGET` 환경변수로 덮어쓴다.
 * (Vite 설정은 Node 에서 도므로 `.env.local` 이 아니라 셸 환경변수를 읽는다.)
 */
const DEV_API_TARGET = process.env.VITE_DEV_API_TARGET ?? 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      /**
       * dev 서버(5173) 에서 API 요청만 Spring(8080) 으로 넘긴다.
       *
       * **CORS 설정을 서버에 넣지 않기 위해서다.** 브라우저가 보기에 요청은 여전히
       * 같은 오리진(5173)에서 나가므로 프리플라이트 자체가 생기지 않는다.
       * 서버에 `@CrossOrigin` 이나 CorsConfigurationSource 를 두면 개발 편의를 위한
       * 설정이 운영 코드에 남고, 나중에 허용 오리진을 좁히는 일을 누군가 해야 한다.
       *
       * 운영에서는 nginx 가 같은 오리진으로 묶으므로 이 블록이 필요 없다 —
       * dev 서버에서만 동작한다.
       *
       * 경로를 다시 쓰지 않는다(`rewrite` 없음). 서버가 `/api/**` 로 받기 때문이다.
       * 여기서 `/api` 를 떼면 프론트가 보는 경로와 서버 로그의 경로가 달라져,
       * 404 가 났을 때 어느 쪽 경로를 봐야 하는지 헷갈린다.
       */
      '/api': { target: DEV_API_TARGET, changeOrigin: true },
      /** 사전 파일(명세 §2.2). 봉투를 쓰지 않는 정적 파일이라 경로가 다르다. */
      '/static': { target: DEV_API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // 명시적으로 import 하게 둔다 — globals:true 로 describe/it/expect 를 전역으로 열면
    // eslint 에도 vitest 전역을 새로 등록해야 하는데, 테스트 파일 몇 개뿐이라 그 값어치가 없다.
    globals: false,
  },
})
