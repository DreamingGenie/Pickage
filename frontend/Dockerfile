# ── 1단계: 빌드 ────────────────────────────────────────────────
# Vite 는 정적 파일을 만들어 낼 뿐이라 최종 이미지에 Node 가 필요 없다.
FROM node:22-alpine AS build
WORKDIR /app

# 의존성을 먼저 받아 레이어로 굳힌다. 소스만 고쳤을 때 npm ci 를 건너뛴다.
COPY package.json package-lock.json ./
# npm install 이 아니라 npm ci 다 — 락파일 그대로 설치하므로
# 내 PC 와 서버가 다른 버전을 받는 일이 없다.
RUN npm ci

COPY . .
# package.json 의 build 는 `tsc -b && vite build` 다.
# 타입 오류가 있으면 여기서 멈춘다 — 깨진 화면이 배포되는 것보다 낫다.
RUN npm run build

# ── 2단계: 서빙 ────────────────────────────────────────────────
# 이 컨테이너가 80/443 을 받는다. 정적 파일을 주고, /api 는 백엔드로 넘긴다.
# nginx 설정은 이미지에 굽지 않고 compose 가 마운트한다 —
# 설정만 고칠 때 프런트를 다시 빌드하지 않기 위해서다.
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
