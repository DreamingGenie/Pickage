import type { CommunityErrorCode, CommunityRefreshStage } from '@/api/types'

/**
 * 커뮤니티 탭 view-model.
 *
 * `topics`/`messages`/`repository` 등은 이미 읽기 전용 표시값이라 `issue-card.tsx`·
 * `thread.tsx`·`data-limits.tsx`는 `@/api/types`의 wire 타입(`CommunityTopic` 등)을
 * 그대로 받는다 — ecosystem처럼 차트 좌표로 재가공하는 단계가 없어서, 다시 camelCase로
 * 감싸면 필드명만 두 벌이 되고 얻는 것이 없다. 여기서 view-model이 필요한 것은 **wire에
 * 없는 클라이언트 전용 상태**(진행 단계 표시, admission 거절 notice)뿐이다.
 */

export interface CommunityProgressModel {
  stage: CommunityRefreshStage | null
  /** 서버가 만든 고정 한국어 문구. 가짜 % 로 바꾸지 않는다. */
  stageMessage: string
  /** worker 가 실제로 시작하기 전이면 null */
  startedAt: string | null
}

/**
 * task 를 만들지 못한 admission 거절(§8.2). GET registry 에 남지 않으므로 서버가 아니라
 * 화면이 기억해야 한다 — 새 active task 확인, 성공, 명시적 재시도 시에만 지운다.
 * 뒤이은 GET 의 `view_status: IDLE` 이 이 값을 지우면 안 된다.
 */
export interface CommunityNotice {
  errorCode: CommunityErrorCode | null
  message: string
  retryAt: string | null
}
