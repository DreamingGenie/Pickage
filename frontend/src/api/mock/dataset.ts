/**
 * mock 데이터 원본.
 *
 * 값은 지어낸 것이다. **구조만** 명세를 따른다 —
 * 주간 스냅샷, 패키지마다 다른 관측 시작, 지표 결측(null), major 별 dependents 합계.
 *
 * 난수를 쓰지 않는다. 새로고침마다 그래프가 흔들리면 화면 버그와 구분할 수 없다.
 */

/** 0.5 — 모든 현재값의 기준. 실제로는 `SELECT MAX(snapshot_at) FROM snapshot`. */
export const LATEST_SNAPSHOT = '2026-08-31'

const WEEK_MS = 7 * 864e5

/** 스냅샷은 매주 월요일 하나. 최신에서 뒤로 세어 만든다. */
export function snapshotDates(weeks: number, end = LATEST_SNAPSHOT): string[] {
  const endMs = Date.parse(end)
  return Array.from({ length: weeks }, (_, i) =>
    new Date(endMs - (weeks - 1 - i) * WEEK_MS).toISOString().slice(0, 10),
  )
}

/**
 * 전체 스냅샷 축.
 *
 * 조회 상한이 없어진 뒤에도(S15P21A506-374) 2년 반치를 유지한다 — 구간 자르기와 간격
 * 솎아내기가 실제로 동작하는지 보려면 축이 화면보다 길어야 한다.
 */
export const ALL_SNAPSHOTS = snapshotDates(130)

/** 결정적 흔들림. 두 주기를 겹쳐 규칙적으로 보이지 않게만 한다. */
const wobble = (seed: number, i: number) =>
  Math.sin((i + seed) / 3.3) * 0.55 + Math.sin((i + seed) / 8.7) * 0.9

export interface MockMajor {
  major: string
  /** 최신 스냅샷 기준 dependents 합계 */
  dependents: number
}

export interface MockPackage {
  name: string
  repo_url: string | null
  latest_version: string
  published_at: string
  description: string | null
  licenses: string[]
  is_deprecated: boolean

  /** 관측 시작 인덱스. 이보다 앞선 스냅샷에는 행이 아예 없다(§4 시점 어긋남). */
  startIndex: number

  /** 최신 스냅샷의 주간 다운로드. 과거는 growth 로 역산한다. */
  downloads: number
  /** 주당 다운로드 증가율 */
  downloadsGrowth: number

  /** 최신 스냅샷의 dependents 합계(전 버전) */
  dependents: number
  dependentsGrowth: number

  stars: number
  /** 주당 별 증가량 */
  starsPerWeek: number
  openIssues: number
  openIssuesPerWeek: number

  /** major 별 지분. 합이 dependents 와 정확히 같을 필요는 없다(비율만 쓴다). */
  majors: MockMajor[]

  /**
   * 지표 결측. true 면 패키지는 존재하지만 스냅샷이 없어 지표가 전부 null 이다.
   * 0.5 — `not_found` 와 구분해야 하는 경우를 화면에서 실제로 밟아보기 위한 것.
   */
  noSnapshot?: boolean

  /**
   * 검색용 채움 패키지 표시.
   *
   * 있으면 시계열이 **1차식**(`latest - step * weeksAgo`)이고 전부 정수다.
   * 시드 SQL 이 같은 값을 `generate_series` 로 만들 수 있어야 해서다 — 그래서
   * 300개를 넣어도 시드 파일이 커지지 않는다(값 대신 계수만 싣는다).
   */
  filler?: { dlStep: number; depStep: number }
}

/**
 * 카탈로그.
 *
 * winston·pino·bunyan 은 기존 화면 기본값이라 그대로 두고,
 * express·fastify·koa 는 명세 예시라 함께 넣는다.
 */
