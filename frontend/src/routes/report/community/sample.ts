import type { CommunityResult } from '@/api/types'

/**
 * 레이아웃 검토용 정적 예시. **실제 GitHub 현황에 대한 주장이 아니다** — 구현계획
 * §6.4의 fixture와 같은 성격이다. 런타임 정책 시험(=`api/mock/community.ts`)과는
 * 분리한다 — 저건 폴링 진행을 흉내내야 해서 상태를 가지지만, 이건 고정 스냅샷 하나다.
 */
export const SAMPLE_COMMUNITY_RESULT: CommunityResult = {
  snapshot_id: '00000000-0000-4000-8000-000000000001',
  collected_at: '2026-09-11T00:00:00Z',
  fresh_until: '2026-09-12T00:00:00Z',
  serve_until: '2026-09-18T00:00:00Z',
  data_status: 'AVAILABLE',
  summary_status: 'READY',
  summary_retry_at: null,
  repository: {
    owner: 'pickage-fixture',
    name: 'community-fixture',
    full_name: 'pickage-fixture/community-fixture',
    scope: 'PACKAGE_SCOPED',
    archived: false,
  },
  summary: { issue_count: 1, open_issue_count: 1, comment_count: 2, reaction_count: 1 },
  topics: [
    {
      issue_number: 7,
      state: 'OPEN',
      title_original: 'Configuration question',
      title_ko: '설정 동작 확인',
      comments_count: 2,
      reactions_count: 1,
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-10T00:00:00Z',
      collection_status: 'COMPLETE',
      summary_status: 'READY',
      summary_ko: '작성자가 설정 동작을 질문했고 댓글에서 확인 방법이 제시됐다.',
      // '설정 동작' 은 핵심어, '댓글에서 확인 방법이 제시됐다' 는 핵심 문장
      summary_marks: [
        { start: 5, end: 10, kind: 'KEY_TERM' },
        { start: 17, end: 33, kind: 'KEY_SENTENCE' },
      ],
      messages: [
        {
          author_login: 'example-user',
          role: 'ISSUE_AUTHOR',
          kind: 'DISCUSSION',
          created_at: '2026-09-01T00:00:00Z',
          text: '설정 동작을 질문했다.',
        },
      ],
    },
  ],
  limitations: [
    {
      code: 'ROOT_PACKAGE_SCOPE_HEURISTIC',
      message: '루트 패키지 연결에 기반하며 모든 Issue의 주제를 보장하지 않습니다.',
      issue_number: null,
    },
  ],
  data_limits: {
    policy_version: 'github-active-v1',
    lookback_days: 180,
    max_issues: 2,
    max_comments_per_issue: 100,
    max_messages_per_issue: 4,
    source_note: '수치는 선택한 Issue 집합의 값이며 저장소 전체나 고유 참여자 수가 아닙니다.',
  },
}
