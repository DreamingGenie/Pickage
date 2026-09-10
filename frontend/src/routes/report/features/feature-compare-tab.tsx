import { AnalysisProgress } from '@/routes/report/_components/analysis-progress'
import type { AnalysisRun } from '@/routes/report/_components/use-analysis-run'
import {
  COMPARISON_PACKAGES,
  FEATURE_ROWS,
  VERDICT_LABEL,
  type Verdict,
} from '@/routes/report/features/sample'
import { cn } from '@/lib/utils'

/**
 * v1-OSS-03B-feature-compare
 *
 * 최초 분석이 끝나기 전에는 진행 카드 + skeleton 을 보여준다(IA 9.4).
 * 생태계 변화 탭은 기다리지 않고 바로 볼 수 있으므로, 여기만 대기 상태를 갖는다.
 */
export function FeatureCompareTab({
  run,
  onOpenEvidence,
}: {
  run: AnalysisRun
  onOpenEvidence: (evidenceId: string) => void
}) {
  const running = run.status !== 'COMPLETED'

  // 최초 분석: 결과가 아직 없으니 자리를 skeleton 으로 잡고 진행만 보여준다.
  if (running && !run.hasCompletedOnce) {
    return <AnalysisProgress run={run} packages={COMPARISON_PACKAGES} />
  }

  return (
    <div className="flex flex-col gap-5">
      {/* 재분석: 이전 결과를 그대로 두고 상태 카드만 위에 얹는다 (IA 9.4) */}
      {running && <AnalysisProgress run={run} packages={COMPARISON_PACKAGES} compactCard />}

      <section
        className={cn(
          'flex flex-col gap-5 rounded-2xl border p-6 transition-opacity',
          running && 'opacity-60',
        )}
      >
        <header className="flex flex-wrap items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold">핵심 기능 비교</h3>
          <div className="flex items-center gap-2">
            <span className="font-mono text-base text-muted-foreground">정확한 버전 기준</span>
            <button
              type="button"
              onClick={run.restart}
              disabled={running}
              className="rounded-md border px-2.5 py-1 text-base transition-colors hover:border-foreground/40 disabled:opacity-50"
            >
              선택한 버전으로 재분석
            </button>
          </div>
        </header>

        <div className="flex flex-wrap gap-1.5">
          {COMPARISON_PACKAGES.map((p) => (
            <span key={p} className="rounded border px-1.5 py-0.5 font-mono text-base">
              {p}
            </span>
          ))}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-base">
            <thead>
              <tr className="text-muted-foreground">
                <th className="pb-3 text-left font-normal">확인 항목</th>
                {COMPARISON_PACKAGES.map((p) => (
                  <th key={p} className="pb-3 text-left font-mono font-normal">
                    {p.split('@')[0]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FEATURE_ROWS.map((row) => (
                <tr key={row.label} className="border-t align-top">
                  <td className="py-3 pr-3 text-muted-foreground">{row.label}</td>
                  {row.cells.map((cell, i) => (
                    <td key={i} className="py-2">
                      {/* 데이터 셀 전체가 Drawer 열기 대상이다 (IA 9.2) */}
                      <button
                        type="button"
                        onClick={() => cell.evidenceId && onOpenEvidence(cell.evidenceId)}
                        disabled={!cell.evidenceId}
                        className="-mx-2 flex w-full flex-col items-start gap-1 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted/60 disabled:hover:bg-transparent"
                      >
                        <VerdictPill verdict={cell.verdict} />
                        {cell.note && (
                          <span className="font-mono text-base leading-tight text-muted-foreground">
                            {cell.note}
                          </span>
                        )}
                        {cell.evidenceId && (
                          <span className="font-mono text-base text-muted-foreground underline underline-offset-2">
                            {cell.evidenceId}
                          </span>
                        )}
                      </button>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="border-t pt-4 text-base leading-relaxed text-muted-foreground">
          <strong className="font-medium text-foreground">미확인</strong>은 미지원이 아닙니다. 해당
          버전 자료에서 확인되지 않았다는 뜻이고, 무엇을 어디까지 찾아봤는지 근거에 함께 담깁니다.{' '}
          <strong className="font-medium text-foreground">미지원</strong>은 공식 부정 근거가 있을
          때만 씁니다. 추천 · 순위 · 승자를 매기지 않습니다.
        </p>
      </section>
    </div>
  )
}

/** 구상안 7.2 verdict 5종. 미확인은 실패색을 쓰지 않는다. */
export function VerdictPill({ verdict, className }: { verdict: Verdict; className?: string }) {
  const style: Record<Verdict, string> = {
    SUPPORTED: 'bg-emerald-50 text-emerald-700',
    CONDITIONALLY_SUPPORTED: 'bg-amber-50 text-amber-700',
    LIMITED_SUPPORT: 'bg-amber-50 text-amber-700',
    UNCONFIRMED: 'bg-muted text-muted-foreground',
    UNSUPPORTED: 'bg-red-50 text-red-700',
  }
  return (
    <span
      className={cn(
        'w-fit rounded px-1.5 py-0.5 text-base font-medium',
        style[verdict],
        className,
      )}
      title={verdict}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  )
}
