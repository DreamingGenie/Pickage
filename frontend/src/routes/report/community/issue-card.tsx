import { Badge } from '@/components/ui/badge'
import { StatusBadge } from '@/components/common/status-badge'
import { CommunityThread } from '@/routes/report/community/thread'
import type { CommunityCollectionStatus, CommunityLimitation, CommunityTopic } from '@/api/types'

const COLLECTION_STATUS: Record<
  CommunityCollectionStatus,
  { label: string; level: 'ok' | 'warn' | 'err' }
> = {
  COMPLETE: { label: '댓글 전체 수집', level: 'ok' },
  TRUNCATED: { label: '댓글 일부만 수집', level: 'warn' },
  FAILED: { label: '댓글 수집 실패', level: 'err' },
}

/**
 * Issue 하나. `collection_status`(자료 축)와 `summary_status`(요약 축)를 서로 다른
 * 배지로 낸다 — 섞으면 "댓글은 다 모았는데 요약만 실패"가 "자료 없음"처럼 보인다
 * (구현계획 §5.2).
 */
export function CommunityIssueCard({
  topic,
  limitations,
}: {
  topic: CommunityTopic
  limitations: CommunityLimitation[]
}) {
  const relatedLimitations = limitations.filter((l) => l.issue_number === topic.issue_number)
  const collection = COLLECTION_STATUS[topic.collection_status]

  return (
    <div className="flex flex-col gap-2 rounded-xl border p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <p className="text-sm font-medium">{topic.title_ko ?? topic.title_original}</p>
          {topic.title_ko && (
            <p className="text-base text-muted-foreground">원제목: {topic.title_original}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline" className="text-xs">
            {topic.state === 'OPEN' ? '열림' : '닫힘'}
          </Badge>
          <StatusBadge status={collection.level} label={collection.label} />
        </div>
      </div>

      <p className="font-mono text-base text-muted-foreground">
        댓글 {topic.comments_count} · 반응 {topic.reactions_count} · #{topic.issue_number}
      </p>

      {topic.summary_ko ? (
        <p className="text-sm">{topic.summary_ko}</p>
      ) : (
        <p className="text-base text-muted-foreground">
          이 Issue는 확인된 제목·수치만 있고 한국어 요약은 아직 없습니다.
        </p>
      )}

      {relatedLimitations.map((l) => (
        <p key={l.code} className="text-base text-muted-foreground">
          {l.message}
        </p>
      ))}

      <CommunityThread flow={topic.flow} messages={topic.messages} />
    </div>
  )
}
