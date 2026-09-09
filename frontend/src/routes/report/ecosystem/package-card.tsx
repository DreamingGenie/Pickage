import { ChevronDownIcon } from 'lucide-react'

import { seriesStyle } from '@/components/charts/tokens'
import { ShareBars, ShareDonut } from '@/components/charts/version-share'
import { ObservationBadges } from '@/routes/report/ecosystem/badges'
import type { PackageCardModel } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 패키지 카드.
 *
 * 기본은 전부 펼침. 여러 개를 동시에 펼 수 있고, 직접 접기 전까지 닫히지 않는다.
 *
 * 접힘: 패키지 이름과 최신 버전. 그리고 그 패키지 선이 차트에서 물러난다.
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
        {model.isDeprecated && (
          <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800">
            폐기 표시
          </span>
        )}
      </div>
      <span className="flex shrink-0 items-center gap-2">
        <span className="font-mono text-[11px] text-muted-foreground">v{model.latestVersion}</span>
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

      {model.description && (
        <p className="-mt-2 text-[12.5px] leading-relaxed text-muted-foreground">
          {model.description}
        </p>
      )}

      <ObservationBadges model={model} />

      {/* Dependents 증감 — 유입·이탈로 나누지 않는다. 합계값이라 그렇게 나눌 수 없다 */}
      <div className="flex items-baseline justify-between gap-3 border-t pt-5">
        <span className="text-[12px] text-muted-foreground">Dependents 증감</span>
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-[17px] leading-none font-semibold tabular-nums">
            {delta === null
              ? '—'
              : `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toLocaleString()}`}
          </span>
          <span className="text-[10.5px] text-muted-foreground">
            {delta === null ? '점이 부족합니다' : '화면에 뜬 구간'}
          </span>
        </span>
      </div>

      {/* Version Share */}
      <div className="flex flex-col gap-3 border-t pt-5">
        <span className="text-[12px] text-muted-foreground">Version Share</span>
        {model.versionShare.length === 0 ? (
          <p className="text-[11.5px] text-muted-foreground">
            이 시점의 버전 분포 자료가 없습니다.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-5">
              <ShareDonut
                groups={model.versionShare}
                size={104}
                ariaLabel={`${model.key} major 버전 분포`}
              />
              <ShareBars groups={model.versionShare} />
            </div>
            {/*
              명세 §5·§6 — 조각 합계는 버전별 합산이라 실제 사용처 수보다 크다.
              그래서 비율만 적고 총계를 쓰지 않는다.
            */}
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              공개된 의존 조건을 major 단위로 묶은 비율입니다. 실제 설치 버전이 아니고, 한
              프로젝트가 여러 버전에 걸릴 수 있어 합계는 실제 사용처 수보다 큽니다.
            </p>
          </>
        )}
      </div>

      {/* 라이선스·최신 릴리스는 판단 재료라 카드 맨 아래에 조용히 둔다 */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-4 text-[11px] text-muted-foreground">
        <span>{model.licenses.length ? model.licenses.join(' · ') : '라이선스 미상'}</span>
        <span className="font-mono">최신 릴리스 {model.publishedAt.slice(0, 10)}</span>
        {model.repoUrl && <span className="truncate font-mono">{model.repoUrl}</span>}
      </div>
    </button>
  )
}
