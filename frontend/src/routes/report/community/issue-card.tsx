import { ExternalLinkIcon } from 'lucide-react'

import { EmphasizedText } from '@/components/common/emphasized-text'
import { InfoDialog } from '@/components/common/info-dialog'
import { StatusBadge } from '@/components/common/status-badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { IssueAccent } from '@/routes/report/community/accent'
import { githubIssueUrl } from '@/routes/report/community/summary-marks'
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
 * `댓글 일부만 수집했습니다.` 는 카드 아래 `댓글 일부만 수집` 배지와, `댓글을 확인하지 못했습니다.` 는
 * `댓글 수집 실패` 배지와 같은 문장이다. 같은 카드 안에서 두 번 읽히지 않게 한계 목록에서는 뺀다 —
 * 배지는 `collection_status` 에서, 이 문구는 `limitations` 에서 온다.
 * API 가 이 한계를 계속 내려주는 이유는 화면이 아니라 `data_status`(부분 자료 여부) 계산 때문이다.
 */
const DUPLICATES_COLLECTION_BADGE = new Set(['COMMENTS_TRUNCATED', 'COMMENTS_UNAVAILABLE'])

/**
 * "핵심 논의" 카드 — Issue 하나의 제목·수치·한국어 요약(S15P21A506-407).
 * `collection_status`(자료 축)와 `summary_status`(요약 축)를 서로 다른 배지로 낸다 — 섞으면
 * "댓글은 다 모았는데 요약만 실패"가 "자료 없음"처럼 보인다(구현계획 §5.2).
 *
 * 대표 발화는 여기 없다 — 같은 Issue 의 "실제 논의 흐름" 카드(`thread.tsx`)가 낸다.
 */
export function CommunityIssueCard({
  topic,
  limitations,
  accent,
  repositoryFullName,
}: {
  topic: CommunityTopic
  limitations: CommunityLimitation[]
  accent: IssueAccent
  /** `owner/name`. 있으면 `#번호` 자리에 GitHub Issue 로 가는 링크 버튼을 둔다 */
  repositoryFullName?: string | null
}) {
  // 배지와 같은 말을 하는 것은 뺀다. 남는 것(요약 입력 한도 등)은 요약 옆 ⓘ 모달로 둔다.
  const notes = limitations.filter(
    (l) => l.issue_number === topic.issue_number && !DUPLICATES_COLLECTION_BADGE.has(l.code),
  )
  const collection = COLLECTION_STATUS[topic.collection_status]
  const issueUrl = githubIssueUrl(repositoryFullName, topic.issue_number)
  const stats = `${topic.state === 'OPEN' ? '열림' : '종료'} · 댓글 ${topic.comments_count} · 반응 ${topic.reactions_count}`

  const info =
    notes.length > 0 ? (
      <InfoDialog
        label={`#${topic.issue_number} 요약 안내`}
        title="요약 안내"
        className="relative z-10 ml-1 align-middle"
      >
        {notes.map((l) => (
          <p key={l.code}>{l.message}</p>
        ))}
      </InfoDialog>
    ) : null

  return (
    /*
      카드 전체를 누르면 GitHub 원문이 열린다 — 버튼만 눌러야 해서 불편하다는 의견. 링크를 따로 하나 더
      두지 않고 기존 "GitHub에서 보기" 링크를 카드 크기로 늘린다(`after:inset-0`). 그래서 링크는 여전히
      하나뿐이다(DEC-COMMUNITY-LINK-MARKS). 안의 ⓘ 버튼은 `relative z-10` 으로 그 위에 둔다.
    */
    <div
      className={cn(
        'relative flex flex-col gap-3 rounded-2xl border border-l-[5px] bg-card p-6',
        issueUrl && 'transition-shadow hover:shadow-[0_6px_20px_-12px_rgba(15,23,42,0.35)]',
        accent.bar,
      )}
    >
      {/*
        `#번호` 자리에는 실제 GitHub 논의 페이지로 가는 링크 버튼을 둔다(S15P21A506-409). 확장 화면 외부 링크 금지의
        예외로 제품 책임자가 정한 **이 링크 하나뿐**이다 — 새 탭으로 열고 `noopener noreferrer` 를 붙인다.
        주소는 검증된 저장소 이름과 Issue 번호로만 만든다. 만들 수 없으면 링크 없이 `#번호` 글자를 둔다.
        상태는 색이 아니라 글자(`열림`·`종료`)로 적는다.
      */}
      <div
        className={cn(
          'flex flex-wrap items-center gap-x-3 gap-y-1 text-base font-bold',
          accent.text,
        )}
      >
        {issueUrl ? (
          <Button
            asChild
            variant="outline"
            size="sm"
            className={cn(
              "h-8 gap-1.5 font-bold after:absolute after:inset-0 after:rounded-2xl after:content-['']",
              accent.text,
            )}
          >
            <a
              href={issueUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`GitHub에서 보기 — Issue #${topic.issue_number} (새 탭에서 열림)`}
            >
              GitHub에서 보기
              <ExternalLinkIcon aria-hidden />
            </a>
          </Button>
        ) : (
          <span>{`#${topic.issue_number}`}</span>
        )}
        <span>{stats}</span>
      </div>

      <div className="flex flex-col gap-1">
        <h4 className="text-xl leading-snug font-bold">{topic.title_ko ?? topic.title_original}</h4>
        {topic.title_ko && (
          <p className="text-base text-muted-foreground">원제목: {topic.title_original}</p>
        )}
      </div>

      {topic.summary_ko ? (
        <p className="text-sm leading-relaxed">
          <EmphasizedText text={topic.summary_ko} marks={topic.summary_marks} />
          {info}
        </p>
      ) : (
        <p className="text-base text-muted-foreground">
          이 Issue는 확인된 제목·수치만 있고 한국어 요약은 아직 없습니다.
          {info}
        </p>
      )}

      {/* 두 카드 높이가 달라도 배지는 아래에 나란히 놓인다 */}
      <div className="mt-auto border-t pt-3">
        <StatusBadge status={collection.level} label={collection.label} />
      </div>
    </div>
  )
}
