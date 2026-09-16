import { ChevronDownIcon } from 'lucide-react'

import { errorNotice } from '@/api/client'
import { seriesStyle } from '@/components/charts/tokens'
import { ShareBars, ShareDonut } from '@/components/charts/version-share'
import { Skeleton } from '@/components/ui/skeleton'
import { ObservationBadges } from '@/routes/report/ecosystem/badges'
import {
  ALL_MAJORS,
  type MajorSelection,
  type MetricState,
  type PackageCardModel,
} from '@/routes/report/ecosystem/model'
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
  selectedVersion,
  onVersionChange,
  versionShareState = { status: 'ready' },
}: {
  model: PackageCardModel
  index: number
  expanded: boolean
  onToggle: () => void
  /** 구상안 §5.2 — 이 카드만의 표시 버전들. 다른 카드와 독립이다. 빈 배열이 "전체". */
  selectedVersion: MajorSelection
  onVersionChange: (next: MajorSelection) => void
  /** Version Share 조회의 처지(126) — 응답 하나가 전체 카드를 담으므로 카드마다 갈리지 않는다. */
  versionShareState?: MetricState
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
        <span className="truncate font-mono text-base font-medium">{model.key}</span>
        {isBase && (
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-base text-muted-foreground">
            기준
          </span>
        )}
        {model.isDeprecated && (
          <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-base text-amber-800">
            폐기 표시
          </span>
        )}
      </div>
      <span className="flex shrink-0 items-center gap-2">
        <span className="font-mono text-base text-muted-foreground">v{model.latestVersion}</span>
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

  /*
    펼친 카드는 button 이 아니라 div 다. 안에 표시 버전 선택기가 들어가는데,
    button 안의 button 은 HTML 이 허용하지 않고 클릭이 바깥으로 새어 카드가 접힌다.
    접기는 머리글만 담당한다.
  */
  return (
    <div className="flex flex-col gap-6 rounded-2xl border border-foreground/40 bg-background p-6 text-left shadow-[0_4px_24px_-12px_rgba(15,23,42,0.35)]">
      <button type="button" onClick={onToggle} aria-expanded className="text-left">
        {header}
      </button>

      {model.description && (
        <p className="-mt-2 text-base leading-relaxed text-muted-foreground">{model.description}</p>
      )}

      <ObservationBadges model={model} />

      {/* Dependents — 표시 버전과 증감. 증감은 유입·이탈로 나누지 않는다(합계값이라 나눌 수 없다) */}
      <div className="flex flex-col gap-3 border-t pt-5">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-base text-muted-foreground">Dependents 증감</span>
          <span className="flex items-baseline gap-2">
            <span className="font-mono text-lg leading-none font-semibold tabular-nums">
              {delta === null
                ? '—'
                : `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toLocaleString()}`}
            </span>
            <span className="text-base text-muted-foreground">
              {delta === null ? '점이 부족합니다' : '화면에 뜬 구간'}
            </span>
          </span>
        </div>
        {/*
          311c — 표시 간격에 따라 "화면에 뜬 첫 점"이 구간 시작과 정확히 같지 않을 수 있다
          (`sampleEvery`가 뒤에서부터 솎기 때문). 그래서 실제로 증감을 낸 두 날짜를 그대로 적는다.
        */}
        {delta !== null && model.dependentsDeltaFrom && model.dependentsDeltaTo && (
          <p className="-mt-1.5 font-mono text-base text-muted-foreground">
            {model.dependentsDeltaFrom} ~ {model.dependentsDeltaTo}
          </p>
        )}

        <VersionPicker
          majors={model.availableMajors}
          selected={selectedVersion}
          onChange={onVersionChange}
          label={`${model.key} 표시 버전`}
        />
      </div>

      {/* Version Share — 126: "이 시점 자료 없음"과 "조회 실패"를 다른 문구로 분리한다 */}
      <div className="flex flex-col gap-3 border-t pt-5">
        <span className="text-base text-muted-foreground">Version Share</span>
        {versionShareState.status === 'loading' ? (
          <Skeleton className="h-28 w-full rounded-xl" />
        ) : versionShareState.status === 'error' ? (
          <VersionShareError error={versionShareState.error} onRetry={versionShareState.onRetry} />
        ) : model.versionShare.length === 0 ? (
          <p className="text-base text-muted-foreground">이 시점의 버전 분포 자료가 없습니다.</p>
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
            <p className="text-base leading-relaxed text-muted-foreground">
              공개된 의존 조건을 major 단위로 묶은 비율입니다. 실제 설치 버전이 아니고, 한
              프로젝트가 여러 버전에 걸릴 수 있어 합계는 실제 사용처 수보다 큽니다.
            </p>
            {/* 개요의 snapshotAt(카드 전체 공통 기준일)과 다른 값일 수 있어 따로 적는다 */}
            {model.versionShareSnapshotAt && (
              <p className="font-mono text-base text-muted-foreground">
                기준일 {model.versionShareSnapshotAt}
              </p>
            )}
          </>
        )}
        {versionShareState.status === 'ready' && versionShareState.refreshError !== undefined && (
          <p className="-mt-1.5 flex flex-wrap items-baseline gap-2 text-base leading-relaxed text-muted-foreground">
            <span>최신 자료를 받지 못해 마지막으로 받은 것을 그렸습니다.</span>
            {versionShareState.onRetry && errorNotice(versionShareState.refreshError).retryable && (
              <button
                type="button"
                onClick={versionShareState.onRetry}
                className="underline underline-offset-2 hover:text-foreground"
              >
                다시 시도
              </button>
            )}
          </p>
        )}
      </div>

      {/* 라이선스·최신 릴리스는 판단 재료라 카드 맨 아래에 조용히 둔다 */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t pt-4 text-base text-muted-foreground">
        <span>{model.licenses.length ? model.licenses.join(' · ') : '라이선스 미상'}</span>
        <span className="font-mono">최신 릴리스 {model.publishedAt.slice(0, 10)}</span>
        {model.repoUrl && <span className="truncate font-mono">{model.repoUrl}</span>}
      </div>
    </div>
  )
}

/**
 * 표시 버전 선택기 (구상안 §5.2). **여러 개를 고를 수 있고, 고른 것을 합한다.**
 *
 * **이 카드의 Dependents 선만 바꾼다.** 다른 카드도, 버전 분포도, 기능 비교도 건드리지 않는다.
 * 서버에 다시 묻지도 않는다 — major 별 시리즈를 이미 다 받아 두었다.
 *
 * "전체" 는 **모두 끄는 버튼**이지 다른 버전들과 나란한 선택지가 아니다. 같은 줄에 두면
 * "전체 + 4.x" 를 동시에 누를 수 있어 보이는데, 그건 뜻이 없는 상태다.
 *
 * 마지막 하나를 끄면 자동으로 전체로 돌아간다 — 아무것도 안 고른 빈 그래프는 조작 실수이지
 * 보고 싶은 화면이 아니다.
 *
 * 고를 것이 없으면(자료 없음, 또는 major 가 하나뿐) 선택기를 그리지 않는다.
 * 누를 수 없는 버튼 한 개는 조작할 수 있다는 잘못된 신호를 준다.
 *
 * 선택 상태를 색으로만 알리지 않는다 — `aria-pressed` 와 테두리를 함께 쓴다.
 */
function VersionPicker({
  majors,
  selected,
  onChange,
  label,
}: {
  majors: string[]
  selected: MajorSelection
  onChange: (next: MajorSelection) => void
  label: string
}) {
  if (majors.length < 2) return null

  const isAll = selected.length === 0

  function toggle(major: string) {
    const next = selected.includes(major)
      ? selected.filter((m) => m !== major)
      : [...selected, major]
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-pressed={isAll}
          onClick={() => onChange(ALL_MAJORS)}
          className={cn(
            'rounded-md border px-2 py-1 text-base transition-colors duration-150',
            isAll
              ? 'border-foreground/50 bg-foreground/[0.06] font-medium text-foreground'
              : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
          )}
        >
          전체
        </button>

        <span aria-hidden className="mx-0.5 h-4 w-px bg-border" />

        {majors.map((m) => {
          const active = selected.includes(m)
          return (
            <button
              key={m}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(m)}
              className={cn(
                'rounded-md border px-2 py-1 font-mono text-base transition-colors duration-150',
                active
                  ? 'border-foreground/50 bg-foreground/[0.06] font-medium text-foreground'
                  : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
              )}
            >
              {m}.x
            </button>
          )
        })}
      </div>
      <p className="text-base leading-relaxed text-muted-foreground">
        {isAll
          ? '전 버전을 합한 값입니다. 여러 개를 골라 합쳐 볼 수 있습니다.'
          : `고른 ${selected.length}개 버전을 합한 값입니다. 다른 패키지의 선택과는 무관합니다.`}
      </p>
    </div>
  )
}

/**
 * Version Share 조회 자체가 실패했을 때. "이 시점 자료 없음"(정상 200, 빈 배열)과는
 * 다른 문구를 쓴다 — 전자는 조회했지만 그 시점 자료가 없다는 뜻이고, 이건 조회를 못 했다는 뜻이다.
 */
function VersionShareError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const notice = errorNotice(error)
  return (
    <div className="flex flex-col items-start gap-2 rounded-xl border border-dashed px-4 py-3 text-base text-muted-foreground">
      <span className="font-medium text-foreground">{notice.message}</span>
      {onRetry && notice.retryable && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border px-3 py-1.5 text-xs transition-colors hover:border-foreground/40"
        >
          다시 시도
        </button>
      )}
    </div>
  )
}
