/**
 * GitHub 커뮤니티 현황 mock (S15P21A506-316).
 *
 * `handlers.ts`와 별도 파일이다 — 이 기능만 **폴링에 따라 진행되는 서버 registry**를
 * 흉내내야 한다(QUEUED → RUNNING(단계별) → COMPLETED). 진행은 실제 시계가 아니라
 * **GET 호출 횟수**로 미룬다 — 난수도 실제 타이머도 쓰지 않아야 새로고침·테스트에서
 * 항상 같은 순서로 재현된다(기존 mock 관례).
 *
 * 개발 중 화면을 확인할 때 쓰는 이름:
 * - `winston` — 이미 수집된 RESULT/FRESH (재진입 시나리오)
 * - `pino` — RESULT 이지만 요약 일부 실패(PARTIAL) + `summary_retry_at`
 * - `bunyan` — 저장소는 확인됐지만 논의 없음(NO_DISCUSSION_DATA)
 * - `express` — 저장소 연결 자체를 확인 못함(UNVERIFIED_REPOSITORY)
 * - `koa` — POST 가 항상 용량 초과로 거절됨(CAPACITY_LIMITED, refresh_id=null)
 * - 그 외 이름 — IDLE 에서 시작해 POST 후 GET 을 반복하면 QUEUED→RUNNING(6단계)→RESULT
 */

import { ApiError } from '@/api/client'
import { BY_NAME } from '@/api/mock/dataset'
import { NPM_NAME_RE } from '@/api/types'
import type {
  CommunityDataLimits,
  CommunityLimitation,
  CommunityRefreshInfo,
  CommunityRefreshStage,
  CommunityRefreshTrigger,
  CommunityRepository,
  CommunityResult,
  CommunityStatusResponse,
  CommunityTopic,
} from '@/api/types'

const fail = (code: 'V001' | 'V004', message: string): never => {
  throw new ApiError(400, code, message)
}

const LATENCY_MS = 220
const delay = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), LATENCY_MS))

const FRESH_MS = 24 * 60 * 60_000
const SERVE_MS = 7 * 24 * 60 * 60_000

const STAGES: CommunityRefreshStage[] = [
  'VERIFYING_REPOSITORY',
  'SEARCHING_ISSUES',
  'COLLECTING_COMMENTS',
  'SUMMARIZING',
  'VALIDATING',
  'PUBLISHING',
]

const STAGE_MESSAGE: Record<CommunityRefreshStage, string> = {
  VERIFYING_REPOSITORY: '저장소를 확인하는 중입니다.',
  SEARCHING_ISSUES: 'Issue를 찾는 중입니다.',
  COLLECTING_COMMENTS: '댓글을 모으는 중입니다.',
  SUMMARIZING: '요약을 만드는 중입니다.',
  VALIDATING: '요약을 검증하는 중입니다.',
  PUBLISHING: '결과를 게시하는 중입니다.',
}

const DATA_LIMITS: CommunityDataLimits = {
  policy_version: 'github-active-v1',
  lookback_days: 180,
  max_issues: 2,
  max_comments_per_issue: 100,
  max_messages_per_issue: 4,
  source_note: '수치는 선택한 Issue 집합의 값이며 저장소 전체나 고유 참여자 수가 아닙니다.',
}

/** 진행 중(QUEUED/RUNNING) task. `stageIndex` -1 이 QUEUED, 0~5 가 STAGES 인덱스. */
interface MockTask {
  refreshId: string
  trigger: CommunityRefreshTrigger
  stageIndex: number
  startedAt: string
}

const tasks = new Map<string, MockTask>()
const results = new Map<string, CommunityResult>()

/** `koa` 는 항상 이 상태를 보여주기 위한 고정 데모 이름이다. */
const CAPACITY_DEMO_NAME = 'koa'

/**
 * 데모용 이름은 "이미 수집됨" 상태로 미리 채워 둔다 — 그래야 개발 중 화면 확인이
 * 매번 6단계 진행을 기다리지 않고 바로 RESULT 를 본다(재진입 시나리오).
 * `fixtureResult` 는 아래 정의돼 있지만 함수 선언이라 호이스팅되어 여기서 바로 쓸 수 있다.
 */
for (const seedName of ['winston', 'pino', 'bunyan', 'express']) {
  const seeded = fixtureResult(seedName)
  if (seeded) results.set(seedName, seeded)
}

function now(): string {
  return new Date().toISOString()
}

