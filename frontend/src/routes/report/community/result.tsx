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

/**
 * 저장소 전체 Issue 수 표기. 천 단위 쉼표를 넣는다(`12,345건`).
 *
 * 값이 없으면 — 서버가 못 구했거나 이 값을 더하기 전에 저장된 스냅샷이다(S15P21A506-413) — `—` 로 둔다. 0 으로 채우면 "Issue 가
 * 없는 저장소"로 읽히므로 없는 값을 지어내지 않는다.
 */
function issueCountText(count: number | null | undefined): string {
  return count == null ? '—' : `${count.toLocaleString('ko-KR')}건`
}

/**
 * 저장소 카드 옆에 두는 `열린 Issue` 한 칸(S15P21A506-469). 예전엔 이 칸이 4칸짜리 요약 수치 행의
 * 하나였다 — 전체 Issue·핵심 논의 누적 댓글·사용자 반응 3칸과 수집 상태 배지 행은 화면이 복잡하다는
 * 이유로 없앴고, 저장소 규모를 보여주는 맥락으로서 값어치가 있는 이 칸만 저장소 카드 왼쪽으로 옮겼다.
 */
function OpenIssuesCard({ openIssues }: { openIssues: number | null | undefined }) {
  return (
    <div className="flex w-full flex-col gap-1 rounded-2xl border bg-card px-5 py-4 sm:w-40">
      <p className="text-base text-muted-foreground">열린 Issue</p>
      <p className="text-3xl leading-tight font-bold tracking-tight">{issueCountText(openIssues)}</p>
      <p className="text-base text-muted-foreground">
        {openIssues == null ? '이번 자료에는 집계되지 않았습니다' : '현재 open 상태 전체'}
      </p>
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
  const { topics } = result
  const openIssues = result.repository?.open_issue_count
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

        <div className="flex w-full flex-col gap-4 sm:w-auto sm:flex-row sm:items-start">
          {/* 예전엔 요약 수치 4칸 행의 하나였다 — 나머지 3칸·수집 상태 배지 행과 함께 없애고 이 칸만
              저장소 카드 옆으로 올렸다(S15P21A506-469). 터미널 상태(저장소 미확인 등)에는 조회할
              저장소 자체가 없어 함께 두지 않는다. */}
          {!terminalMessage && <OpenIssuesCard openIssues={openIssues} />}
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
          <section className="flex flex-col gap-4">
            <SectionHeading title="핵심 논의" hint="GitHub 공개 Issue · 핵심 논지 요약" />
            <div className="grid gap-6 lg:grid-cols-2">
              {topics.map((topic, i) => (
                <CommunityIssueCard
                  key={topic.issue_number}
                  topic={topic}
                  limitations={result.limitations}
                  accent={issueAccent(i)}
                  repositoryFullName={result.repository?.full_name}
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
                    repositoryFullName={result.repository?.full_name}
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
