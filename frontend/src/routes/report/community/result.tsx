import { InfoDialog } from '@/components/common/info-dialog'
import { StatusBadge } from '@/components/common/status-badge'
import { issueAccent } from '@/routes/report/community/accent'
import { CommunityScopeInfo } from '@/routes/report/community/data-limits'
import { CommunityIssueCard } from '@/routes/report/community/issue-card'
import { CommunityThreadCard } from '@/routes/report/community/thread'
import type { CommunityDataStatus, CommunityResult as CommunityResultData } from '@/api/types'

/** 검증에 실패해 논의를 아예 못 가져온 terminal 상태. 빈 topics 를 그냥 "논의 없음"으로 보여주지 않는다. */
const TERMINAL_MESSAGE: Partial<Record<CommunityDataStatus, string>> = {
  UNVERIFIED_REPOSITORY: '공개 저장소 연결을 확인하지 못했습니다.',
  AMBIGUOUS_SCOPE: '이 패키지와 저장소의 연결이 모호해 범위를 확정하지 못했습니다.',
  UNSUPPORTED_HOST: '저장소가 GitHub가 아니어서 지원하지 않습니다.',
  NO_DISCUSSION_DATA: '최근 조회 기간 안에서 조건에 맞는 논의를 찾지 못했습니다.',
}

/** 요약 수치 한 칸. `sub` 는 그 수치가 무엇으로 이루어졌는지 한 줄로 말한다. */
function Kpi({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border bg-card px-5 py-4">
      <p className="text-base text-muted-foreground">{label}</p>
      <p className="text-3xl leading-tight font-bold tracking-tight">{value}</p>
      <p className="text-base text-muted-foreground">{sub}</p>
    </div>
  )
}

function SectionHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
      <h3 className="text-2xl font-bold tracking-tight">{title}</h3>
      <p className="text-base text-muted-foreground">{hint}</p>
    </div>
  )
}

/**
 * RESULT 뷰(S15P21A506-407 와이어프레임 형태). 위에서부터 ① 제목과 저장소 카드 ② 요약 수치 ③ 핵심 논의
 * ④ 실제 논의 흐름이다. `freshness`는 색만으로 구분하지 않고 문구를 함께 준다(IA §1-13).
 * 다른 패키지로 대체하지 않는다 — terminal 상태여도 이 기준 패키지의 사실만 보여준다.
 *
 * `packageName` 은 화면 제목용이다. 저장소 이름이 아니라 사용자가 고른 기준 패키지 이름을 쓴다.
 */
export function CommunityResultView({
  result,
  freshness,
  packageName,
}: {
  result: CommunityResultData
  freshness: 'FRESH' | 'STALE'
  packageName?: string | null
}) {
  const terminalMessage = TERMINAL_MESSAGE[result.data_status]
  const { summary, topics } = result
  const closedCount = summary.issue_count - summary.open_issue_count
  const hasThreads = topics.some((t) => t.messages.length > 0)

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-4">
        <div className="flex min-w-0 flex-col gap-2">
          <p className="text-base font-bold tracking-wider text-emerald-700">
            {packageName ? `${packageName.toUpperCase()} · GITHUB COMMUNITY` : 'GITHUB COMMUNITY'}
          </p>
          <h2 className="text-4xl leading-tight font-bold tracking-tight">
            {packageName ? `${packageName} 커뮤니티 현황` : '커뮤니티 현황'}
          </h2>
          <p className="text-sm text-muted-foreground">
            {packageName ? `${packageName} 저장소` : '저장소'}의 공개 Issue에서 핵심 논의와 실제
            댓글 흐름을 봅니다.
          </p>
        </div>

        <div className="flex w-full flex-col gap-2.5 rounded-2xl border bg-card px-5 py-4 sm:w-80">
          <div className="flex items-center justify-between gap-2">
            {result.repository ? (
              // 링크가 아니다 — 확장 화면은 저장소 식별자를 표시 문자열로만 둔다(IA §1-14)
              <p className="font-mono text-sm font-bold">{`github.com/${result.repository.full_name}`}</p>
            ) : (
              <p className="text-sm text-muted-foreground">확인된 저장소 없음</p>
            )}
            {/*
              저장소 수준 한계(패키지 범위 추정, 제외된 이슈 등)와 수집 기준을 한 모달로 모았다
              (S15P21A506-406). 셋 다 "이 결과가 어떤 범위로 모였나" 에 대한 설명이라 나눌 이유가 없다.
              터미널 상태(저장소 미확인 등)에서도 조회 기준은 그대로라 항상 둔다.
            */}
            <InfoDialog label="수집 기준 안내" title="수집 기준과 한계">
              <CommunityScopeInfo limits={result.data_limits} limitations={result.limitations} />
            </InfoDialog>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2.5">
            <StatusBadge
              status={freshness === 'FRESH' ? 'ok' : 'warn'}
              label={freshness === 'FRESH' ? '최신' : '이전 자료(갱신 필요)'}
            />
            <p className="text-base text-muted-foreground">
              {new Date(result.collected_at).toLocaleString('ko-KR', {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}{' '}
              기준
            </p>
          </div>
        </div>
      </div>

      {result.repository?.archived && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          보관(archived)된 저장소입니다. 더 이상 활발히 관리되지 않을 수 있습니다.
        </p>
      )}

      {terminalMessage ? (
        <p className="rounded-2xl border border-dashed px-5 py-4 text-sm">{terminalMessage}</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi
              label="분석 Issue"
              value={`${summary.issue_count}건`}
              sub={`최근 ${result.data_limits.lookback_days}일 공개 Issue`}
            />
            <Kpi
              label="누적 댓글"
              value={`${summary.comment_count}개`}
              sub={topics.map((t) => `#${t.issue_number} ${t.comments_count}개`).join(' · ') || '—'}
            />
            <Kpi label="사용자 반응" value={`${summary.reaction_count}개`} sub="GitHub 반응 합계" />
            <Kpi
              label="열린 Issue"
              value={`${summary.open_issue_count}건`}
              sub={
                summary.open_issue_count === 0 ? '분석한 Issue 모두 종료' : `종료 ${closedCount}건`
              }
            />
          </div>

          <section className="flex flex-col gap-4">
            <SectionHeading title="핵심 논의" hint="GitHub 공개 Issue · 핵심 논지 요약" />
            <div className="grid gap-6 lg:grid-cols-2">
              {topics.map((topic, i) => (
                <CommunityIssueCard
                  key={topic.issue_number}
                  topic={topic}
                  limitations={result.limitations}
                  accent={issueAccent(i)}
                />
              ))}
            </div>
          </section>

          {hasThreads && (
            <section className="flex flex-col gap-4">
              <SectionHeading
                title="실제 논의 흐름"
                hint="원문 댓글의 핵심 논지를 한국어로 요약했습니다."
              />
              <div className="grid gap-6 lg:grid-cols-2">
                {topics.map((topic, i) => (
                  <CommunityThreadCard
                    key={topic.issue_number}
                    topic={topic}
                    accent={issueAccent(i)}
                  />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
