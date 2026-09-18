import { HatchDef } from '@/components/charts/version-share'
import { SHARE_FILLS } from '@/components/charts/tokens'
import type {
  TransitionCounts,
  TransitionDataStatus,
} from '@/routes/report/ecosystem/transitions-model'
import { cn } from '@/lib/utils'

type CategoryKey = 'retained' | 'inflowAdopted' | 'outflow' | 'unobserved'

/** 고정 네 범주. 항상 이 순서로, 항상 넷 다 그린다 — `unobserved`를 빼거나 `retained`에
 *  합치면 유지율이 실제보다 높게 보이는 거짓 그래프가 된다(1년 구간 기준 최대 75%p 차이). */
const CATEGORIES: { key: CategoryKey; label: string; fill: string }[] = [
  { key: 'retained', label: '유지', fill: SHARE_FILLS[0] },
  { key: 'inflowAdopted', label: '유입', fill: SHARE_FILLS[1] },
  { key: 'outflow', label: '이탈', fill: SHARE_FILLS[2] },
  { key: 'unobserved', label: '미관측', fill: SHARE_FILLS[3] },
]

const PLACEHOLDER_WIDTH = 40

/**
 * 유지·유입·이탈 네 범주 막대 — 패키지 하나 × kind 하나.
 *
 * `data_status`가 행 전체를 지배한다(백엔드 계약) — 카테고리별로 다른 상태를 섞지 않는다.
 * `OUT_OF_SCOPE`·`NOT_COMPUTED`를 0짜리 막대로 그리면 "아무도 안 쓴다"는 거짓말이 되므로,
 * 절대 `width: 0`이나 진짜 값처럼 보이는 자리로 그리지 않는다 — 둘 다 고정 placeholder
 * 폭에 서로 다른 질감(빗금 vs 점선 빈틀)을 써서 "값이 없다"는 것 자체가 형태로 보이게 한다.
 */
export function TransitionBars({
  counts,
  dataStatus,
  max,
  className,
}: {
  counts: TransitionCounts | null
  dataStatus: TransitionDataStatus
  /** 비교 중인 패키지 전체를 통틀어 호출자가 한 번 계산한 값 — 여기서 스케일을
   *  독립적으로 잡으면 패키지끼리 막대 길이를 비교할 수 없게 된다. */
  max: number
  className?: string
}) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <svg width="0" height="0" aria-hidden className="absolute">
        <HatchDef />
      </svg>
      {CATEGORIES.map((cat) => (
        <BarRow
          key={cat.key}
          label={cat.label}
          fill={cat.fill}
          value={counts ? counts[cat.key] : null}
          dataStatus={dataStatus}
          max={max}
        />
      ))}
      {dataStatus === 'NO_DATA' && <p className="text-base text-muted-foreground">의존자 없음</p>}
      {dataStatus === 'OUT_OF_SCOPE' && (
        <p className="text-base text-muted-foreground">분석 대상 아님 · top-100k 밖</p>
      )}
      {dataStatus === 'NOT_COMPUTED' && <p className="text-base text-muted-foreground">준비 중</p>}
      {dataStatus === 'COMPLETE' && counts && counts.inflowRaw !== counts.inflowAdopted && (
        <p className="-mt-0.5 text-base text-muted-foreground/80">
          원시 유입 {counts.inflowRaw.toLocaleString()} · 신규 {counts.inflowNew.toLocaleString()}건
          포함
        </p>
      )}
    </div>
  )
}

function BarRow({
  label,
  fill,
  value,
  dataStatus,
  max,
}: {
  label: string
  fill: string
  value: number | null
  dataStatus: TransitionDataStatus
  max: number
}) {
  const isPlaceholder = dataStatus === 'OUT_OF_SCOPE' || dataStatus === 'NOT_COMPUTED'
  const width = isPlaceholder
    ? PLACEHOLDER_WIDTH
    : value !== null && max > 0
      ? Math.max((value / max) * 100, value > 0 ? 2 : 0)
      : 0

  return (
    <div className="grid grid-cols-[52px_1fr_64px] items-center gap-2">
      <span className="text-base text-muted-foreground">{label}</span>
      <span
        className={cn(
          'h-2.5 overflow-hidden rounded-sm',
          dataStatus === 'NOT_COMPUTED' ? 'border border-dashed bg-transparent' : 'bg-muted',
        )}
      >
        {dataStatus === 'OUT_OF_SCOPE' ? (
          // CSS `background: url(#svg-pattern)`은 SVG 페인트 서버를 HTML 배경으로
          // 참조하는 비표준 방식이라 Chrome에서 렌더링되지 않는다(실기기 확인함,
          // `ShareBars`의 기존 `UNRESOLVED_FILL` 사용도 같은 문제를 잠재적으로 안고
          // 있으나 현재 데이터에 UNRESOLVED 조각이 없어 아직 드러나지 않았을 뿐이다).
          // 그래서 `fill` 속성으로 직접 참조되는 `<rect>`로 그린다 — 이건 표준이라
          // 크로스브라우저로 확실히 동작한다.
          <svg width="100%" height="100%" viewBox="0 0 100 10" preserveAspectRatio="none">
            <rect width={width} height="10" rx="2" fill="url(#pk-hatch)" />
          </svg>
        ) : dataStatus !== 'NOT_COMPUTED' ? (
          <span
            className="block h-full rounded-sm"
            style={{ width: `${width}%`, background: fill }}
          />
        ) : null}
      </span>
      <span className="text-right font-mono text-base text-muted-foreground tabular-nums">
        {isPlaceholder ? '—' : (value ?? 0).toLocaleString()}
      </span>
    </div>
  )
}
