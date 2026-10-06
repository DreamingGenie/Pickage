import { ExternalLinkIcon, LightbulbIcon } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { IssueAccent } from '@/routes/report/community/accent'
import { githubIssueUrl } from '@/routes/report/community/summary-marks'
import type { CommunityMessage, CommunityMessageRole, CommunityTopic } from '@/api/types'

const ROLE_LABEL: Record<CommunityMessageRole, string> = {
  ISSUE_AUTHOR: '작성자',
  REPOSITORY_OWNER: '저장소 소유자',
  ORGANIZATION_MEMBER: '조직 구성원',
  COLLABORATOR: '협업자',
  CONTRIBUTOR: '기여자',
}

/**
 * 패키지를 실제로 운영하는 쪽의 발화. 이 발화는 **답변하는 느낌**이 나도록 오른쪽에 두고 아이콘도 오른쪽에
 * 붙인다(S15P21A506-407). 작성자·기여자는 질문하고 의견을 보태는 쪽이라 왼쪽이다.
 *
 * 정렬은 뜻을 더하는 장식이다 — 누가 운영 측인지는 역할 배지(`협업자` 등)가 글자로 말한다(IA §1-13).
 */
const MAINTAINER_ROLES = new Set<CommunityMessageRole>([
  'REPOSITORY_OWNER',
  'ORGANIZATION_MEMBER',
  'COLLABORATOR',
])

type Tone = 'author' | 'maintainer' | 'other'

const TONE: Record<Tone, { avatar: string; bubble: string }> = {
  author: { avatar: 'bg-emerald-700', bubble: 'border-emerald-200 bg-emerald-50' },
  maintainer: { avatar: 'bg-slate-900', bubble: 'border-blue-200 bg-blue-50' },
  other: { avatar: 'bg-slate-600', bubble: 'border-border bg-slate-50' },
}

function toneOf(role: CommunityMessageRole | null): Tone {
  if (role === 'ISSUE_AUTHOR') return 'author'
  if (role && MAINTAINER_ROLES.has(role)) return 'maintainer'
  return 'other'
}

/** 아이디의 영문·숫자 앞 두 글자. 없으면 물음표 — 개인 사진은 쓰지 않는다. */
function initialsOf(login: string | null): string {
  const letters = (login ?? '').replace(/[^0-9A-Za-z]/g, '').slice(0, 2)
  return letters ? letters.toUpperCase() : '?'
}

/** 한국 시간 기준 날짜(`2026-04-03`). 서버는 UTC 로 준다. */
function dateOf(iso: string): string {
  return new Date(iso).toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' })
}

function Bubble({ message }: { message: CommunityMessage }) {
  const tone = toneOf(message.role)
  const maintainer = tone === 'maintainer'

  return (
    <li
      data-side={maintainer ? 'right' : 'left'}
      className={cn(
        'flex items-start gap-3',
        // 반대쪽에 여백을 둬 말풍선이 카드 폭을 끝까지 채우지 않게 한다 — 주고받는 모양이 된다.
        maintainer ? 'flex-row-reverse pl-8' : 'pr-8',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'flex size-10 shrink-0 items-center justify-center rounded-full text-base font-bold text-white',
          TONE[tone].avatar,
        )}
      >
        {initialsOf(message.author_login)}
      </span>
      <div className={cn('min-w-0 flex-1 rounded-xl border px-4 py-3', TONE[tone].bubble)}>
        <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-base">
          {/* 식별자는 표시 문자열로만 — 클릭 가능한 링크를 만들지 않는다 */}
          <span className="font-mono font-bold">{message.author_login ?? '알 수 없음'}</span>
          {message.role && (
            <Badge variant="outline" className="bg-background text-xs">
              {ROLE_LABEL[message.role]}
            </Badge>
          )}
          {/*
            `USER_SOLUTION` 은 채택·정답 판정이 아니라 "해결 방법을 제시한 발화 유형"일 뿐이라 라벨도 그렇게만
            적는다(구현계획 §4.2). 일반 논의에는 라벨을 달지 않는다 — 대부분이 논의라 붙이면 소음이다.
          */}
          {message.kind === 'USER_SOLUTION' && (
            <Badge variant="outline" className="gap-1 bg-background text-xs">
              <LightbulbIcon aria-hidden className="size-3.5" />
              해결 방법 제시
            </Badge>
          )}
          <span className="ml-auto text-muted-foreground">{dateOf(message.created_at)}</span>
        </div>
        <p className="text-sm leading-relaxed">{message.text}</p>
      </div>
    </li>
  )
}

/**
 * Issue 하나의 대표 발화(`messages`, 최대 3개)를 대화처럼 보여주는 카드(S15P21A506-407).
 *
 * **사건 흐름(`flow`) 단계 목록은 그리지 않는다**(S15P21A506-406). 바로 위 한국어 요약(`summary_ko`)이
 * 같은 사건을 이미 말하고 있어, 번호 목록이 그 내용을 한 번 더 풀어 쓸 뿐이었다. 서버도 S15P21A506-412 부터 `flow` 를
 * 만들지도 내려주지도 않는다(응답에 남아 있어도 읽지 않는다). 카드 제목도 요약 카드와 같은 말이라 다시 쓰지 않는다 — `#번호`로 잇는다.
 *
 * S15P21A506-448: 카드 머리의 `ISSUE #번호`만 원문 링크로 둔다. 작성자·저장소 식별자는 기존처럼
 * 표시 문자열로 유지하고, 검증된 저장소 이름과 Issue 번호로 주소를 만들 수 있을 때만 링크를 그린다.
 */
export function CommunityThreadCard({
  topic,
  accent,
  repositoryFullName,
}: {
  topic: CommunityTopic
  accent: IssueAccent
  /** `owner/name`. 있으면 `ISSUE #번호`를 해당 GitHub Issue 원문으로 연결한다 */
  repositoryFullName?: string | null
}) {
  const issueUrl = githubIssueUrl(repositoryFullName, topic.issue_number)

  return (
    <div className="flex flex-col gap-4 rounded-2xl border bg-card p-6">
      <div className={cn('border-b pb-3 text-base font-bold tracking-wide', accent.text)}>
        {issueUrl ? (
          <a
            href={issueUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`ISSUE #${topic.issue_number} 원문 보기 (새 탭에서 열림)`}
            className="inline-flex items-center gap-1.5 rounded-sm outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {`ISSUE #${topic.issue_number}`}
            <ExternalLinkIcon aria-hidden className="size-4" />
          </a>
        ) : (
          <span>{`ISSUE #${topic.issue_number}`}</span>
        )}
      </div>
      {topic.messages.length > 0 ? (
        <ul className="flex flex-col gap-4">
          {topic.messages.map((m, i) => (
            <Bubble key={i} message={m} />
          ))}
        </ul>
      ) : (
        <p className="text-base text-muted-foreground">보여 줄 대표 발화가 없습니다.</p>
      )}
    </div>
  )
}
