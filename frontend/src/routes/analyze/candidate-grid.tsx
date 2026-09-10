import { CheckIcon } from 'lucide-react'

import type { Candidate } from '@/routes/analyze/sample-registry'
import { cn } from '@/lib/utils'

/**
 * 후보 카드 그리드 (IA 6.2 · Figma 220:196).
 *
 * 데스크톱 3열, 모바일 1열 스택(IA 13).
 * 버전은 표시하지 않는다 — 보고서에서 고른다.
 * 상태 표시는 색과 함께 아이콘·문구를 둔다(IA 1.11).
 */
export function CandidateGrid({
  candidates,
  picked,
  onToggle,
}: {
  candidates: Candidate[]
  picked: string[]
  onToggle: (name: string) => void
}) {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {candidates.map((c) => {
        const on = picked.includes(c.package)
        return (
          <li key={c.package}>
            <button
              type="button"
              onClick={() => onToggle(c.package)}
              aria-pressed={on}
              className={cn(
                'flex h-full w-full flex-col gap-5 rounded-2xl border bg-background p-6 text-left transition-[border-color,box-shadow]',
                on
                  ? 'border-foreground shadow-[0_2px_16px_-10px_rgba(15,23,42,0.4)]'
                  : 'hover:border-foreground/30',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="font-mono text-2xl leading-none font-bold tracking-tight">
                  {c.package}
                </span>
                <span
                  aria-hidden
                  className={cn(
                    'grid size-5 shrink-0 place-items-center rounded-[5px] border',
                    on && 'border-foreground bg-foreground',
                  )}
                >
                  {on && <CheckIcon className="size-3.5 text-background" strokeWidth={3} />}
                </span>
              </div>

              <dl className="flex flex-col gap-3.5">
                <Row label="설명 유사도">
                  <span className="text-base font-semibold tabular-nums">
                    {c.descriptionSimilarity.toFixed(2)}
                  </span>
                </Row>
                <div className="flex flex-col gap-1">
                  <dt className="text-base text-muted-foreground">공통 키워드</dt>
                  <dd className="font-mono text-base">{c.sharedKeywords.join(' · ')}</dd>
                </div>
                <Row label="최근 배포">
                  <span className="font-mono text-base tabular-nums">{c.publishedAt}</span>
                </Row>
              </dl>

              <DataStatusPill status={c.dataStatus} />
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-base text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** 구상안 4.3 dataStatus. 자료 상태이지 품질 판정이 아니다. */
function DataStatusPill({ status }: { status: Candidate['dataStatus'] }) {
  const ready = status === 'READY'
  return (
    <span
      className={cn(
        'mt-auto inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-base',
        ready
          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
          : 'border-amber-200 bg-amber-50 text-amber-700',
      )}
    >
      <span aria-hidden className="text-base">
        {ready ? '●' : '▲'}
      </span>
      {ready ? '분석 가능' : '일부 자료 제한'}
    </span>
  )
}
