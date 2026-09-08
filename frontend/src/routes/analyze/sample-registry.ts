/**
 * 화면-01·02 를 붙여보기 위한 임시 레지스트리.
 *
 * 미해결: Spring 이 붙으면 `usePackageResolution` · `useCandidates` 로 갈아끼운다.
 * 후보 응답 모양은 구상안 4.3 을 그대로 따른다 — 후보에 버전을 넣지 않는다.
 */

export interface RegistryEntry {
  name: string
  description: string
  keywords: string[]
  publishedAt: string
}

/** 검색이 그럴듯하게 동작하도록 로거 주변을 넉넉히 채웠다. */
export const REGISTRY: RegistryEntry[] = [
  {
    name: 'winston',
    description: 'A logger for just about everything',
    keywords: ['logger', 'logging', 'json'],
    publishedAt: '2026-07-14',
  },
  {
    name: 'pino',
    description: 'Fast JSON logger for Node.js',
    keywords: ['logger', 'logging', 'json'],
    publishedAt: '2026-08-21',
  },
  {
    name: 'bunyan',
    description: 'A simple and fast JSON logging module',
    keywords: ['logger', 'json', 'stream'],
    publishedAt: '2025-12-03',
  },
  {
    name: 'log4js',
    description: 'Port of Log4js to work with Node.js',
    keywords: ['logger', 'appenders', 'level'],
    publishedAt: '2026-06-15',
  },
  {
    name: 'loglevel',
    description: 'Minimal lightweight logging for JavaScript',
    keywords: ['logger', 'level', 'browser'],
    publishedAt: '2026-03-02',
  },
  {
    name: 'morgan',
    description: 'HTTP request logger middleware for node.js',
    keywords: ['logger', 'http', 'middleware'],
    publishedAt: '2025-09-18',
  },
  {
    name: 'debug',
    description: 'Lightweight debugging utility',
    keywords: ['debug', 'logger'],
    publishedAt: '2026-05-27',
  },
  {
    name: 'signale',
    description: 'Highly configurable logging utility',
    keywords: ['logger', 'cli'],
    publishedAt: '2024-08-09',
  },
  {
    name: 'consola',
    description: 'Elegant console logger',
    keywords: ['logger', 'console'],
    publishedAt: '2026-07-30',
  },
  {
    name: 'tslog',
    description: 'Powerful, fast and expressive logging for TypeScript',
    keywords: ['logger', 'typescript'],
    publishedAt: '2026-04-11',
  },
  {
    name: 'roarr',
    description: 'JSON logger for Node.js and browser',
    keywords: ['logger', 'json'],
    publishedAt: '2026-01-22',
  },
  {
    name: 'npmlog',
    description: 'Logger for npm',
    keywords: ['logger', 'npm'],
    publishedAt: '2024-02-14',
  },
  {
    name: 'express',
    description: 'Fast, unopinionated, minimalist web framework',
    keywords: ['web', 'framework', 'http'],
    publishedAt: '2026-06-02',
  },
  {
    name: 'fastify',
    description: 'Fast and low overhead web framework',
    keywords: ['web', 'framework', 'http'],
    publishedAt: '2026-08-05',
  },
  {
    name: 'koa',
    description: 'Koa web app framework',
    keywords: ['web', 'framework'],
    publishedAt: '2026-02-19',
  },
  {
    name: 'moment',
    description: 'Parse, validate, manipulate, and display dates',
    keywords: ['date', 'time', 'parse'],
    publishedAt: '2025-11-20',
  },
  {
    name: 'dayjs',
    description: 'Fast 2kB immutable date-time library',
    keywords: ['date', 'time', 'immutable'],
    publishedAt: '2026-07-08',
  },
  {
    name: 'date-fns',
    description: 'Modern JavaScript date utility library',
    keywords: ['date', 'time', 'functional'],
    publishedAt: '2026-08-12',
  },
  {
    name: 'luxon',
    description: 'Immutable date wrapper with time zone support',
    keywords: ['date', 'time', 'timezone'],
    publishedAt: '2026-05-04',
  },
  {
    name: 'lodash',
    description: 'Lodash modular utilities',
    keywords: ['utility', 'functional'],
    publishedAt: '2026-02-08',
  },
  {
    name: 'axios',
    description: 'Promise based HTTP client',
    keywords: ['http', 'client', 'ajax'],
    publishedAt: '2026-08-01',
  },
  {
    name: 'zod',
    description: 'TypeScript-first schema validation',
    keywords: ['schema', 'validation', 'typescript'],
    publishedAt: '2026-08-25',
  },
]

