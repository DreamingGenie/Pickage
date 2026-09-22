import { CircleAlertIcon, RefreshCwIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
import type { ChangeSummary } from '@/routes/report/features/model'

/**
 * 분석 상태 카드 (IA §9.4, 와이어프레임 「기능 비교 분석 상태」).
 *
 * **분석 상태는 이 카드 안에서만 말한다.** 결과는 상태에 따라 사라지지 않는다 — 재분석이
 * 필요하거나 실패해도 이전 완료 결과는 그대로 남는다(구상안 §9.3).
 */
export function AnalysisStatusCard({ run }: { run: FeatureAnalysis }) {
  const view = run.completed
  if (!view) return null

  const stale = view.packages.flatMap((pkg) => {
    const picked = run.selected[pkg.name]
    return picked && picked !== pkg.version
      ? [{ name: pkg.name, from: pkg.version, to: picked }]
      : []
  })
  const rerunFailure = run.failure?.kind === 'RUN' ? run.failure : null

  return (
    <section
      aria-labelledby="analysis-status-title"
      className="flex flex-col gap-4 rounded-2xl border p-6"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="size-2 rounded-full bg-emerald-600" />
          <h3 id="analysis-status-title" className="text-sm font-semibold">
            분석 완료
          </h3>
        </div>
        {/*
          서버가 준 자료 기준일이 아니라 이 화면이 결과를 받은 시각이다. "기준일" 로 적으면
          자료의 날짜로 읽히므로 시각만 적는다.
        */}
        <span className="text-base text-muted-foreground">
          {new Date(view.analyzedAt).toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          })}{' '}
          분석
        </span>
      </header>

      <p className="text-base leading-relaxed text-muted-foreground">
        위에서 고른 버전 기준의 결과입니다. 버전을 바꾸면 다시 분석해야 반영됩니다.
      </p>

      {/* 재분석이 성공한 직후 한 번. 닫으면 다시 나오지 않는다 (IA §9.3) */}
      {run.changes && <ChangesCallout changes={run.changes} onDismiss={run.dismissChanges} />}

      {stale.length > 0 && (
        <Callout tone="amber" title="재분석 필요 · 기존 결과 유지">
          {stale.map((s) => `${s.name} ${s.from} → ${s.to}`).join(' · ')} 변경됨 · 사용자가
          &lsquo;선택한 버전으로 재분석&rsquo;을 실행할 때 갱신됩니다. 그때까지 PDF는 만들 수
          없습니다.
        </Callout>
      )}

      {rerunFailure && (
        <Callout
          tone="red"
          title="재분석에 실패했습니다 · 이전 결과를 유지했습니다"
          action={
            <Button type="button" variant="outline" size="sm" onClick={run.restart}>
              <RefreshCwIcon className="size-3.5" aria-hidden />
              다시 시도
            </Button>
          }
        >
          {rerunFailure.message}
        </Callout>
      )}
    </section>
  )
}

function ChangesCallout({ changes, onDismiss }: { changes: ChangeSummary; onDismiss: () => void }) {
  const lines = changes.versionChanges.map((c) => `${c.name} ${c.from} → ${c.to}`)

  return (
    <Callout
      tone="green"
      title="재분석 완료 · 바뀐 버전"
      action={
        <Button type="button" variant="outline" size="sm" onClick={onDismiss}>
          확인
        </Button>
      }
    >
      <ul className="flex list-disc flex-col gap-0.5 pl-4">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </Callout>
  )
}

const TONE = {
  amber: 'border-amber-200 bg-amber-50/60 text-amber-900',
  blue: 'border-blue-200 bg-blue-50/60 text-blue-900',
  red: 'border-red-200 bg-red-50/60 text-red-900',
  green: 'border-emerald-200 bg-emerald-50/60 text-emerald-900',
} as const

/** 색과 함께 제목 글자·아이콘으로 상태를 말한다(IA §1-13) */
function Callout({
  tone,
  title,
  action,
  children,
}: {
  tone: keyof typeof TONE
  title: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div
      role="status"
      className={cn(
        'flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4',
        TONE[tone],
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="flex items-center gap-1.5 text-base font-semibold">
          <CircleAlertIcon className="size-3.5 shrink-0" aria-hidden />
          {title}
        </p>
        <div className="text-base leading-relaxed">{children}</div>
      </div>
      {action}
    </div>
  )
}

/** 최초 분석이 실패했거나 버전 목록을 못 받았다. 보여줄 이전 결과가 없다. */
export function AnalysisFailure({
  message,
  retryable,
  onRetry,
}: {
  message: string
  retryable: boolean
  onRetry: () => void
}) {
  return (
    <section className="flex flex-col items-start gap-3 rounded-2xl border border-dashed p-6">
      <h3 className="text-sm font-semibold">기능 비교를 불러오지 못했습니다</h3>
      <p className="text-base leading-relaxed text-muted-foreground">
        {message} 실패했다고 해서 어떤 기능이 지원되지 않는다는 뜻은 아닙니다. 생태계 변화 탭은
        그대로 볼 수 있습니다.
      </p>
      {retryable && (
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          <RefreshCwIcon className="size-3.5" aria-hidden />
          다시 시도
        </Button>
      )}
    </section>
  )
}

/** 정식 버전이 없는 패키지가 있어 자동으로 시작하지 않았다. 선택을 기다린다. */
export function SelectionPrompt() {
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-dashed p-6">
      <h3 className="text-sm font-semibold">비교할 버전을 선택해 주세요</h3>
      <p className="text-base leading-relaxed text-muted-foreground">
        정식 버전이 없는 패키지가 있어 사전 배포 버전을 자동으로 고르지 않았습니다. 위에서 버전을
        선택한 뒤 &lsquo;선택한 버전으로 분석&rsquo;을 눌러 주세요.
      </p>
    </section>
  )
}

/**
 * 이 조합의 기능 비교가 아직 없을 때.
 *
 * **고른 패키지를 그대로 적어 준다.** 무엇에 대한 이야기인지 밝히지 않으면 사용자는
 * 이 자리에 있던 표가 자기 조합의 결과였는지 아닌지 구분하지 못한다.
 */
export function NoAnalysis({ packages }: { packages: readonly string[] }) {
  return (
    <section className="flex flex-col gap-4 rounded-2xl border border-dashed p-6">
      <h3 className="text-sm font-semibold">핵심 기능 비교</h3>

      <div className="flex flex-wrap gap-1.5">
        {packages.map((p) => (
          <span key={p} className="rounded border px-1.5 py-0.5 font-mono text-[11px]">
            {p}
          </span>
        ))}
      </div>

      <p className="text-base leading-relaxed text-muted-foreground">
        이 조합의 기능 비교는 아직 준비되지 않았습니다. 정확한 버전의 배포본을 받아 근거를 뽑는
        분석이 먼저 끝나야 합니다.
      </p>

      <p className="border-t pt-4 text-[11.5px] leading-relaxed text-muted-foreground">
        <strong className="font-medium text-foreground">생태계 변화</strong> 탭은 이 조합의 실제
        자료로 이미 떠 있습니다. 기능 비교만 기다립니다.
      </p>
    </section>
  )
}