export const MOCK_PACKAGES: MockPackage[] = [
  {
    name: 'winston',
    repo_url: 'https://github.com/winstonjs/winston',
    latest_version: '3.19.0',
    published_at: '2026-07-14T09:02:11Z',
    description: 'A logger for just about everything',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 12_940_000,
    downloadsGrowth: 0.0016,
    dependents: 12_560,
    dependentsGrowth: 0.0011,
    stars: 22_412,
    starsPerWeek: 11,
    openIssues: 412,
    openIssuesPerWeek: -0.4,
    majors: [
      { major: '3', dependents: 6_782 },
      { major: '2', dependents: 3_893 },
      { major: '1', dependents: 1_507 },
      { major: '0', dependents: 378 },
    ],
  },
  {
    name: 'pino',
    repo_url: 'https://github.com/pinojs/pino',
    latest_version: '10.3.1',
    published_at: '2026-08-21T04:41:52Z',
    description: 'Fast JSON logger for Node.js',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 6_820_000,
    downloadsGrowth: 0.0042,
    dependents: 5_610,
    dependentsGrowth: 0.0051,
    stars: 15_038,
    starsPerWeek: 17,
    openIssues: 138,
    openIssuesPerWeek: 0.3,
    majors: [
      { major: '10', dependents: 2_300 },
      { major: '9', dependents: 2_019 },
      { major: '8', dependents: 1_065 },
      { major: '7', dependents: 226 },
    ],
  },
  {
    name: 'bunyan',
    repo_url: 'https://github.com/trentm/node-bunyan',
    latest_version: '1.8.15',
    published_at: '2025-12-03T18:20:03Z',
    description: 'A simple and fast JSON logging module for node.js services',
    licenses: ['MIT'],
    /** 폐기 표시 경로를 화면에서 밟아보기 위한 값 */
    is_deprecated: true,
    startIndex: 0,
    downloads: 618_000,
    downloadsGrowth: -0.0013,
    dependents: 1_712,
    dependentsGrowth: -0.0009,
    stars: 7_192,
    starsPerWeek: 0.4,
    openIssues: 331,
    openIssuesPerWeek: 0,
    majors: [
      { major: '1', dependents: 1_506 },
      { major: '0', dependents: 206 },
    ],
  },
  {
    name: 'express',
    repo_url: 'https://github.com/expressjs/express',
    latest_version: '5.0.1',
    published_at: '2026-07-14T09:02:11Z',
    description: 'Fast, unopinionated, minimalist web framework',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 38_214_905,
    downloadsGrowth: 0.0009,
    dependents: 888_890,
    dependentsGrowth: 0.0008,
    stars: 66_120,
    starsPerWeek: 79,
    openIssues: 187,
    openIssuesPerWeek: -0.5,
    majors: [
      { major: '4', dependents: 812_430 },
      { major: '5', dependents: 71_120 },
      { major: '3', dependents: 5_340 },
    ],
  },
  {
    name: 'fastify',
    repo_url: 'https://github.com/fastify/fastify',
    latest_version: '5.7.0',
    published_at: '2026-08-02T11:14:40Z',
    description: 'Fast and low overhead web framework, for Node.js',
    licenses: ['MIT'],
    is_deprecated: false,
    /** 늦게 관측이 시작된 패키지. 시리즈 길이가 달라지는 경우를 만든다. */
    startIndex: 44,
    downloads: 4_120_000,
    downloadsGrowth: 0.0061,
    dependents: 41_220,
    dependentsGrowth: 0.0066,
    stars: 34_870,
    starsPerWeek: 41,
    openIssues: 96,
    openIssuesPerWeek: 0.2,
    majors: [
      { major: '5', dependents: 24_180 },
      { major: '4', dependents: 14_902 },
      { major: '3', dependents: 2_138 },
    ],
  },
  {
    name: 'koa',
    repo_url: 'https://github.com/koajs/koa',
    latest_version: '3.1.0',
    published_at: '2026-05-19T07:55:12Z',
    description: 'Koa web app framework',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 2_460_000,
    downloadsGrowth: -0.0004,
    dependents: 30_140,
    dependentsGrowth: 0.0003,
    stars: 35_610,
    starsPerWeek: 6,
    openIssues: 61,
    openIssuesPerWeek: 0,
    majors: [
      { major: '2', dependents: 27_940 },
      { major: '3', dependents: 2_010 },
      { major: '1', dependents: 190 },
    ],
  },
  {
    name: 'log4js',
    repo_url: 'https://github.com/log4js-node/log4js-node',
    latest_version: '6.9.1',
    published_at: '2026-06-15T02:30:00Z',
    description: 'Port of Log4js to work with node.',
    licenses: ['Apache-2.0'],
    is_deprecated: false,
    startIndex: 12,
    downloads: 3_180_000,
    downloadsGrowth: 0.0007,
    dependents: 4_980,
    dependentsGrowth: 0.0004,
    stars: 5_812,
    starsPerWeek: 1.2,
    openIssues: 74,
    openIssuesPerWeek: 0.1,
    majors: [
      { major: '6', dependents: 4_120 },
      { major: '4', dependents: 610 },
      { major: '3', dependents: 250 },
    ],
  },
  {
    name: 'loglevel',
    repo_url: 'https://github.com/pimterry/loglevel',
    latest_version: '1.9.2',
    published_at: '2026-03-02T13:09:44Z',
    description: 'Minimal lightweight logging for JavaScript',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 9_410_000,
    downloadsGrowth: 0.0011,
    dependents: 3_240,
    dependentsGrowth: 0.0006,
    stars: 2_691,
    starsPerWeek: 0.6,
    openIssues: 19,
    openIssuesPerWeek: 0,
    majors: [
      { major: '1', dependents: 3_190 },
      { major: '0', dependents: 50 },
    ],
  },
  {
    name: 'consola',
    repo_url: 'https://github.com/unjs/consola',
    latest_version: '3.4.2',
    published_at: '2026-07-30T21:02:00Z',
    description: 'Elegant Console Logger',
    licenses: ['MIT'],
    is_deprecated: false,
    /**
     * 0.5 — 패키지는 있으나 스냅샷이 아직 없다.
     * 지표는 전부 null 이고 `not_found` 에는 들어가지 않는다.
     */
    noSnapshot: true,
    startIndex: 0,
    downloads: 0,
    downloadsGrowth: 0,
    dependents: 0,
    dependentsGrowth: 0,
    stars: 0,
    starsPerWeek: 0,
    openIssues: 0,
    openIssuesPerWeek: 0,
    majors: [],
  },
  {
    name: 'morgan',
    repo_url: 'https://github.com/expressjs/morgan',
    latest_version: '1.10.1',
    published_at: '2025-09-18T10:00:00Z',
    description: 'HTTP request logger middleware for node.js',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 7_120_000,
    downloadsGrowth: 0.0005,
    dependents: 21_400,
    dependentsGrowth: 0.0004,
    stars: 8_010,
    starsPerWeek: 1.4,
    openIssues: 42,
    openIssuesPerWeek: 0,
    majors: [{ major: '1', dependents: 21_400 }],
  },
  {
    name: 'debug',
    repo_url: 'https://github.com/debug-js/debug',
    latest_version: '4.4.3',
    published_at: '2026-05-27T16:44:10Z',
    description: 'Lightweight debugging utility for Node.js and the browser',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 412_000_000,
    downloadsGrowth: 0.0012,
    dependents: 1_204_300,
    dependentsGrowth: 0.001,
    stars: 11_290,
    starsPerWeek: 3.1,
    openIssues: 88,
    openIssuesPerWeek: 0,
    majors: [
      { major: '4', dependents: 1_098_200 },
      { major: '3', dependents: 91_800 },
      { major: '2', dependents: 14_300 },
    ],
  },
  {
    name: 'tslog',
    repo_url: 'https://github.com/fullstack-build/tslog',
    latest_version: '4.9.3',
    published_at: '2026-04-11T08:12:00Z',
    description: 'Powerful, fast and expressive logging for TypeScript and JavaScript',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 61,
    downloads: 486_000,
    downloadsGrowth: 0.0071,
    dependents: 612,
    dependentsGrowth: 0.0083,
    stars: 2_112,
    starsPerWeek: 2.4,
    /** 저장소 연결이 검증되지 않은 경우 — stars 는 있고 issues 만 없다 */
    openIssues: 0,
    openIssuesPerWeek: 0,
    majors: [
      { major: '4', dependents: 540 },
      { major: '3', dependents: 72 },
    ],
  },
  {
    name: 'signale',
    repo_url: null,
    latest_version: '1.4.0',
    published_at: '2024-08-09T00:00:00Z',
    description: 'Highly configurable logging utility',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 214_000,
    downloadsGrowth: -0.0021,
    dependents: 380,
    dependentsGrowth: -0.0018,
    /** repo_url 이 없으면 별·이슈를 관측할 수 없다 — null 경로 */
    stars: 0,
    starsPerWeek: 0,
    openIssues: 0,
    openIssuesPerWeek: 0,
    majors: [{ major: '1', dependents: 380 }],
  },
  {
    name: '@types/node',
    repo_url: 'https://github.com/DefinitelyTyped/DefinitelyTyped',
    latest_version: '24.13.3',
    published_at: '2026-08-28T05:31:00Z',
    description: 'TypeScript definitions for node',
    licenses: ['MIT'],
    is_deprecated: false,
    startIndex: 0,
    downloads: 198_400_000,
    downloadsGrowth: 0.0021,
    dependents: 512_800,
    dependentsGrowth: 0.0024,
    stars: 50_120,
    starsPerWeek: 22,
    openIssues: 214,
    openIssuesPerWeek: 0.6,
    majors: [
      { major: '24', dependents: 210_400 },
      { major: '22', dependents: 168_200 },
      { major: '20', dependents: 94_100 },
      { major: '18', dependents: 32_600 },
      { major: '16', dependents: 7_500 },
    ],
  },
]

