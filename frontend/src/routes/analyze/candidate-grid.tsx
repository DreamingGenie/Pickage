import { CheckIcon } from 'lucide-react'

import type { SimilarCandidate } from '@/api/types'
import { cn } from '@/lib/utils'

/**
 * 후보 카드 그리드 (IA 6.2 · 구상안 §4.3).
 *
 * **버전은 고르지 않는다.** 최신 버전을 적는 것은 "언제 것인지" 를 보여주는 정보이지
 * 선택지가 아니다 — 비교 버전은 보고서 안에서 카드마다 따로 고른다(구상안 §5.2).
 *
 * 선택 상태를 색으로만 알리지 않는다 — 체크 표시와 `aria-pressed` 를 함께 쓴다(IA §1-13).
 *
 * 3열 고정(`sm:grid-cols-3`). 노출 후보가 3개(`VISIBLE_CANDIDATES`, IA §6.1-4)인데 2열로
 * 두면 세 번째 카드가 혼자 다음 줄에 남아 세 후보가 대등한 선택지라는 인상이 깨진다
 * (S15P21A506-309 재검수에서 발견).
 */
export function CandidateGrid({
  candidates,
  picked,
  onToggle,
}: {
  candidates: SimilarCandidate[]
  picked: string[]
  onToggle: (name: string) => void
}) {
  return (
    <ul className="grid gap-4 sm:grid-cols-3">
      {candidates.map((c) => {
        const on = picked.includes(c.name)
        return (
          <li key={c.name}>
            <button
              type="button"
              onClick={() => onToggle(c.name)}
              aria-pressed={on}
              className={cn(
                'flex h-full w-full flex-col gap-4 rounded-2xl border bg-background p-6 text-left transition-[border-color,box-shadow]',
                on
                  ? 'border-foreground shadow-[0_2px_16px_-10px_rgba(15,23,42,0.4)]'
                  : 'hover:border-foreground/30',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="min-w-0 font-mono text-2xl leading-none font-bold tracking-tight">
                  {c.name}
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

              {/*
                설명이 없을 수 있다. 그때 자리를 비워 두면 카드 높이가 서로 달라져
                "이 카드는 뭔가 빠졌다" 가 아니라 "정렬이 깨졌다" 로 보인다.
              */}
              <p className="line-clamp-3 leading-relaxed text-muted-foreground">
                {c.description ?? '설명이 등록되어 있지 않습니다.'}
              </p>

              <dl className="mt-auto flex flex-col gap-2 border-t pt-4">
                <Row label="유사도 순위">
                  <span className="font-mono tabular-nums">{c.rank}위</span>
                </Row>
                <Row label="최신 버전">
                  <span className="font-mono tabular-nums">{c.latest_version ?? '미확인'}</span>
                </Row>
              </dl>
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
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}
