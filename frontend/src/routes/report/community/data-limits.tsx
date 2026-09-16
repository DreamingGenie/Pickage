import type { CommunityDataLimits } from '@/api/types'

/**
 * 자료 상한 안내(구현계획 §6.2·8.3). 서버가 준 `source_note`를 그대로 보여준다 —
 * "Issue 최대 2개·댓글 최대 100개" 같은 숫자를 화면이 다시 만들면 정책이 바뀔 때
 * 여기만 낡은 값으로 남는다.
 */
export function CommunityDataLimitsNote({ limits }: { limits: CommunityDataLimits }) {
  return (
    <p className="text-base text-muted-foreground">
      {limits.source_note}{' '}
      <span className="font-mono">
        (lookback {limits.lookback_days}d · issues ≤{limits.max_issues} · comments ≤
        {limits.max_comments_per_issue})
      </span>
    </p>
  )
}
