import { Badge } from '@/components/ui/badge'
import { InfoDialog } from '@/components/common/info-dialog'
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
 * 카드의 수집 상태 배지가 **이미 말하는 사실**을 되풀이하는 한계 코드(S15P21A506-406).
 *
 * `댓글 일부만 수집했습니다.` 는 오른쪽 위 `댓글 일부만 수집` 배지와, `댓글을 확인하지 못했습니다.` 는
 * `댓글 수집 실패` 배지와 같은 문장이다. 같은 카드 안에서 두 번 읽히지 않게 한계 목록에서는 뺀다 —
 * 배지는 `collection_status` 에서, 이 문구는 `limitations` 에서 온다.
 * API 가 이 한계를 계속 내려주는 이유는 화면이 아니라 `data_status`(부분 자료 여부) 계산 때문이다.
 */
const DUPLICATES_COLLECTION_BADGE = new Set(['COMMENTS_TRUNCATED', 'COMMENTS_UNAVAILABLE'])

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
  // 배지와 같은 말을 하는 것은 뺀다. 남는 것(요약 입력 한도 등)은 요약 옆 ⓘ 모달로 둔다.
  const notes = limitations.filter(
    (l) => l.issue_number === topic.issue_number && !DUPLICATES_COLLECTION_BADGE.has(l.code),
  )
  const collection = COLLECTION_STATUS[topic.collection_status]

  const info =
    notes.length > 0 ? (
      <InfoDialog
        label={`#${topic.issue_number} 요약 안내`}
        title="요약 안내"
        className="ml-1 align-middle"
      >
        {notes.map((l) => (
          <p key={l.code}>{l.message}</p>
        ))}
      </InfoDialog>
    ) : null

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
        <p className="text-sm">
          {topic.summary_ko}
          {info}
        </p>
      ) : (
        <p className="text-base text-muted-foreground">
          이 Issue는 확인된 제목·수치만 있고 한국어 요약은 아직 없습니다.
          {info}
        </p>
      )}

      <CommunityThread messages={topic.messages} />
    </div>
  )
}
