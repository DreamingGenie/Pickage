import { describe, expect, it } from 'vitest'

import { noticeFromRefresh, toProgressModel } from '@/routes/report/community/adapter'
import type { CommunityRefreshInfo } from '@/api/types'

function refresh(overrides: Partial<CommunityRefreshInfo>): CommunityRefreshInfo {
  return {
    refresh_id: 'r1',
    status: 'RUNNING',
    stage: 'SEARCHING_ISSUES',
    stage_message: 'Issue를 찾는 중입니다.',
    started_at: '2026-09-15T00:00:00Z',
    last_updated_at: '2026-09-15T00:00:01Z',
    poll_after_seconds: 2,
    retry_at: null,
    error_code: null,
    ...overrides,
  }
}

describe('toProgressModel', () => {
  it('서버 stage_message 를 그대로 옮긴다(가짜 진행률을 만들지 않는다)', () => {
    const model = toProgressModel(
      refresh({ stage: 'SUMMARIZING', stage_message: '요약을 만드는 중입니다.' }),
    )
    expect(model).toEqual({
      stage: 'SUMMARIZING',
      stageMessage: '요약을 만드는 중입니다.',
      startedAt: '2026-09-15T00:00:00Z',
    })
  })
})

describe('noticeFromRefresh', () => {
  it('refresh_id 가 있으면(=task 가 등록됨) notice 로 다루지 않는다', () => {
    expect(noticeFromRefresh(refresh({ refresh_id: 'r1', status: 'RUNNING' }))).toBeNull()
  })

  it('refresh 가 없으면 notice 도 없다', () => {
    expect(noticeFromRefresh(null)).toBeNull()
  })

  it('QUEUED/RUNNING/COMPLETED 는 refresh_id 가 없어도 notice 로 다루지 않는다', () => {
    expect(noticeFromRefresh(refresh({ refresh_id: null, status: 'COMPLETED' }))).toBeNull()
  })

  it('admission 거절(refresh_id 없음 + CAPACITY_LIMITED)은 notice 로 바꾼다', () => {
    const notice = noticeFromRefresh(
      refresh({
        refresh_id: null,
        status: 'CAPACITY_LIMITED',
        stage: null,
        stage_message: '지금은 처리할 수 있는 여유가 없습니다.',
        retry_at: '2026-09-15T00:05:00Z',
        error_code: 'CAPACITY_LIMITED',
      }),
    )
    expect(notice).toEqual({
      errorCode: 'CAPACITY_LIMITED',
      message: '지금은 처리할 수 있는 여유가 없습니다.',
      retryAt: '2026-09-15T00:05:00Z',
    })
  })

  it('admission 거절(refresh_id 없음 + FAILED)도 notice 로 바꾼다', () => {
    const notice = noticeFromRefresh(
      refresh({
        refresh_id: null,
        status: 'FAILED',
        stage: null,
        error_code: 'COMMUNITY_DISABLED',
      }),
    )
    expect(notice?.errorCode).toBe('COMMUNITY_DISABLED')
  })
})
