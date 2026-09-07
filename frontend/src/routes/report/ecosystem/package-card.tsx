import { ChevronDownIcon } from 'lucide-react'

import { seriesStyle } from '@/components/charts/tokens'
import { ShareBars, ShareDonut } from '@/components/charts/version-share'
import { ObservationBadges } from '@/routes/report/ecosystem/badges'
import { TOTAL, type PackageCardModel } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 패키지 카드.
 *
 * 기본은 전부 펼침. 여러 개를 동시에 펼 수 있고, 직접 접기 전까지 닫히지 않는다.
 *
 * 접힘: 패키지 이름만. 그리고 그 패키지 선이 차트에서 물러난다.
 * 펼침: 뱃지 · Dependents 증감 · Version Share 상세.
 *
 * 접힘 상태에도 선 견본은 남긴다 — 그래프의 어느 선이 이 패키지인지
 * 알 수 없으면 접힌 목록이 쓸모없어진다.
 */
export function PackageCard({
  model,
  index,
  expanded,
  onToggle,
}: {
  model: PackageCardModel
  index: number
  expanded: boolean
  onToggle: () => void
}) {
  const style = seriesStyle(index)
  const isBase = index === 0
  const delta = model.dependentsDelta

  const header = (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2.5">
        <svg width="20" height="8" aria-hidden className="shrink-0">
          <line
            x1="0"
            y1="4"
            x2="20"
            y2="4"
            stroke={style.color}
            strokeWidth="2.6"
            strokeDasharray={style.dash}
            strokeLinecap="round"
          />
        </svg>
        <span className="truncate font-mono text-[15px] font-medium">{model.key}</span>
        {isBase && (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            기준
          </span>
        )}
      </div>
      <span className="flex shrink-0 items-center gap-2">
        {expanded && (
          <span className="font-mono text-[11px] text-muted-foreground">
            {model.selectedDisplayVersion === TOTAL ? 'TOTAL' : model.selectedDisplayVersion}
          </span>
        )}
        <ChevronDownIcon
          aria-hidden
          className={cn(
            'size-4 text-muted-foreground transition-transform duration-200',
            expanded && 'rotate-180',
          )}
        />
      </span>
    </div>
  )

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={false}
        className="rounded-2xl border bg-background px-6 py-5 text-left transition-colors duration-200 hover:border-foreground/30 hover:bg-muted/30"
      >
        {header}
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded
      className="flex flex-col gap-6 rounded-2xl border border-foreground/40 bg-background p-6 text-left shadow-[0_4px_24px_-12px_rgba(15,23,42,0.35)]"
    >
      {header}

      <ObservationBadges model={model} />

      {/* Dependents 증감 — 유입·이탈로 나누지 않는다 */}
      <div className="flex items-baseline justify-between gap-3 border-t pt-5">
        <span className="text-[12px] text-muted-foreground">Dependents 증감</span>
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-[17px] leading-none font-semibold tabular-nums">
            {delta === null
              ? '—'
              : `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toLocaleString()}`}
          </span>
          <span className="text-[10.5px] text-muted-foreground">기간 전체</span>
        </span>
      </div>

      {/* Version Share 상세 */}
      <div className="flex flex-col gap-3 border-t pt-5">
        <span className="text-[12px] text-muted-foreground">Version Share</span>
        <div className="flex flex-wrap items-center gap-5">
          <ShareDonut
            groups={model.versionShare}
            size={104}
            ariaLabel={`${model.key} 버전 계열 분포`}
          />
          <ShareBars groups={model.versionShare} />
        </div>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          공개된 의존 조건의 분포입니다. 실제 설치 버전이 아닙니다.
        </p>
      </div>
    </button>
  )
}