const BY_NAME = new Map(REGISTRY.map((e) => [e.name, e]))
export const findPackage = (name: string) => BY_NAME.get(name)

export type MatchKind = 'EXACT' | 'PREFIX' | 'CONTAINS' | 'KEYWORD' | 'SIMILAR'

export interface SearchHit {
  entry: RegistryEntry
  kind: MatchKind
  /** 이름에서 질의와 겹치는 구간. 하이라이트에 쓴다. */
  hit?: [number, number]
}

/** 오타 한두 개까지만 잡는 편집 거리. */
function distance(a: string, b: string): number {
  const m = a.length
  const n = b.length
  if (Math.abs(m - n) > 2) return 99
  let prev = Array.from({ length: n + 1 }, (_, j) => j)
  for (let i = 1; i <= m; i++) {
    const cur = [i]
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
    }
    prev = cur
  }
  return prev[n]
}

const ORDER: Record<MatchKind, number> = {
  EXACT: 0,
  PREFIX: 1,
  CONTAINS: 2,
  KEYWORD: 3,
  SIMILAR: 4,
}

/**
 * 이름이 같거나 가까운 순으로 찾는다.
 *
 * 이름 일치 → 접두 → 포함 → 키워드 → 오타 순이다.
 * 레지스트리 검색이지 후보 추천이 아니다. 어느 쪽이 낫다는 정렬을 하지 않는다.
 */
export function searchPackages(query: string, limit = 8): SearchHit[] {
  const q = query.trim().toLowerCase()
  if (!q) return []

  const hits: SearchHit[] = []
  for (const entry of REGISTRY) {
    const name = entry.name.toLowerCase()
    if (name === q) {
      hits.push({ entry, kind: 'EXACT', hit: [0, name.length] })
      continue
    }
    if (name.startsWith(q)) {
      hits.push({ entry, kind: 'PREFIX', hit: [0, q.length] })
      continue
    }
    const at = name.indexOf(q)
    if (at > 0) {
      hits.push({ entry, kind: 'CONTAINS', hit: [at, at + q.length] })
      continue
    }
    if (q.length >= 3 && entry.keywords.some((k) => k.includes(q))) {
      hits.push({ entry, kind: 'KEYWORD' })
      continue
    }
    if (q.length >= 4 && distance(name, q) <= 2) {
      hits.push({ entry, kind: 'SIMILAR' })
    }
  }

  return hits
    .sort((a, b) => ORDER[a.kind] - ORDER[b.kind] || a.entry.name.localeCompare(b.entry.name))
    .slice(0, limit)
}

export const MATCH_LABEL: Record<MatchKind, string> = {
  EXACT: '이름 일치',
  PREFIX: '이름 시작',
  CONTAINS: '이름 포함',
  KEYWORD: '키워드 일치',
  SIMILAR: '비슷한 이름',
}

/** 후보 카드 (구상안 4.3). 버전은 담지 않는다. */
export interface Candidate {
  package: string
  descriptionSimilarity: number
  sharedKeywords: string[]
  publishedAt: string
  /** 구상안 4.3 dataStatus. 카드 하단 상태 표시로 쓴다. */
  dataStatus: 'READY' | 'PARTIAL'
  defaultSelected: boolean
}

export const CANDIDATES: Record<string, Candidate[]> = {
  winston: [
    {
      package: 'pino',
      descriptionSimilarity: 0.92,
      sharedKeywords: ['logger', 'logging', 'json'],
      publishedAt: '2026.08.21',
      dataStatus: 'READY',
      defaultSelected: true,
    },
    {
      package: 'bunyan',
      descriptionSimilarity: 0.86,
      sharedKeywords: ['logger', 'json', 'stream'],
      publishedAt: '2025.12.03',
      dataStatus: 'PARTIAL',
      defaultSelected: true,
    },
    {
      package: 'log4js',
      descriptionSimilarity: 0.81,
      sharedKeywords: ['logger', 'appenders', 'level'],
      publishedAt: '2026.06.15',
      dataStatus: 'READY',
      defaultSelected: false,
    },
  ],
}

export const MAX_COMPARISON = 3

/** 확인 지연 흉내. 실제로는 레지스트리 왕복이다. */
export const FAKE_LATENCY_MS = 550
