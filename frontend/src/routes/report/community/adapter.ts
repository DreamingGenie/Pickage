import type { CommunityRefreshInfo } from '@/api/types'
import type { CommunityNotice, CommunityProgressModel } from '@/routes/report/community/model'

export function toProgressModel(refresh: CommunityRefreshInfo): CommunityProgressModel {
  return {
    stage: refresh.stage,
    stageMessage: refresh.stage_message,
    startedAt: refresh.started_at,
  }
}

/**
 * admission 거절/실패로 task 를 못 만든 응답만 notice 로 바꾼다.
 * `refresh_id`가 있으면(=task 가 실제로 등록됨) progress/result 로 이미 보여줄 수 있으므로
 * 여기서는 다루지 않는다 — 새 GET registry 에 안 남는, 거절 그 순간만 notice 가 필요하다.
 */
export function noticeFromRefresh(refresh: CommunityRefreshInfo | null): CommunityNotice | null {
  if (!refresh || refresh.refresh_id) return null
  if (refresh.status !== 'FAILED' && refresh.status !== 'CAPACITY_LIMITED') return null
  return {
    errorCode: refresh.error_code,
    message: refresh.stage_message,
    retryAt: refresh.retry_at,
  }
}
