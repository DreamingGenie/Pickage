import { useMemo, useState } from 'react'

import { SeriesLegend } from '@/components/charts/line-chart'
import {
  EcosystemToolbar,
  type EcosystemControls,
} from '@/routes/report/ecosystem/ecosystem-toolbar'
import { MetricChart } from '@/routes/report/ecosystem/metric-chart'
import { PackageCard } from '@/routes/report/ecosystem/package-card'
import { TOTAL, type EcosystemModel, type PackageCardModel } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 03A 생태계 변화.
 *
 * 하나의 큰 카드로 묶지 않는다. 공통 조작줄과 범례가 위에 있고,
 * Dependents · Activity 는 각자 독립 카드로 위아래에 쌓인다(IA 8.1).
 * 시간축이 같으므로 세로로 겹쳐 읽는 편이 좌우로 나누는 것보다 대조가 쉽다.
 *
 * 별 수·이슈·폐기 표시는 시계열로 그리지 않고 패키지 카드의 뱃지로 낸다.
 *
 * 패키지 카드는 기본이 전부 펼침이다. 서로 배타적이지 않아 여러 개를 동시에 열어 둘 수 있고,
 * 직접 접기 전까지 닫히지 않는다. 접은 패키지는 차트에서도 흐려진다.
 */
export function EcosystemView({
  model,
  compactChart = false,
  className,
}: {
  model: EcosystemModel
  /** 인트로 미리보기처럼 좁은 자리에 넣을 때 */
  compactChart?: boolean
  className?: string
}) {
  /**
   * 고를 수 있는 스냅샷 날짜. 지표마다 커버리지가 다르므로 **넓은 쪽**을 목록으로 쓴다.
   * 좁은 지표는 자기 카드 안에서 잘리고 그 사실을 스스로 알린다.
   */
  const snapshots = useMemo(() => {
    const set = new Set<string>()
    for (const key of ['dependents', 'downloads'] as const) {
      for (const s of model.series[key]) for (const p of s.points) set.add(p.t)
    }
    return [...set].sort()
  }, [model])

  const [controls, setControls] = useState<EcosystemControls>(() => ({
    // 기본은 최근 52개 스냅샷
    window: {
      start: snapshots[Math.max(0, snapshots.length - 52)],
      end: snapshots[snapshots.length - 1],
    },
    intervalKey: '1w',
  }))
  /**
   * 펼쳐진 패키지. 기본은 전부 펼침이고 여러 개를 동시에 열어 둘 수 있다.
   * 접힌 패키지는 차트에서도 물러난다 — 그래서 선택이 아니라 펼침 상태가 강조를 정한다.
   */
  const [expanded, setExpanded] = useState<string[]>(() => model.packages.map((p) => p.key))
  const [versions, setVersions] = useState<Record<string, string>>(() =>
    Object.fromEntries(model.packages.map((p) => [p.key, p.selectedDisplayVersion])),
  )

  const packages: PackageCardModel[] = model.packages.map((p) => ({
    ...p,
    selectedDisplayVersion: versions[p.key] ?? TOTAL,
  }))

  const height = compactChart ? 148 : 196

  return (
    <div className={cn('flex flex-col gap-5', className)}>
      <EcosystemToolbar
        controls={controls}
        onChange={setControls}
        snapshots={snapshots}
        packages={packages}
        onVersionChange={(key, v) => setVersions((prev) => ({ ...prev, [key]: v }))}
      />

      {/* 두 카드가 같은 시리즈·같은 선 모양을 쓰므로 범례도 한 번만 */}
      <SeriesLegend series={model.series.dependents} emphasisKeys={expanded} />

      {/* 세로로 쌓는다. 같은 시간축을 위아래로 겹쳐 읽는 게 나란히 두는 것보다 낫다 */}
      <div className="flex flex-col gap-5">
        <MetricChart
          title="Dependents"
          unit="직접 의존 패키지 수"
          series={model.series.dependents}
          window={controls.window}
          intervalKey={controls.intervalKey}
          observedFrom={model.observedFrom.dependents}
          coverageNote={model.coverageNote?.dependents}
          emphasisKeys={expanded}
          height={height}
        />
        <MetricChart
          title="Activity"
          unit="Downloads · 주간 · npm 공식 자료"
          series={model.series.downloads}
          window={controls.window}
          intervalKey={controls.intervalKey}
          observedFrom={model.observedFrom.downloads}
          coverageNote={model.coverageNote?.downloads}
          emphasisKeys={expanded}
          height={height}
        />
      </div>

      <div className="grid items-start gap-4">
        {packages.map((p, i) => (
          <PackageCard
            key={p.key}
            model={p}
            index={i}
            expanded={expanded.includes(p.key)}
            onToggle={() =>
              setExpanded((cur) =>
                cur.includes(p.key) ? cur.filter((k) => k !== p.key) : [...cur, p.key],
              )
            }
          />
        ))}
      </div>

      <p className="text-[11px] text-muted-foreground">
        {expanded.length === 0
          ? '모든 패키지를 접었습니다. 카드를 누르면 다시 펼쳐집니다.'
          : expanded.length < model.packages.length
            ? `접힌 패키지는 차트에서도 흐려집니다. 펼침 ${expanded.length} / ${model.packages.length}`
            : '카드를 누르면 접히고, 그 패키지 선이 차트에서 물러납니다.'}
      </p>
    </div>
  )
}
