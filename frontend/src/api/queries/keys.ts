/**
 * react-query 키.
 *
 * 배치 엔드포인트라 키에 **이름 배열**이 들어간다. §7 이 지적한 대로
 * `[express, fastify]` 와 `[fastify, express]` 는 서로 다른 캐시 항목이 되므로,
 * 키를 만들 때 정렬해서 조합 순서 때문에 같은 데이터를 두 번 받지 않게 한다.
 * (서버 URL 은 요청 순서를 유지한다 — 응답 정렬이 요청 순서를 따르기 때문이다.)
 */

const sorted = (names: readonly string[]) => [...names].sort()

export const queryKeys = {
  dict: {
    all: ['dict'] as const,
    manifest: () => [...queryKeys.dict.all, 'manifest'] as const,
    file: (url: string) => [...queryKeys.dict.all, 'file', url] as const,
  },
  packages: {
    all: ['packages'] as const,
    search: (q: string, limit?: number) =>
      [...queryKeys.packages.all, 'search', q, limit ?? null] as const,
    overview: (names: readonly string[]) =>
      [...queryKeys.packages.all, 'overview', sorted(names)] as const,
    downloads: (names: readonly string[], from?: string, to?: string) =>
      [...queryKeys.packages.all, 'downloads', sorted(names), from ?? null, to ?? null] as const,
    dependents: (names: readonly string[], from?: string, to?: string) =>
      [...queryKeys.packages.all, 'dependents', sorted(names), from ?? null, to ?? null] as const,
    versionShare: (names: readonly string[], snapshotAt?: string) =>
      [...queryKeys.packages.all, 'version', sorted(names), snapshotAt ?? null] as const,
    transitions: (names: readonly string[], period?: string) =>
      [...queryKeys.packages.all, 'transitions', sorted(names), period ?? null] as const,
    removalReasons: (names: readonly string[], period?: string) =>
      [...queryKeys.packages.all, 'removal-reasons', sorted(names), period ?? null] as const,
    // 구간이 아니라 **종류**가 키에 들어간다. 두 값은 모집단이 다른 별개의 실행이라
    // 같은 이름이어도 캐시를 공유하면 안 된다.
    migrationPairs: (names: readonly string[], kind?: string) =>
      [...queryKeys.packages.all, 'migration-pairs', sorted(names), kind ?? null] as const,
    // 유사 패키지만 이름이 하나다. 정렬할 배열이 없으므로 그대로 넣는다.
    similar: (name: string, limit?: number) =>
      [...queryKeys.packages.all, 'similar', name, limit ?? null] as const,
  },
  report: {
    all: ['report'] as const,
    // 생성은 뮤테이션이라 키가 없다. 미리보기만 캐시한다 — 같은 보고서는 내용이 안 바뀐다.
    preview: (reportId: string) => [...queryKeys.report.all, 'preview', reportId] as const,
  },
  features: {
    all: ['features'] as const,
    // 결과는 캐시하지 않는다(뮤테이션). 버전 목록만 키가 있다.
    versions: (names: readonly string[]) =>
      [...queryKeys.features.all, 'versions', sorted(names)] as const,
    // 소비 조건은 배치 산출물이라 캐시해도 된다 — 같은 (이름, 버전) 이면 값이 안 바뀐다.
    env: (refs: readonly string[]) => [...queryKeys.features.all, 'env', sorted(refs)] as const,
    // run 은 식별자로 캐시한다. 결과 자체는 캐시하지 않는다(DEC-FEATURE-CACHE-20260917-01).
    run: (runId: string) => [...queryKeys.features.all, 'run', runId] as const,
  },
  community: {
    all: ['community'] as const,
    // 기준 패키지 하나에 대한 조회라 이름 하나만 키에 들어간다(§316).
    status: (name: string) => [...queryKeys.community.all, 'status', name] as const,
  },
} as const
