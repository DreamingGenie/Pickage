import { StatusBadge } from '@/components/common/status-badge'
import { CommunityDataLimitsNote } from '@/routes/report/community/data-limits'
import { CommunityIssueCard } from '@/routes/report/community/issue-card'
import type { CommunityDataStatus, CommunityResult as CommunityResultData } from '@/api/types'

/** 검증에 실패해 논의를 아예 못 가져온 terminal 상태. 빈 topics 를 그냥 "논의 없음"으로 보여주지 않는다. */
const TERMINAL_MESSAGE: Partial<Record<CommunityDataStatus, string>> = {
  UNVERIFIED_REPOSITORY: '공개 저장소 연결을 확인하지 못했습니다.',
  AMBIGUOUS_SCOPE: '이 패키지와 저장소의 연결이 모호해 범위를 확정하지 못했습니다.',
  UNSUPPORTED_HOST: '저장소가 GitHub가 아니어서 지원하지 않습니다.',
  NO_DISCUSSION_DATA: '최근 조회 기간 안에서 조건에 맞는 논의를 찾지 못했습니다.',
}

/**
 * RESULT 뷰. `freshness`는 색만으로 구분하지 않고 문구를 함께 준다(IA §1-13).
 * 다른 패키지로 대체하지 않는다 — terminal 상태여도 이 기준 패키지의 사실만 보여준다.
 */
export function CommunityResultView({
  result,
  freshness,
}: {
  result: CommunityResultData
  freshness: 'FRESH' | 'STALE'
}) {
  const terminalMessage = TERMINAL_MESSAGE[result.data_status]
  // issue_number 가 없는(저장소 범위) 한계만 여기서 낸다 — Issue 하나에 붙는 한계는
  // `issue-card.tsx`가 각 카드 안에서 낸다.
  const repoLimitations = result.limitations.filter((l) => l.issue_number === null)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          {result.repository ? (
            <p className="font-mono text-sm">{result.repository.full_name}</p>
          ) : (
            <p className="text-sm text-muted-foreground">확인된 저장소 없음</p>
          )}
          <p className="font-mono text-base text-muted-foreground">
            기준 시각 {new Date(result.collected_at).toLocaleString('ko-KR')}
          </p>
        </div>
        <StatusBadge
          status={freshness === 'FRESH' ? 'ok' : 'warn'}
          label={freshness === 'FRESH' ? '최신' : '이전 자료(갱신 필요)'}
        />
      </div>

      {result.repository?.archived && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          보관(archived)된 저장소입니다. 더 이상 활발히 관리되지 않을 수 있습니다.
        </p>
      )}

      {!terminalMessage && (
        <p className="font-mono text-base text-muted-foreground">
          Issue {result.summary.issue_count}(열림 {result.summary.open_issue_count}) · 댓글{' '}
          {result.summary.comment_count} · 반응 {result.summary.reaction_count}
        </p>
      )}

      {repoLimitations.map((l) => (
        <p
          key={l.code}
          className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground"
        >
          {l.message}
        </p>
      ))}

      {terminalMessage ? (
        <p className="rounded-lg border border-dashed px-3 py-2 text-sm">{terminalMessage}</p>
      ) : (
        <div className="flex flex-col gap-3">
          {result.topics.map((topic) => (
            <CommunityIssueCard
              key={topic.issue_number}
              topic={topic}
              limitations={result.limitations}
            />
          ))}
        </div>
      )}

      <CommunityDataLimitsNote limits={result.data_limits} />
    </div>
  )
}
