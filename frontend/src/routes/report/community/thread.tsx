import { Badge } from '@/components/ui/badge'
import type { CommunityFlowStep, CommunityMessage, CommunityMessageRole } from '@/api/types'

const ROLE_LABEL: Record<CommunityMessageRole, string> = {
  ISSUE_AUTHOR: '작성자',
  REPOSITORY_OWNER: '저장소 소유자',
  ORGANIZATION_MEMBER: '조직 구성원',
  COLLABORATOR: '협업자',
  CONTRIBUTOR: '기여자',
}

const KIND_LABEL: Record<CommunityMessage['kind'], string> = {
  DISCUSSION: '논의',
  USER_SOLUTION: '해결 방법 제시',
}

/**
 * Issue 하나의 사건 흐름(`flow`) + 대표 발화(`messages`, 최대 3개).
 *
 * 원문 링크를 달지 않는다 — 확장 화면 공통 규칙(IA §1-14, 저장소·작성자 식별자는 표시
 * 문자열로만). `USER_SOLUTION`은 채택·정답 판정이 아니라 "해결 방법을 제시한 발화
 * 유형"일 뿐이라 라벨도 그렇게만 적는다(구현계획 §4.2).
 */
export function CommunityThread({
  flow,
  messages,
}: {
  flow: CommunityFlowStep[]
  messages: CommunityMessage[]
}) {
  if (flow.length === 0 && messages.length === 0) return null

  return (
    <div className="flex flex-col gap-3 border-t pt-3">
      {flow.length > 0 && (
        <ol className="flex flex-col gap-1">
          {flow.map((step, i) => (
            <li key={i} className="text-base text-muted-foreground">
              {i + 1}. {step.text}
            </li>
          ))}
        </ol>
      )}

      {messages.length > 0 && (
        <ul className="flex flex-col gap-2">
          {messages.map((m, i) => (
            <li key={i} className="rounded-lg border border-dashed px-3 py-2">
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-base text-muted-foreground">
                {/* 식별자는 표시 문자열로만 — 클릭 가능한 링크를 만들지 않는다 */}
                <span className="font-mono text-foreground">{m.author_login ?? '알 수 없음'}</span>
                {m.role && (
                  <Badge variant="outline" className="text-xs">
                    {ROLE_LABEL[m.role]}
                  </Badge>
                )}
                <Badge variant="outline" className="text-xs">
                  {KIND_LABEL[m.kind]}
                </Badge>
              </div>
              <p className="text-sm">{m.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