/* ------------------------------------------------------------------ *
 * 검색용 채움 목록
 * ------------------------------------------------------------------ */

/**
 * 실제로 쓰이는 npm 이름들.
 *
 * 위 카탈로그 14개만으로는 <b>검색창에 뭘 쳐도 두어 개밖에 안 뜬다.</b> 자동완성의
 * 동작(접두사 일치, 인기순 정렬, 사전↔폴백 병합)을 눈으로 확인하려면 이름이 충분히
 * 많아야 한다.
 *
 * 카탈로그와 달리 지표를 손으로 적지 않는다. 이름에서 결정적으로 파생시킨다 —
 * 300개 분량을 손으로 적는 것은 유지할 수 없고, 적는 순간 오타가 데이터가 된다.
 */
const FILLER_NAMES: string[] = [
  // 프레임워크·런타임
  'next',
  'nuxt',
  'svelte',
  'sveltekit',
  'astro',
  'remix',
  'gatsby',
  'vue',
  'angular',
  'preact',
  'solid-js',
  'qwik',
  'ember-source',
  'backbone',
  'jquery',
  'alpinejs',
  'nestjs',
  'hono',
  'elysia',
  'polka',
  'restify',
  'hapi',
  'sails',
  'adonisjs',
  'feathers',
  // 빌드·번들
  'webpack',
  'rollup',
  'parcel',
  'esbuild',
  'swc',
  'babel-core',
  'terser',
  'browserify',
  'gulp',
  'grunt',
  'turbo',
  'nx',
  'lerna',
  'changesets',
  'tsup',
  'unbuild',
  'rspack',
  'postcss',
  'autoprefixer',
  'cssnano',
  'sass',
  'less',
  'stylus',
  'tailwindcss',
  // 테스트
  'jest',
  'vitest',
  'mocha',
  'chai',
  'sinon',
  'ava',
  'tape',
  'jasmine',
  'karma',
  'cypress',
  'playwright',
  'puppeteer',
  'selenium-webdriver',
  'testing-library',
  'supertest',
  'nock',
  'msw',
  'faker',
  'chance',
  'istanbul',
  'nyc',
  'c8',
  // 린트·포맷
  'eslint-config-airbnb',
  'eslint-plugin-import',
  'eslint-plugin-react',
  'stylelint',
  'husky',
  'lint-staged',
  'commitlint',
  'standard',
  'xo',
  'oxlint',
  'biome',
  // 유틸
  'ramda',
  'immer',
  'immutable',
  'rxjs',
  'date-fns',
  'dayjs',
  'moment',
  'luxon',
  'uuid',
  'nanoid',
  'shortid',
  'ulid',
  'cuid',
  'slugify',
  'qs',
  'query-string',
  'deepmerge',
  'clone-deep',
  'fast-deep-equal',
  'lodash-es',
  'underscore',
  'classnames',
  'clsx',
  'tiny-invariant',
  'ts-pattern',
  'remeda',
  // 검증·스키마
  'joi',
  'yup',
  'ajv',
  'superstruct',
  'io-ts',
  'valibot',
  'class-validator',
  'json-schema',
  'zod-to-json-schema',
  // HTTP·네트워크
  'node-fetch',
  'got',
  'superagent',
  'undici',
  'ky',
  'cross-fetch',
  'ws',
  'socket.io',
  'socket.io-client',
  'engine.io',
  'sockjs',
  'eventsource',
  'http-proxy',
  'http-proxy-middleware',
  'cors',
  'helmet',
  'compression',
  'body-parser',
  'cookie-parser',
  'multer',
  'formidable',
  'busboy',
  // DB·ORM
  'prisma',
  'typeorm',
  'sequelize',
  'knex',
  'mongoose',
  'mongodb',
  'pg',
  'mysql2',
  'sqlite3',
  'better-sqlite3',
  'redis',
  'ioredis',
  'drizzle-orm',
  'kysely',
  'objection',
  'bookshelf',
  'mikro-orm',
  'level',
  'lowdb',
  // 인증·보안
  'jsonwebtoken',
  'passport',
  'bcrypt',
  'bcryptjs',
  'argon2',
  'crypto-js',
  'node-forge',
  'jose',
  'oauth',
  'csurf',
  'express-rate-limiter',
  // CLI·터미널
  'yargs',
  'minimist',
  'meow',
  'inquirer',
  'prompts',
  'enquirer',
  'ora',
  'listr',
  'cli-table3',
  'boxen',
  'figlet',
  'gradient-string',
  'kleur',
  'picocolors',
  'ansi-colors',
  'strip-ansi',
  'cli-progress',
  'update-notifier',
  // 파일·경로
  'fs-extra',
  'glob',
  'fast-glob',
  'globby',
  'chokidar',
  'rimraf',
  'mkdirp',
  'del',
  'cpy',
  'archiver',
  'tar',
  'unzipper',
  'adm-zip',
  'yauzl',
  'path-to-regexp',
  'upath',
  'find-up',
  'pkg-dir',
  'read-pkg',
  // 데이터 포맷
  'papaparse',
  'csv-parse',
  'csv-stringify',
  'xlsx',
  'js-yaml',
  'yaml',
  'toml',
  'ini',
  'dotenv',
  'dotenv-expand',
  'xml2js',
  'fast-xml-parser',
  'cheerio',
  'jsdom',
  'marked',
  'markdown-it',
  'remark',
  'rehype',
  'unified',
  'gray-matter',
  'highlight.js',
  'prismjs',
  'shiki',
  // 이미지·미디어
  'sharp',
  'jimp',
  'canvas',
  'svgo',
  'imagemin',
  'qrcode',
  'jsbarcode',
  'fluent-ffmpeg',
  'pdfkit',
  'pdf-lib',
  'jspdf',
  'html2canvas',
  // 상태·데이터 페칭
  'redux',
  'react-redux',
  'redux-thunk',
  'redux-saga',
  'zustand',
  'jotai',
  'valtio',
  'recoil',
  'mobx',
  'xstate',
  'swr',
  'apollo-client',
  'graphql',
  'urql',
  'relay-runtime',
  'trpc',
  // React 생태
  'react-dom',
  'react-router-dom',
  'react-hook-form',
  'formik',
  'react-select',
  'react-table',
  'react-virtualized',
  'react-window',
  'framer-motion',
  'react-spring',
  'react-dnd',
  'react-beautiful-dnd',
  'styled-components',
  'emotion',
  'radix-ui',
  'headlessui',
  'chakra-ui',
  'antd',
  'material-ui',
  // 차트·시각화
  'd3',
  'chart.js',
  'echarts',
  'plotly.js',
  'recharts',
  'victory',
  'nivo',
  'apexcharts',
  'highcharts',
  'three',
  'pixi.js',
  'konva',
  'fabric',
  // 노드 런타임·프로세스
  'nodemon',
  'pm2',
  'concurrently',
  'cross-env',
  'npm-run-all',
  'execa',
  'shelljs',
  'zx',
  'node-cron',
  'bull',
  'bullmq',
  'agenda',
  'bree',
  'cluster',
  'piscina',
  'worker-farm',
  // 로깅·관측
  'winston-elasticsearch',
  'bunyan-format',
  'pino-elasticsearch',
  'debug-fabulous',
  'opentelemetry',
  'prom-client',
  'newrelic',
  'sentry',
  'rollbar',
  'bugsnag',
  // 국제화·접근성
  'i18next',
  'react-i18next',
  'formatjs',
  'intl-messageformat',
  'polyglot',
  'axe-core',
  'pa11y',
  // 타입 정의
  '@types/react',
  '@types/express',
  '@types/lodash',
  '@types/jest',
  '@types/jquery',
  '@types/uuid',
  '@types/cors',
  '@types/multer',
  // 기타 도구
  'semver',
  'validator',
  'sanitize-html',
  'dompurify',
  'he',
  'entities',
  'mime',
  'mime-types',
  'content-type',
  'accepts',
  'negotiator',
  'etag',
  'nodemailer',
  'sendgrid',
  'twilio',
  'stripe',
  'aws-sdk',
  'firebase',
  'axios-retry',
  'p-limit',
  'p-retry',
  'p-queue',
  'p-map',
  'async',
  'bluebird',
]

