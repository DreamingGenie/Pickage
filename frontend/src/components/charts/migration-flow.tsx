import { FLOW_FILLS } from '@/components/charts/tokens'
import { EvidenceBadge, VariantBadge } from '@/routes/report/ecosystem/migration-badges'
import {
  coveredPct,
  observationHint,
  type MigrationDestination,
  type PackageMigration,
} from '@/routes/report/ecosystem/migration-model'
import { cn } from '@/lib/utils'

/**
 * 교체 흐름 막대 — 패키지 하나 (S15P21A506-424).
 *
 * <h2>가로 누적 막대의 **전체 폭이 100%다**</h2>
 *
 * 이 막대는 도착지끼리의 상대 크기를 그리는 것이 아니라 **관측된 이동 전체에서 각
 * 도착지가 차지하는 몫**을 그린다. 그래서 채워지지 않고 남는 자리가 생기고, 그 자리가
 * 이 화면에서 가장 중요한 정보다.
 *
 * <b>남는 자리를 없애려고 정규화하면 안 된다.</b> `share_pm_pct` 의 분모는 빌더가
 * `lift>=5` 인 쌍 전체로 잡는데 표에는 근거가 약한 것을 뺀 나머지만 적재된다. 실측하면
 * 출발 패키지 7,141개 중 5,688개(79.7%)의 합이 99.5% 에 못 미치고 <b>중앙값이 25.7%</b>
 * 다. 100 으로 맞추면 모든 도착지의 점유율이 네 배 가까이 부풀려진다.
 *
 * 그래서 남는 자리를 빗금으로 그리고 "근거가 약해 뺀 이동" 이라고 이름을 준다. 비어
 * 있는 것이 아니라 <b>세었지만 싣지 않은 것</b>이라는 뜻이다.
 *
 * <h2>`RemovalBars` 가 도넛인데 이쪽은 막대인 이유</h2>
 *
 * 저쪽은 두 범주가 항상 100%를 채우므로 도넛이 그 사실을 형태로 보장한다. 이쪽은 정반대다
 * — <b>100%를 채우지 못한다는 것</b>이 요점이라, 채우다 만 것이 보이는 형태여야 한다.
 * 도넛으로 그리면 남는 호가 "없는 범주" 처럼 읽힌다.
 */
export function MigrationFlowBar({
  pkg,
  className,
}: {
  pkg: PackageMigration
  className?: string
}) {
  if (pkg.dataStatus === 'COMPLETE' || pkg.dataStatus === 'INSUFFICIENT_EVIDENCE') {
    return <FlowBody pkg={pkg} className={className} />
  }

  const message =
    pkg.dataStatus === 'NO_DATA'
      ? '이동이 관측되지 않았어요'
      : pkg.dataStatus === 'OUT_OF_SCOPE'
        ? '분석 대상 아님 · 자료가 없는 패키지예요'
        : '준비 중'

  return (
    <div className={cn('flex min-h-32 flex-col items-center justify-center', className)}>
      <p className="text-base text-muted-foreground">{message}</p>
    </div>
  )
}

