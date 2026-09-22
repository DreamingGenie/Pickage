import { CheckIcon, PlusIcon } from 'lucide-react'

import type { SimilarCandidate } from '@/api/types'
import { cn } from '@/lib/utils'

/**
 * 후보 카드 그리드 (IA 6.2 · 구상안 §4.3).
 *
 * **버전은 고르지 않는다.** 카드에 버전을 적지 않는다 — 비교 버전은 보고서 안에서 따로 고른다(구상안 §5.2).
 *
 * 선택 상태를 색으로만 알리지 않는다 — `추가` / `✓ 추가됨` 글자와 `aria-pressed` 를 함께 쓴다(IA §1-13).
 *
 * 이름이 길면(`@opentelemetry/winston-transport`) 한 줄로 자르고 전체 이름은 `title` 로 둔다 —
 * 예전에는 긴 이름이 카드 밖으로 넘쳤다.
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
          <li key={c.name} className="min-w-0">
            <button
              type="button"
              onClick={() => onToggle(c.name)}
              aria-pressed={on}
              aria-label={`${c.name} ${on ? '비교에서 빼기' : '비교에 추가'}`}
              className={cn(
                'flex h-full w-full flex-col gap-3 rounded-2xl border bg-card p-5 text-left transition-[border-color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40',
                on
                  ? 'border-primary shadow-[0_6px_20px_-12px_rgba(15,23,42,0.45)]'
                  : 'hover:border-primary/40',
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <span
                  title={c.name}
                  className="min-w-0 truncate font-mono text-xl leading-tight font-bold tracking-tight"
                >
                  {c.name}
                </span>
                <span
                  aria-hidden
                  className={cn(
                    'flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-medium',
                    on ? 'bg-primary text-primary-foreground' : 'border text-muted-foreground',
                  )}
                >
                  {on ? (
                    <>
                      <CheckIcon className="size-3.5" strokeWidth={3} />
                      추가됨
                    </>
                  ) : (
                    <>
                      <PlusIcon className="size-3.5" />
                      추가
                    </>
                  )}
                </span>
              </div>

              {/*
                설명이 없을 수 있다. 그때 자리를 비워 두면 카드 높이가 서로 달라져
                "이 카드는 뭔가 빠졌다" 가 아니라 "정렬이 깨졌다" 로 보인다.
              */}
              <p className="line-clamp-3 leading-relaxed text-muted-foreground">
                {c.description ?? '등록된 설명이 없어요.'}
              </p>

              <p className="mt-auto flex flex-wrap gap-x-2 border-t pt-3 text-sm text-muted-foreground">
                <span>
                  비슷한 순서{' '}
                  <span className="font-mono text-foreground tabular-nums">{c.rank}위</span>
                </span>
              </p>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