function repositoryOf(name: string): CommunityRepository {
  const pkg = BY_NAME.get(name)
  const owner = pkg?.repo_url?.match(/github\.com\/([^/]+)\//)?.[1] ?? name
  return {
    owner,
    name,
    full_name: `${owner}/${name}`,
    scope: 'PACKAGE_SCOPED',
    archived: false,
    issue_count: 1234,
    open_issue_count: 56,
  }
}

function topic(
  overrides: Partial<CommunityTopic> & Pick<CommunityTopic, 'issue_number'>,
): CommunityTopic {
  return {
    state: 'OPEN',
    updated_at: '2026-09-10T00:00:00Z',
    created_at: '2026-09-01T00:00:00Z',
    title_original: 'Configuration question',
    title_ko: null,
    comments_count: 0,
    reactions_count: 0,
    collection_status: 'COMPLETE',
    summary_status: 'SKIPPED',
    summary_ko: null,
    messages: [],
    summary_marks: [],
    ...overrides,
  }
}

/** 이름별 고정 결과 프로필. 목록에 없는 이름은 `defaultResult`로 합성한다. */
function fixtureResult(name: string): CommunityResult | null {
  const collectedAt = '2026-09-15T00:00:00Z'
  const base = {
    snapshot_id: `00000000-0000-4000-8000-${name.length.toString().padStart(12, '0')}`,
    collected_at: collectedAt,
    fresh_until: new Date(Date.parse(collectedAt) + FRESH_MS).toISOString(),
    serve_until: new Date(Date.parse(collectedAt) + SERVE_MS).toISOString(),
    data_limits: DATA_LIMITS,
  }

  if (name === 'pino') {
    return {
      ...base,
      data_status: 'AVAILABLE',
      summary_status: 'PARTIAL',
      summary_retry_at: null,
      repository: repositoryOf(name),
      summary: { issue_count: 2, open_issue_count: 1, comment_count: 5, reaction_count: 2 },
      topics: [
        topic({
          issue_number: 42,
          title_original: 'Log level not applied after reload',
          title_ko: '재시작 후 로그 레벨이 반영되지 않음',
          comments_count: 3,
          reactions_count: 2,
          summary_status: 'READY',
          summary_ko: '설정을 재적용하는 방법이 댓글에서 공유됐다.',
          summary_marks: [{ start: 4, end: 12, kind: 'KEY_TERM' }],
          messages: [
            {
              author_login: 'example-user',
              role: 'CONTRIBUTOR',
              kind: 'USER_SOLUTION',
              created_at: '2026-09-05T00:00:00Z',
              text: '설정 파일을 재적용하는 방법을 공유했다.',
            },
          ],
        }),
        topic({
          issue_number: 51,
          title_original: 'Feature request: async transport',
          summary_status: 'FAILED',
          comments_count: 2,
          reactions_count: 0,
        }),
      ],
      limitations: [
        {
          code: 'SUMMARY_UNAVAILABLE',
          message: '요약을 제공하지 못해 확인된 제목과 수치만 표시합니다.',
          issue_number: 51,
        },
      ] satisfies CommunityLimitation[],
    }
  }

  if (name === 'bunyan') {
    return {
      ...base,
      data_status: 'NO_DISCUSSION_DATA',
      summary_status: 'SKIPPED',
      summary_retry_at: null,
      repository: repositoryOf(name),
      summary: { issue_count: 0, open_issue_count: 0, comment_count: 0, reaction_count: 0 },
      topics: [],
      limitations: [],
    }
  }

  if (name === 'express') {
    return {
      ...base,
      data_status: 'UNVERIFIED_REPOSITORY',
      summary_status: 'SKIPPED',
      summary_retry_at: null,
      repository: null,
      summary: { issue_count: 0, open_issue_count: 0, comment_count: 0, reaction_count: 0 },
      topics: [],
      limitations: [],
    }
  }

  // winston + 그 외 임의 이름 — 기본 성공 결과.
  return {
    ...base,
    data_status: 'AVAILABLE',
    summary_status: 'READY',
    summary_retry_at: null,
    repository: repositoryOf(name),
    summary: { issue_count: 1, open_issue_count: 1, comment_count: 2, reaction_count: 1 },
    limitations: [
      {
        code: 'ROOT_PACKAGE_SCOPE_HEURISTIC',
        message: '루트 패키지 연결에 기반하며 모든 Issue의 주제를 보장하지 않습니다.',
        issue_number: null,
      },
    ],
    topics: [
      topic({
        issue_number: 7,
        title_original: 'Configuration question',
        title_ko: '설정 동작 확인',
        comments_count: 2,
        reactions_count: 1,
        summary_status: 'READY',
        summary_ko: '작성자가 설정 동작을 질문했고 댓글에서 확인 방법이 제시됐다.',
        messages: [
          {
            author_login: 'example-user',
            role: 'ISSUE_AUTHOR',
            kind: 'DISCUSSION',
            created_at: '2026-09-01T00:00:00Z',
            text: '설정 동작을 질문했다.',
          },
          {
            author_login: 'example-maintainer',
            role: 'REPOSITORY_OWNER',
            kind: 'USER_SOLUTION',
            created_at: '2026-09-02T00:00:00Z',
            text: '설정을 확인하는 방법을 제시했다.',
          },
        ],
      }),
    ],
  }
}

function freshnessOf(result: CommunityResult): 'FRESH' | 'STALE' | null {
  const nowMs = Date.now()
  if (nowMs >= Date.parse(result.serve_until)) return null
  return nowMs < Date.parse(result.fresh_until) ? 'FRESH' : 'STALE'
}

function statusFor(name: string): CommunityStatusResponse {
  const task = tasks.get(name)

  if (task) {
    if (task.stageIndex < 0) {
      return {
        package_name: name,
        view_status: 'PROCESSING',
        freshness: null,
        refresh: {
          refresh_id: task.refreshId,
          status: 'QUEUED',
          stage: null,
          stage_message: '대기열에서 기다리는 중입니다.',
          started_at: null,
          last_updated_at: now(),
          poll_after_seconds: 2,
          retry_at: null,
          error_code: null,
        },
        result: null,
      }
    }
    if (task.stageIndex < STAGES.length) {
      const stage = STAGES[task.stageIndex]
      const refresh: CommunityRefreshInfo = {
        refresh_id: task.refreshId,
        status: 'RUNNING',
        stage,
        stage_message: STAGE_MESSAGE[stage],
        started_at: task.startedAt,
        last_updated_at: now(),
        poll_after_seconds: 2,
        retry_at: null,
        error_code: null,
      }
      const published = results.get(name)
      return {
        package_name: name,
        view_status: 'PROCESSING',
        freshness: published ? freshnessOf(published) : null,
        refresh,
        result: published ?? null,
      }
    }
    // 마지막 단계까지 지났다 — 게시하고 task 를 지운다.
    tasks.delete(name)
    const built = fixtureResult(name)
    if (built) results.set(name, built)
  }

  const result = results.get(name)
  if (!result) {
    return { package_name: name, view_status: 'IDLE', freshness: null, refresh: null, result: null }
  }
  const freshness = freshnessOf(result)
  if (freshness === null) {
    results.delete(name) // serve_until 경과 — 더는 보여주지 않는다.
    return { package_name: name, view_status: 'IDLE', freshness: null, refresh: null, result: null }
  }
  return { package_name: name, view_status: 'RESULT', freshness, refresh: null, result }
}

function validateName(name: string | undefined): string {
  const value = (name ?? '').trim()
  if (!value) fail('V001', '패키지명(name)은 필수입니다.')
  if (!NPM_NAME_RE.test(value)) fail('V004', '패키지명 형식이 올바르지 않습니다.')
  return value
}

export function mockCommunityStatus(name: string | undefined): Promise<CommunityStatusResponse> {
  const validated = validateName(name)
  // GET 이 폴링을 흉내내는 지점이다 — 부를 때마다 진행 중 task 를 한 단계 전진시킨다.
  const task = tasks.get(validated)
  if (task) task.stageIndex += 1
  return delay(statusFor(validated))
}

export function mockCommunityRefresh(
  name: string | undefined,
  trigger: CommunityRefreshTrigger | undefined,
): Promise<CommunityStatusResponse> {
  const validated = validateName(name)
  if (trigger !== 'ANALYSIS_CONFIRMED' && trigger !== 'TAB_OPENED') {
    fail('V004', 'trigger 값이 올바르지 않습니다.')
  }

  if (validated === CAPACITY_DEMO_NAME) {
    return delay({
      package_name: validated,
      view_status: 'FAILED',
      freshness: null,
      refresh: {
        refresh_id: null,
        status: 'CAPACITY_LIMITED',
        stage: null,
        stage_message: '지금은 처리할 수 있는 여유가 없습니다.',
        started_at: null,
        last_updated_at: now(),
        poll_after_seconds: null,
        retry_at: new Date(Date.now() + 5_000).toISOString(),
        error_code: 'CAPACITY_LIMITED',
      },
      result: null,
    })
  }

  const existingTask = tasks.get(validated)
  const existingResult = results.get(validated)
  const fresh = existingResult ? freshnessOf(existingResult) === 'FRESH' : false

  // 기존 작업 참여 또는 fresh 적중 — 새 task 를 만들지 않는다.
  if (existingTask || fresh) return delay(statusFor(validated))

  tasks.set(validated, {
    refreshId: crypto.randomUUID(),
    trigger: trigger as CommunityRefreshTrigger,
    stageIndex: -1,
    startedAt: now(),
  })
  return delay(statusFor(validated))
}