/**
 * 이름 → 결정적 정수. 값은 이 해시에서 파생된다.
 *
 * <b>정수만 쓴다.</b> 시드 SQL 이 같은 값을 `generate_series` 로 만들어야 해서다 —
 * 부동소수를 쓰면 TypeScript 와 PostgreSQL 의 마지막 자리가 갈리고, 그러면 mock 과
 * 서버가 미세하게 다른 숫자를 그린다. 그 차이는 "구현이 틀렸나?" 로 오해되기 딱 좋다.
 */
function nameHash(name: string): number {
  let h = 2166136261
  for (let i = 0; i < name.length; i++) {
    h ^= name.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return Math.abs(h | 0)
}

/**
 * 채움 패키지 하나를 만든다.
 *
 * 카탈로그 14개와 달리 시계열이 <b>1차식</b>이다 — `base + step * i`.
 * 곡선이 밋밋하지만 이 패키지들의 목적은 검색 목록을 채우는 것이지 차트를 보여주는
 * 것이 아니고, 1차식이라야 SQL 이 같은 값을 만들 수 있다.
 */
function makeFiller(name: string): MockPackage {
  const h = nameHash(name)

  // 인기 분포가 한쪽으로 쏠리게 한다 — 목록 앞쪽이 실제로 큰 값을 갖도록.
  const dlLatest = 20_000 + (h % 4_000_000)
  const dlStep = ((h >> 3) % 2000) - 400 // 주당 증감. 음수면 감소 추세
  const depLatest = 200 + (h % 30_000)
  const depStep = ((h >> 7) % 40) - 8

  // major 는 둘로만 나눈다. 나누는 비율이 `floor(v/3)` 과 `v - floor(v/3)` 이라
  // 정수 나눗셈만으로 끝나고, SQL 의 `/` 도 같은 값을 낸다(양수 절단).
  // 세 조각 이상으로 나누면 반올림이 끼어들어 두 구현이 갈릴 수 있다.
  const majorTop = 2 + ((h >> 11) % 7)
  const lower = Math.floor(depLatest / 3)
  const majors: MockMajor[] = [
    { major: String(majorTop), dependents: depLatest - lower },
    { major: String(majorTop - 1), dependents: lower },
  ].filter((m) => m.dependents > 0)

  return {
    name,
    repo_url: `https://github.com/example/${name.replace('@', '').replace('/', '-')}`,
    latest_version: `${majorTop}.${(h >> 5) % 20}.${(h >> 9) % 10}`,
    published_at: '2026-08-10T00:00:00Z',
    description: null,
    licenses: ['MIT'],
    is_deprecated: false,
    // 일부는 늦게 관측이 시작되게 한다 — 시리즈 길이가 다른 경우를 검색 결과에서도 만난다.
    startIndex: h % 5 === 0 ? 30 + (h % 40) : 0,
    downloads: dlLatest,
    downloadsGrowth: 0,
    dependents: depLatest,
    dependentsGrowth: 0,
    stars: 50 + (h % 40_000),
    starsPerWeek: (h >> 13) % 30,
    openIssues: h % 400,
    openIssuesPerWeek: 0,
    majors,
    filler: { dlStep, depStep },
  }
}

/**
 * 채움 패키지. 카탈로그 뒤에 붙는다.
 *
 * 중복을 코드로 지운다. 손으로 적은 300줄에서 같은 이름을 두 번 적는 것은 시간문제이고,
 * 그대로 두면 시드에서 PK 충돌로 터진다 — 그때는 원인이 목록 어딘가의 한 줄이라 찾기 번거롭다.
 */
export const FILLER_PACKAGES: MockPackage[] = [...new Set(FILLER_NAMES)]
  .filter((name) => !MOCK_PACKAGES.some((p) => p.name === name))
  .map(makeFiller)

/** 카탈로그 + 채움. 조회·검색이 보는 전체 목록. */
export const ALL_PACKAGES: MockPackage[] = [...MOCK_PACKAGES, ...FILLER_PACKAGES]

export const BY_NAME = new Map(ALL_PACKAGES.map((p) => [p.name, p]))

/**
 * 사전 파일(2.2) 대용.
 *
 * 실제 사전은 다운로드 상위 10만 개이고 **순서가 곧 인기순**이다.
 * mock 은 카탈로그를 다운로드 내림차순으로 세우고, 사전에만 있고 상세는 없는 이름을
 * 몇 개 섞는다 — 사전에서 고른 이름이 `not_found` 로 돌아오는 경로를 밟기 위한 것.
 */
export const MOCK_DICTIONARY: string[] = [
  // 카탈로그 + 채움을 다운로드 내림차순으로. 이 순서가 곧 인기순이다.
  ...[...ALL_PACKAGES].sort((a, b) => b.downloads - a.downloads).map((p) => p.name),
  // 아래는 사전에만 있고 상세는 없는 이름들 — 사전에서 고른 이름이 `not_found` 로
  // 돌아오는 경로를 화면에서 밟아보기 위한 것이다.
  // 'react' 처럼 누구나 칠 법한 이름을 일부러 여기 둔다. 자주 밟히는 편이 낫다.
  'react',
  'lodash',
  'axios',
  'chalk',
  'commander',
  'zod',
  'vite',
  'typescript',
  'eslint',
  'prettier',
  'expressive-code',
  'express-session',
  'express-validator',
  'express-rate-limit',
  'fastify-plugin',
  'koa-router',
  'koa-bodyparser',
  'pino-pretty',
  'pino-http',
  'winston-daily-rotate-file',
  'winston-transport',
]

/** 최신 스냅샷 인덱스 기준 i 주 전 값. `growth` 는 주당 복리로 본다. */
function backcast(latest: number, growth: number, weeksAgo: number, seed: number): number {
  const base = latest / Math.pow(1 + growth, weeksAgo)
  const noise = wobble(seed, weeksAgo) * base * 0.004
  return Math.max(0, Math.round(base + noise))
}

const seedOf = (name: string) => [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 97

/**
 * 한 패키지의 지표 시계열. 관측 시작 이전 스냅샷은 **행 자체가 없다**.
 * 0 으로 채우지 않는다 — 없는 관측을 있는 것처럼 만들면 안 된다.
 */
export function seriesOf(
  pkg: MockPackage,
  metric: 'downloads' | 'dependents',
): { snapshot_at: string; value: number }[] {
  if (pkg.noSnapshot) return []

  // 채움 패키지는 1차식이다. 정수만 쓰므로 시드 SQL 이 같은 값을 만들 수 있다.
  if (pkg.filler) {
    const latestValue = metric === 'downloads' ? pkg.downloads : pkg.dependents
    const step = metric === 'downloads' ? pkg.filler.dlStep : pkg.filler.depStep
    const last = ALL_SNAPSHOTS.length - 1
    return ALL_SNAPSHOTS.slice(pkg.startIndex).map((snapshot_at, i) => ({
      snapshot_at,
      value: Math.max(0, latestValue - step * (last - (pkg.startIndex + i))),
    }))
  }

  const latest = metric === 'downloads' ? pkg.downloads : pkg.dependents
  const growth = metric === 'downloads' ? pkg.downloadsGrowth : pkg.dependentsGrowth
  const seed = seedOf(pkg.name) + (metric === 'downloads' ? 0 : 31)
  const last = ALL_SNAPSHOTS.length - 1

  return ALL_SNAPSHOTS.slice(pkg.startIndex).map((snapshot_at, i) => ({
    snapshot_at,
    value: backcast(latest, growth, last - (pkg.startIndex + i), seed),
  }))
}

/**
 * dependents 를 major 별로 쪼갠다 (§5).
 *
 * **날짜마다 조각의 합이 `seriesOf(pkg, 'dependents')` 와 정확히 같다.** 마지막 조각이
 * 나머지를 받아 반올림 오차를 흡수한다. 화면의 `TOTAL` 이 이 덧셈을 그대로 하므로,
 * 여기가 어긋나면 mock 과 실서버의 숫자가 달라진다.
 *
 * **지분을 고정하지 않는다.** 고정하면 모든 major 가 똑같은 모양으로 오르내려서
 * "새 버전이 퍼지고 구버전이 물러난다" 는 그림이 나오지 않고, 버전 선택기를 눌러도
 * 곡선 모양이 같아 화면이 제대로 도는지 알 수 없다. 그래서 최신 major 는 0 에서 자라고
 * 구버전은 서서히 물러나게 한다 — `majors` 의 값은 **마지막 스냅샷의 상태**다.
 *
 * 서버와 같은 규칙으로 **앞쪽 0 은 잘라내고 뒤쪽 0 은 남긴다.** 아직 나오지 않은 버전이
 * 바닥에 깔리면 "2년 전부터 있었다" 가 되고, 쇠퇴해 0 에 닿은 버전을 빼면 선이 끊긴다.
 */
export function dependentsByMajor(
  pkg: MockPackage,
): { major: string; points: { snapshot_at: string; value: number }[] }[] {
  const total = seriesOf(pkg, 'dependents')
  if (total.length === 0 || pkg.majors.length === 0) return []

  // 최신 major 가 앞. 서버가 숫자로 정렬해 보내는 순서와 맞춘다.
  const majors = [...pkg.majors].sort((a, b) => numericMajor(b.major) - numericMajor(a.major))
  const last = total.length - 1

  const rows = majors.map((m) => ({ major: m.major, points: [] as typeof total }))

  total.forEach((point, i) => {
    // 0 → 1 로 가는 시간. 마지막 스냅샷에서 t = 1 이라 지분이 `majors` 그대로가 된다.
    const t = last === 0 ? 1 : i / last
    const weights = majors.map(
      (m, k) =>
        k === 0
          ? m.dependents * t // 최신 major 는 0 에서 자란다
          : m.dependents * (1 + (1 - t) * 0.6), // 구버전은 예전에 더 두터웠다
    )
    const sum = weights.reduce((a, b) => a + b, 0)

    let assigned = 0
    weights.forEach((w, k) => {
      const value =
        k === weights.length - 1
          ? point.value - assigned // 나머지. 합이 정확히 맞는다
          : sum === 0
            ? 0
            : Math.round((point.value * w) / sum)
      assigned += value
      rows[k].points.push({ snapshot_at: point.snapshot_at, value: Math.max(0, value) })
    })
  })

  return rows
    .map((r) => {
      const first = r.points.findIndex((p) => p.value > 0)
      return { major: r.major, points: first < 0 ? [] : r.points.slice(first) }
    })
    .filter((r) => r.points.length > 0)
}

/** 숫자가 아닌 major 는 뒤로 보낸다. 서버 SQL 의 정렬 규칙과 같다. */
function numericMajor(major: string): number {
  return /^\d{1,9}$/.test(major) ? Number(major) : -1
}

/** 스냅샷 시점의 stars / open_issues. 직전 대비 증감을 만들기 위해 필요하다. */
export function pointMetric(
  pkg: MockPackage,
  metric: 'stars' | 'open_issues',
  snapshotIndex: number,
): number | null {
  if (pkg.noSnapshot) return null
  if (snapshotIndex < pkg.startIndex) return null
  if (!pkg.repo_url) return null

  const last = ALL_SNAPSHOTS.length - 1
  const weeksAgo = last - snapshotIndex

  // 채움 패키지는 흔들림 없이 1차식이다. 시드 SQL 이 같은 값을 만들 수 있어야 한다.
  if (pkg.filler) {
    return metric === 'stars'
      ? Math.max(0, pkg.stars - pkg.starsPerWeek * weeksAgo)
      : pkg.openIssues
  }
  const [latest, perWeek] =
    metric === 'stars' ? [pkg.stars, pkg.starsPerWeek] : [pkg.openIssues, pkg.openIssuesPerWeek]

  const seed = seedOf(pkg.name) + (metric === 'stars' ? 7 : 53)
  const base = latest - perWeek * weeksAgo
  return Math.max(0, Math.round(base + wobble(seed, weeksAgo) * Math.abs(perWeek) * 0.8))
}

/* ------------------------------------------------------------------ *
 * S15P21A506-361·391. 유지·유입·이탈 — mock 원본
 *
 * 값은 지어낸 것이지만 **네 가지 `data_status` 를 전부 실제로 볼 수 있게** 고른다 —
 * mock 만 돌려서는 COMPLETE 하나만 보고 끝나기 쉬워서, 나머지 셋을 기본 비교 패키지
 * (winston·pino·bunyan) 안에 의도적으로 흩어 둔다.
 * ------------------------------------------------------------------ */

export interface MockTransitionCounts {
  retained: number
  inflow: number
  inflowNew: number
  outflow: number
  unobserved: number
}

export interface MockTransitionRow {
  kind: 'regular' | 'peer' | 'optional'
  dataStatus: 'COMPLETE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'
  /** COMPLETE·NO_DATA 일 때만 채운다 — 그 밖엔 서버처럼 값이 없다(null). */
  counts?: MockTransitionCounts
  /**
   * 관측불가 분해 세 값만 `null` 로 내는 행 (S15P21A506-421·431). **`data_status` 와 독립된
   * 상태**라 `COMPLETE` 인데 셋만 없는 행이 실제로 존재한다 — 마이그레이션이 배포된 뒤
   * 88만 행 재적재가 끝나기 전까지가 그 창이고, 스냅샷 회차마다 다시 생긴다.
   * 화면이 그때 0 으로 그리지 않는지를 mock 만으로 확인할 수 있게 한 건 남겨 둔다.
   */
  freshnessMissing?: true
}

/**
 * winston — regular 는 COMPLETE(원시 inflow 와 실제 채택 수 차이가 크게 보이도록 잡았다),
 * peer 는 NO_DATA(진짜 0), optional 은 COMPLETE(작은 값)이되 **관측불가 분해만 없는 행**이다
 * (`freshnessMissing`, S15P21A506-431).
 *
 * pino — regular 만 COMPLETE, peer·optional 은 OUT_OF_SCOPE(top-100k 밖).
 *
 * bunyan — 세 kind 전부 NOT_COMPUTED. bunyan 하나만 조회하면 응답 전체가 NOT_COMPUTED 뿐이라
 * 서버 계약대로 `t1`·`t2` 키 자체가 없어지는 경우를 재현한다(다른 패키지와 같이 조회하면
 * 그쪽에 COMPLETE 행이 있어 t1·t2 는 정상적으로 나간다).
 */
export const MOCK_TRANSITIONS: Record<string, MockTransitionRow[]> = {
  winston: [
    {
      kind: 'regular',
      dataStatus: 'COMPLETE',
      counts: { retained: 4180, inflow: 9840, inflowNew: 9240, outflow: 980, unobserved: 3120 },
    },
    {
      kind: 'peer',
      dataStatus: 'NO_DATA',
      counts: { retained: 0, inflow: 0, inflowNew: 0, outflow: 0, unobserved: 0 },
    },
    {
      kind: 'optional',
      dataStatus: 'COMPLETE',
      counts: { retained: 118, inflow: 342, inflowNew: 312, outflow: 46, unobserved: 88 },
      // 분해 셋만 없는 행 — 화면은 이 줄에서 하위 막대를 아예 그리지 않아야 한다.
      freshnessMissing: true,
    },
  ],
  pino: [
    {
      kind: 'regular',
      dataStatus: 'COMPLETE',
      counts: { retained: 2610, inflow: 5120, inflowNew: 4720, outflow: 612, unobserved: 1904 },
    },
    { kind: 'peer', dataStatus: 'OUT_OF_SCOPE' },
    { kind: 'optional', dataStatus: 'OUT_OF_SCOPE' },
  ],
  bunyan: [
    { kind: 'regular', dataStatus: 'NOT_COMPUTED' },
    { kind: 'peer', dataStatus: 'NOT_COMPUTED' },
    { kind: 'optional', dataStatus: 'NOT_COMPUTED' },
  ],
}

/**
 * 이탈 사유 픽스처 (S15P21A506-396·410). `MOCK_TRANSITIONS` 와 달리 **한 패키지가 한 줄**이다.
 *
 * 네 `data_status` 를 전부 덮는다 — 화면이 넷을 다르게 그리는지 mock 만으로 확인할 수 있게.
 *
 * winston — COMPLETE(큰 값).  pino — COMPLETE(작은 값).
 * log4js — **NO_DATA(전부 0)**. 운영에서 대상의 58.5%가 이 상태라 가장 흔한 화면이다.
 *          0 으로 그려야 하며 "분석 대상 아님" 으로 뭉개면 안 된다.
 * morgan — OUT_OF_SCOPE(top-100k 밖).
 * bunyan — NOT_COMPUTED. 혼자 조회하면 `t1`·`t2` 키 자체가 없어지는 경우를 재현한다.
 *
 * `removals` 를 적어 두지 않는 이유 — 기간 배율을 곱하면 반올림 때문에
 * `round(no*s) + round(with*s) != round(removals*s)` 가 될 수 있다. 서버에는
 * `no_replacement + with_replacement = removals` DB CHECK 가 걸려 있으므로,
 * mock 도 **두 값을 스케일한 뒤 더해서** removals 를 만든다(handlers.ts).
 */
export interface MockRemovalReason {
  dataStatus: 'COMPLETE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'
  /** COMPLETE·NO_DATA 일 때만 있다. `dependents <= removals` 를 지켜 둔다(DB CHECK). */
  counts?: { noReplacement: number; withReplacement: number; dependents: number }
}

export const MOCK_REMOVAL_REASONS: Record<string, MockRemovalReason> = {
  winston: {
    dataStatus: 'COMPLETE',
    counts: { noReplacement: 1290, withReplacement: 550, dependents: 1622 },
  },
  pino: {
    dataStatus: 'COMPLETE',
    counts: { noReplacement: 286, withReplacement: 126, dependents: 377 },
  },
  log4js: {
    dataStatus: 'NO_DATA',
    counts: { noReplacement: 0, withReplacement: 0, dependents: 0 },
  },
  morgan: { dataStatus: 'OUT_OF_SCOPE' },
  bunyan: { dataStatus: 'NOT_COMPUTED' },
}

/**
 * 관측된 교체 흐름 픽스처 (S15P21A506-424).
 *
 * 다섯 `data_status` 를 전부 덮는다 — 화면이 다섯을 다르게 그리는지 mock 만으로 확인할 수
 * 있게. 기본 비교 3개(winston·pino·bunyan)에 COMPLETE 둘과 NOT_COMPUTED 하나가 들어간다.
 *
 * **점유율 합이 100 이 아니도록 일부러 만들어 두었다.** 실측이 그렇다 — `share_pm_pct` 의
 * 분모는 빌더가 `lift>=5` 인 쌍 전체로 잡는데 표에는 loose(`votes>=3`)만 적재되므로, 출발
 * 패키지의 79.7%가 합 99.5% 에 못 미치고 중앙값이 25.7% 다. mock 이 100 을 채우면 화면이
 * 정규화해도 티가 안 나서, **실제 데이터를 붙이는 날 조용히 네 배 부풀려진다.**
 *
 * winston — COMPLETE(5개 + 그 밖). **실제 moment 의 모양을 그대로 옮겼다** — 상위 5가
 *           11.8%, 그 밖 9.9% → 합 21.7%, 빗금 78%. 처음에는 합을 63.8% 로 두었는데,
 *           4층 검증(2026-09-22)에서 실제 대표 사례가 21.7~44.4% 인 것이 확인됐다.
 *           mock 이 더 후하면 리뷰어가 화면의 진짜 모습을 못 본다.
 * pino    — COMPLETE(2개, 접을 것 없음 → `etc` 는 null).
 * bunyan  — NOT_COMPUTED. 그 종류의 회차를 아직 안 올렸다.
 * log4js  — INSUFFICIENT_EVIDENCE. **쌍은 있는데 전부 근거 미달이라 `destinations` 가 비고
 *           `etc` 에만 들어 있다.** NO_DATA 와 문구가 반대라 반드시 갈라야 한다.
 * loglevel— NO_DATA. 자료는 있는데 이동이 관측되지 않았다.
 * morgan  — OUT_OF_SCOPE. `available_package` 에 없다 — 기다려도 안 온다.
 */
export interface MockMigrationDestination {
  name: string
  votes: number
  coEvents: number
  publisherMonths: number
  dependents: number
  lift: number
  sharePmPct: number
  sharePct: number
  /** 그 패키지를 지운 경우 중 이것을 함께 넣은 비율. 화면이 배지 옆에 그대로 적는다. */
  aPct: number
  evidence: 'strict' | 'recommended' | 'loose'
  variant?: boolean
  firstSeen: string
  lastSeen: string
}

export interface MockMigrationPairs {
  dataStatus: 'COMPLETE' | 'INSUFFICIENT_EVIDENCE' | 'NO_DATA' | 'OUT_OF_SCOPE' | 'NOT_COMPUTED'
  destinations?: MockMigrationDestination[]
  etc?: { pairs: number; sharePmPct: number; belowFilter: number }
  /** 필터 전 관측된 쌍의 수. COMPLETE·INSUFFICIENT·NO_DATA 일 때만 값이 있다. */
  observedPairs?: number
}

const dest = (
  name: string,
  votes: number,
  publisherMonths: number,
  sharePmPct: number,
  evidence: 'strict' | 'recommended' | 'loose',
  extra: Partial<MockMigrationDestination> = {},
): MockMigrationDestination => ({
  name,
  votes,
  coEvents: Math.round(votes * 1.6),
  publisherMonths,
  dependents: Math.round(votes * 1.2),
  lift: Math.round(votes * 40),
  sharePmPct,
  sharePct: sharePmPct + 2.4,
  // 실측에서 a_pct 는 share_pm_pct 보다 훨씬 크다(moment→dayjs 는 5.7% vs 20.8%).
  // 분모가 도착지들이 아니라 이탈 전체이기 때문이다. 배수를 흉내만 낸다.
  aPct: Math.round(sharePmPct * 3.6 * 10) / 10,
  evidence,
  firstSeen: '2019-03-11',
  lastSeen: '2026-07-28',
  ...extra,
})

/** 실행용 의존 기준(deps.dev 전수, 기준일 2026-08-31). */
export const MOCK_MIGRATION_PAIRS_REGULAR: Record<string, MockMigrationPairs> = {
  winston: {
    dataStatus: 'COMPLETE',
    // 실제 moment 는 53쌍 중 26개가 기본 필터를 통과하고 그중 5개만 이름을 세운다.
    observedPairs: 53,
    destinations: [
      dest('pino', 347.4, 384, 5.7, 'strict', { variant: true }),
      dest('bunyan', 166.5, 204, 3.0, 'strict'),
      dest('consola', 91.9, 98, 1.4, 'strict', { variant: true }),
      dest('loglevel', 64.9, 67, 1.0, 'strict'),
      dest('winston-daily-rotate-file', 16.7, 49, 0.7, 'loose'),
    ],
    etc: { pairs: 48, sharePmPct: 9.9, belowFilter: 27 },
  },
  pino: {
    dataStatus: 'COMPLETE',
    observedPairs: 9,
    destinations: [
      dest('winston', 20.5, 14, 31.0, 'recommended', { variant: true }),
      dest('pino-pretty', 8.0, 6, 12.5, 'loose', { variant: true }),
    ],
    etc: { pairs: 7, sharePmPct: 0.9, belowFilter: 7 },
  },
  bunyan: { dataStatus: 'NOT_COMPUTED' },
  log4js: {
    dataStatus: 'INSUFFICIENT_EVIDENCE',
    observedPairs: 3,
    etc: { pairs: 3, sharePmPct: 11.9, belowFilter: 3 },
  },
  loglevel: { dataStatus: 'NO_DATA', observedPairs: 0 },
  morgan: { dataStatus: 'OUT_OF_SCOPE' },
}

/**
 * 개발용 의존 기준(npm registry 상위 10만, 기준일 2026-09-16).
 *
 * **같은 패키지라도 도착지가 다르다.** 종류를 바꿨을 때 화면이 실제로 다른 것을 그리는지,
 * 기준일 캡션이 함께 바뀌는지 mock 으로 확인하려는 것이다. 여기 없는 이름은
 * `NOT_COMPUTED` 로 떨어진다 — 운영에서도 dev 회차는 아직 적재 전이다.
 */
export const MOCK_MIGRATION_PAIRS_DEV: Record<string, MockMigrationPairs> = {
  winston: {
    dataStatus: 'COMPLETE',
    observedPairs: 4,
    destinations: [dest('pino', 12.0, 9, 18.2, 'recommended'), dest('debug', 7.5, 6, 9.4, 'loose')],
    etc: { pairs: 2, sharePmPct: 5.1, belowFilter: 1 },
  },
  pino: { dataStatus: 'NO_DATA', observedPairs: 0 },
  morgan: { dataStatus: 'OUT_OF_SCOPE' },
}

/** 종류마다 기준일이 다르다. 16일 차이가 화면 캡션에 그대로 드러나야 한다. */
export const MOCK_MIGRATION_SNAPSHOT: Record<'regular' | 'dev', string> = {
  regular: '2026-08-31',
  dev: '2026-09-16',
}

/** 기간이 길어질수록 유지·유입·이탈 절대량이 느는 정도만 흉내낸다. 값의 의미는 안 바뀐다. */
export const TRANSITION_PERIOD_SCALE: Record<'1y' | '3y' | '5y', number> = {
  '1y': 0.4,
  '3y': 1,
  '5y': 1.6,
}