function FlowBody({ pkg, className }: { pkg: PackageMigration; className?: string }) {
  const covered = coveredPct(pkg)
  const dropped = Math.max(0, 100 - covered)
  const weak = pkg.dataStatus === 'INSUFFICIENT_EVIDENCE'

  /**
   * **한쪽만 반올림하고 다른 쪽은 100 에서 뺀다.** 둘을 각자 반올림하면 합이 101%(또는
   * 99%)가 된다 — covered 44.5 · dropped 55.5 면 45 와 56 이다. 형제 컴포넌트
   * `RemovalBars` 가 같은 이유로 같은 규칙을 쓴다.
   */
  const coveredPercent = Math.round(covered)
  const droppedPercent = 100 - coveredPercent

  /**
   * 반올림하면 0 이 되는 나머지. **"나머지 0% 를 뺐어요" 는 자기 모순이라** 따로 말한다 —
   * 합이 99.6 인 패키지가 실제로 있다(반올림 때문에 100.2 까지 나온다).
   */
  const droppedIsTiny = dropped > 0 && droppedPercent === 0

  return (
    <div className={cn('flex w-full max-w-72 flex-col gap-3', className)}>
      {/*
        role="img" + aria-label — 막대 조각마다 title 을 달면 스크린리더가 폭을 순서대로
        읽어 주지만, 이 그림의 요점은 개별 폭이 아니라 "얼마나 못 채웠나" 다.
      */}
      <div
        role="img"
        aria-label={`관측된 이동 중 ${coveredPercent}%가 집계에 들어왔고 ${droppedPercent}%는 근거가 약해 빠졌어요`}
        className="flex h-6 w-full overflow-hidden rounded-md border bg-muted/40"
      >
        {pkg.destinations.map((d, i) => (
          <span
            key={d.name}
            style={{ width: `${d.sharePmPct}%`, background: FLOW_FILLS[i % FLOW_FILLS.length] }}
            title={`${d.name} ${d.sharePmPct.toFixed(1)}%`}
          />
        ))}
        {pkg.etc && (
          <span
            style={{ width: `${pkg.etc.sharePmPct}%` }}
            className="bg-muted-foreground/35"
            title={`그 밖 ${pkg.etc.pairs}개 ${pkg.etc.sharePmPct.toFixed(1)}%`}
          />
        )}
        {/* 남는 자리. 배경색으로 두면 "빈 칸" 으로 읽혀 요점이 사라진다 — 빗금으로 채운다. */}
        {dropped > 0 && (
          <span
            style={{ width: `${dropped}%` }}
            className="bg-[repeating-linear-gradient(45deg,transparent,transparent_3px,rgb(148_163_184/0.45)_3px,rgb(148_163_184/0.45)_6px)]"
            title={`근거가 약해 뺀 이동 ${dropped.toFixed(1)}%`}
          />
        )}
      </div>

      {weak ? (
        <p className="text-base text-muted-foreground">
          이동은 <strong className="text-foreground">{pkg.observedPairs ?? 0}건</strong> 관측됐지만
          전부 근거가 약해서 이름을 세우지 않았어요.
        </p>
      ) : (
        <dl className="flex flex-col gap-1.5">
          {pkg.destinations.map((d, i) => (
            <DestinationRow
              key={d.name}
              from={pkg.key}
              dest={d}
              fill={FLOW_FILLS[i % FLOW_FILLS.length]}
            />
          ))}
          {pkg.etc && (
            <div className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-[3px] bg-muted-foreground/35"
                aria-hidden
              />
              <dt className="text-base text-muted-foreground">그 밖 {pkg.etc.pairs}곳</dt>
              <dd className="ml-auto font-mono text-base text-muted-foreground tabular-nums">
                {pkg.etc.sharePmPct.toFixed(1)}%
              </dd>
            </div>
          )}
        </dl>
      )}

      {dropped > 0 && (
        <p className="text-base text-muted-foreground">
          나머지{' '}
          <strong className="text-foreground">
            {droppedIsTiny ? '1% 미만' : `${droppedPercent}%`}
          </strong>
          {/* 조사가 갈린다 — "36%는"(모음)과 "1% 미만은"(받침). 한 벌로 쓰면 한쪽이 어색하다. */}
          {droppedIsTiny ? '은' : '는'} 근거가 약해 집계에서 뺐어요.
        </p>
      )}
    </div>
  )
}

function DestinationRow({
  from,
  dest,
  fill,
}: {
  /** 출발 패키지 이름. 말풍선 문장이 "winston 을 지운…" 으로 시작한다. */
  from: string
  dest: MigrationDestination
  fill: string
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="h-2.5 w-2.5 shrink-0 rounded-[3px]"
        style={{ background: fill }}
        aria-hidden
      />
      <dt className="truncate font-mono text-base text-foreground">{dest.name}</dt>
      {/*
        배지 둘 다 **모달의 풀이표와 같은 문장**을 툴팁으로 단다. 낱말만 떠 있으면 서비스가
        임의로 매긴 점수로 읽히고, 여기서 따로 문장을 쓰면 두 곳이 갈라진다.
      */}
      {dest.variant && <VariantBadge />}
      <EvidenceBadge evidence={dest.evidence} hint={observationHint(from, dest)} />
      <dd className="ml-auto shrink-0 font-mono text-base text-foreground tabular-nums">
        {dest.sharePmPct.toFixed(1)}%
      </dd>
    </div>
  )
}
