import { Button } from '@/components/ui/button'
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

/** 서버가 말하는 실제 단계. 남은 시간은 적지 않는다 — 패키지마다 달라 틀린 약속이 된다. */
const PHASE_LABEL: Record<FeatureRunPhase, string> = {
  PREPARING_DOCS: '문헌을 준비하고 있습니다',
  COMPARING: '기능을 비교하고 있습니다',
  DONE: '마무리하고 있습니다',
}

export function AiComparisonSection({
  run,
  onOpenEvidence,
}: {
  run: FeatureAnalysis
  onOpenEvidence: (evidenceId: string) => void
}) {
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
          위 소비 조건과 README 를 근거로 만든 판정입니다. 근거 ID 를 눌러 원문을 확인할 수
          있습니다.
        </p>
      </header>

      {/* 아직 한 번도 돌지 않았다. 무엇이 일어날지 적고 기다린다. */}
      {!view && !running && (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed p-6">
          <p className="text-base leading-relaxed text-muted-foreground">
            {run.targets
              ? `${run.targets.map((t) => `${t.package_name}@${t.version}`).join(' · ')} 을(를) 비교합니다. 1~2분 걸립니다.`
              : '비교할 버전을 먼저 고르세요. 정식 버전이 없는 패키지는 직접 선택해야 합니다.'}
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
          <FeatureTable view={view} dimmed={running} onOpenEvidence={onOpenEvidence} />
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
 * 진행률을 지어내지 않는다 — 서버가 주는 것은 단계 이름과 경과 초뿐이고, 없는 퍼센트를
 * 그리면 사용자가 남은 시간을 읽는다.
 */
function RunningCard({ run }: { run: FeatureAnalysis }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-3 rounded-2xl border p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-base font-medium">
          {run.phase ? PHASE_LABEL[run.phase] : '분석을 시작하고 있습니다'}
        </p>
        <span className="font-mono text-base text-muted-foreground">{run.elapsedSec}초 경과</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-primary" />
      </div>
      {/* 결과 자리를 미리 잡아 완료 순간에 화면이 튀지 않게 한다 */}
      {!run.completed && (
        <div className="flex flex-col gap-2 pt-1">
          <div className="h-4 w-1/3 animate-pulse rounded bg-muted" />
          <div className="h-24 w-full animate-pulse rounded bg-muted/60" />
        </div>
      )}
    </div>
  )
}
