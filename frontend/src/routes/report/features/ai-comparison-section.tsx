import { CheckIcon, Loader2Icon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { FeatureRunPhase } from '@/api/types'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
import { AnalysisFailure, AnalysisStatusCard } from '@/routes/report/features/analysis-status-card'
import { FeatureTable } from '@/routes/report/features/feature-table'
import { NarrativeSection } from '@/routes/report/features/narrative-section'

/**
 * AI 기능 비교 (BE S15P21A506-130, IA §9.2-4).
 *
 * <h2>누를 때만 돈다</h2>
 *
 * 화면이 뜨자마자 시작하지 않는다. 뒤에 LLM 생성이 붙어 분 단위로 가고 서버에 동시 실행
 * 상한이 있다 — 탭을 열기만 한 사람 몫까지 돌리면 정작 누른 사람이 기다린다. 그래서
 * **버튼 → 로딩 → 결과** 세 모습만 있다.
 *
 * <h2>위 표와 서로를 기다리지 않는다</h2>
 *
 * 핵심 비교 요약은 `GET /api/packages/env` 의 단순 조회라 버전을 고르는 즉시 뜨고, 이 영역이
 * 실패해도 그대로 남는다(기능-10-R06). 두 영역은 데이터도 실행도 겹치지 않는다.
 *
 * <h2>상태는 결과를 지우지 않는다</h2>
 *
 * 한 번 완료한 뒤에는 재분석 중이든 실패했든 이전 결과가 그대로 남는다. 성공해야만
 * 교체된다(구상안 §9.3).
 */

/**
 * 서버가 실제로 지나는 세 단계. 프런트가 칸을 더 쪼개 흉내 내지 않는다 — 끝나지 않은 단계를
 * 완료로 그리게 된다. 남은 시간도 적지 않는다(패키지마다 달라 틀린 약속이 된다).
 */
const STEPS: { phase: FeatureRunPhase; title: string; detail: string }[] = [
  {
    phase: 'PREPARING_DOCS',
    title: 'README 불러오기',
    detail: '선택한 버전의 README 를 모으고 있습니다',
  },
  {
    phase: 'COMPARING',
    title: '기능 비교',
    detail: 'AI 가 README 를 읽고 기능을 나란히 맞춰 보고 있습니다',
  },
  { phase: 'DONE', title: '정리', detail: '결과를 표로 정리하고 있습니다' },
]

export function AiComparisonSection({ run }: { run: FeatureAnalysis }) {
  const running = run.status === 'RUNNING' && run.phase !== null
  const view = run.completed
  const failure = run.failure?.kind === 'RUN' ? run.failure : null

  return (
    <section aria-labelledby="ai-comparison-title" className="flex flex-col gap-5 border-t pt-6">
      <header className="flex flex-col gap-1.5">
        <h3 id="ai-comparison-title" className="text-sm font-semibold">
          AI 기능 비교
        </h3>
        <p className="text-base text-muted-foreground">
          각 패키지의 README 를 AI 가 읽고 기능별로 정리합니다.
        </p>
      </header>

      {/* 아직 한 번도 돌지 않았다. 무엇이 일어날지 적고 기다린다. */}
      {!view && !running && (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed p-6">
          <p className="text-base leading-relaxed text-muted-foreground">
            {run.targets
              ? `${run.targets.map((t) => `${t.package_name} ${t.version}`).join(', ')} 의 기능을 비교합니다. 보통 1~2분 걸립니다.`
              : '비교할 버전을 먼저 고르세요.'}
          </p>
          <StartButton run={run} />
        </div>
      )}

      {running && <RunningCard run={run} />}

      {/* 결과가 하나도 없는데 실패했다 */}
      {!view && failure && (
        <AnalysisFailure
          message={failure.message}
          retryable={failure.retryable && run.canStart}
          onRetry={run.restart}
        />
      )}

      {/* 결과가 있다. 재분석 실패·재분석 필요는 상태 카드가 위에 얹어서 말한다(IA §9.4) */}
      {view && (
        <>
          {!running && <AnalysisStatusCard run={run} />}
          <FeatureTable view={view} dimmed={running} />
          {run.sourceNote && (
            <p className="text-base leading-relaxed text-muted-foreground">{run.sourceNote}</p>
          )}
          <NarrativeSection view={view} dimmed={running} />
          {!running && (
            <div>
              <StartButton run={run} />
            </div>
          )}
        </>
      )}
    </section>
  )
}

/** 시작·재분석 버튼. 버전이 다 정해지기 전에는 누를 수 없다 — 서버가 V004 로 거절한다. */
function StartButton({ run }: { run: FeatureAnalysis }) {
  return (
    <Button
      type="button"
      variant={run.completed ? 'outline' : 'default'}
      onClick={run.restart}
      disabled={!run.canStart}
    >
      {run.completed ? '선택한 버전으로 재분석' : '기능 비교 시작'}
    </Button>
  )
}

/**
 * 로딩.
 *
 * 진행률 막대를 그리지 않는다 — 서버가 주는 것은 단계 이름과 경과 초뿐이라, 없는 퍼센트를
 * 그리면 사용자가 거기서 남은 시간을 읽는다. 대신 **지금 몇 번째 단계인지**를 보여 준다.
 *
 * 아래 자리표시는 완성될 표와 같은 모양(행 × 패키지 열)이다. 완료 순간 화면이 튀지 않고,
 * 무엇이 나올지 미리 짐작하게 한다.
 */
function RunningCard({ run }: { run: FeatureAnalysis }) {
  const current = Math.max(
    0,
    STEPS.findIndex((step) => step.phase === (run.phase ?? 'PREPARING_DOCS')),
  )
  const columns = Math.max(1, run.targets?.length ?? 2)

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col gap-6 overflow-hidden rounded-2xl border p-6"
    >
      <ol className="grid grid-cols-3 gap-3">
        {STEPS.map((step, i) => {
          const state = i < current ? 'done' : i === current ? 'active' : 'todo'
          return (
            <li key={step.phase} className="flex flex-col gap-2">
              <div
                className={cn(
                  'h-1 rounded-full transition-colors duration-500',
                  state === 'done' && 'bg-foreground',
                  state === 'active' && 'animate-pulse bg-foreground/60',
                  state === 'todo' && 'bg-muted',
                )}
              />
              <span
                className={cn(
                  'flex items-center gap-1.5 text-sm',
                  state === 'todo' ? 'text-muted-foreground' : 'text-foreground',
                  state === 'active' && 'font-medium',
                )}
              >
                {state === 'done' && (
                  <CheckIcon className="size-3.5" strokeWidth={2.5} aria-hidden />
                )}
                {state === 'active' && (
                  <Loader2Icon className="size-3.5 animate-spin" aria-hidden />
                )}
                {step.title}
              </span>
            </li>
          )
        })}
      </ol>

      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-base text-foreground">{STEPS[current].detail}</p>
        <span className="text-sm text-muted-foreground tabular-nums">
          {run.elapsedSec}초 지남
          {run.elapsedSec >= 30 && ' · 보통 1~2분 걸립니다'}
        </span>
      </div>

      {/* 완성될 표와 같은 모양의 자리표시. 이전 결과가 있으면 그 표가 흐리게 대신한다 */}
      {!run.completed && (
        <div aria-hidden className="flex flex-col">
          {[0, 1, 2, 3, 4].map((row) => (
            <div
              key={row}
              className="grid items-center gap-4 border-t py-3"
              style={{ gridTemplateColumns: `minmax(8rem, 1.2fr) repeat(${columns}, 1fr)` }}
            >
              <div
                className="h-3.5 animate-pulse rounded bg-muted"
                style={{ width: `${70 - row * 7}%`, animationDelay: `${row * 120}ms` }}
              />
              {Array.from({ length: columns }, (_, col) => (
                <div
                  key={col}
                  className="h-5 w-16 animate-pulse rounded bg-muted/70"
                  style={{ animationDelay: `${row * 120 + col * 60}ms` }}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
