import { useMemo, useState } from 'react'

import { SeriesLegend } from '@/components/charts/line-chart'
import { dependentsLineOf } from '@/routes/report/ecosystem/adapter'
import {
  EcosystemToolbar,
  type EcosystemControls,
} from '@/routes/report/ecosystem/ecosystem-toolbar'
import { MetricChart } from '@/routes/report/ecosystem/metric-chart'
import { PackageCard } from '@/routes/report/ecosystem/package-card'
import {
  ALL_MAJORS,
  type EcosystemModel,
  type MajorSelection,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 생태계 변화.
 *
 * 하나의 큰 카드로 묶지 않는다. 공통 조작줄과 범례가 위에 있고,
 * Dependents · Downloads 는 각자 독립 카드로 위아래에 쌓인다.
 * 시간축이 같으므로 세로로 겹쳐 읽는 편이 좌우로 나누는 것보다 대조가 쉽다.
 *
 * 별 수·이슈·폐기 표시는 시계열로 그리지 않고 패키지 카드의 뱃지로 낸다 —
 * 명세 §3 이 그 둘을 현재값 + 직전 스냅샷 대비 증감으로만 주기 때문이다.
 *
 * 조회 기간은 **부모가 들고 있다.** 그것만 서버 왕복을 부르기 때문이다.
 * 구간·간격은 받은 점을 다루는 일이라 여기 안에서 끝난다.
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
   * 고를 수 있는 스냅샷 날짜. 지표마다 관측 시작이 다르므로 **합집합**을 쓴다.
   * 좁은 지표는 자기 카드 안에서 잘리고 그 사실을 스스로 알린다.
   */
  const snapshots = useMemo(() => {
    const set = new Set<string>()
    for (const key of ['dependents', 'downloads'] as const) {
      for (const s of model.series[key]) for (const p of s.points) set.add(p.t)
    }
    return [...set].sort()
  }, [model])

  /**
   * 구간·간격. 조회 기간이 바뀌면 스냅샷 목록 자체가 갈리므로 구간을 되돌린다.
   * effect 로 동기화하는 대신 목록을 열쇠로 삼아 렌더에서 파생시킨다 —
   * 상태가 두 곳에 갈라지지 않는다.
   */
  const bounds = { start: snapshots[0] ?? '', end: snapshots[snapshots.length - 1] ?? '' }
  const [local, setLocal] = useState<{ key: string; window: EcosystemControls['window'] }>(() => ({
    key: `${bounds.start}~${bounds.end}`,
    window: bounds,
  }))
  const [intervalKey, setIntervalKey] = useState('1w')

  const boundsKey = `${bounds.start}~${bounds.end}`
  const window = local.key === boundsKey ? local.window : bounds

  const controls: EcosystemControls = { window, intervalKey }

  function onControlsChange(next: EcosystemControls) {
    setIntervalKey(next.intervalKey)
    setLocal({ key: boundsKey, window: next.window })
  }

  /**
   * 카드별 표시 버전 (구상안 §5.2). **패키지마다 독립이다.**
   *
   * 서버 왕복이 없다 — major 별 시리즈를 이미 다 받아 두었고 여기서 고르거나 더할 뿐이다.
   * 비교 조합이 바뀌면 선택을 되돌린다. 없어진 패키지의 선택이 남아 있으면 다음에 같은
   * 이름이 들어왔을 때 엉뚱한 버전으로 시작한다.
   */
  const [versions, setVersions] = useState<{
    key: string
    byName: Record<string, MajorSelection>
  }>({ key: '', byName: {} })

  const versionKey = model.packages.map((p) => p.key).join(',')
  const versionByName = versions.key === versionKey ? versions.byName : {}

  function selectVersion(name: string, next: MajorSelection) {
    setVersions({ key: versionKey, byName: { ...versionByName, [name]: next } })
  }

  /**
   * 고른 버전이 반영된 Dependents 선과 카드.
   *
   * 증감도 여기서 다시 센다 — 4.x 만 보고 있는데 증감이 전 버전 합계면 카드 안의 두 숫자가
   * 서로 다른 것을 가리키게 된다.
   */
  const dependentsSeries = model.packages.map((p) =>
    dependentsLineOf(
      p.key,
      model.dependentsByMajor[p.key] ?? [],
      versionByName[p.key] ?? ALL_MAJORS,
    ),
  )

  const seriesByName = new Map(dependentsSeries.map((s) => [s.key, s]))
  const packages = model.packages.map((p) => {
    const points = seriesByName.get(p.key)?.points ?? []
    return {
      ...p,
      dependentsDelta: points.length < 2 ? null : points[points.length - 1].v - points[0].v,
    }
  })

  /**
   * 펼쳐진 패키지. 기본은 전부 펼침이고 여러 개를 동시에 열어 둘 수 있다.
   * 접힌 패키지는 차트에서도 물러난다 — 그래서 선택이 아니라 펼침 상태가 강조를 정한다.
   */
  const packageKeys = model.packages.map((p) => p.key).join(',')
  const [collapsed, setCollapsed] = useState<{ key: string; keys: string[] }>({
    key: packageKeys,
    keys: [],
  })
  const collapsedKeys = collapsed.key === packageKeys ? collapsed.keys : []
  const expanded = model.packages.map((p) => p.key).filter((k) => !collapsedKeys.includes(k))

  const height = compactChart ? 148 : 196

  return (
    <div className={cn('flex flex-col gap-5', className)}>
      {/* 0.2 — 부분 실패. 못 찾은 이름은 조용히 사라지면 안 된다 */}
      {model.notFound.length > 0 && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          찾지 못한 패키지:{' '}
          <span className="font-mono text-foreground">{model.notFound.join(', ')}</span> — 이름을
          확인해 주세요. 나머지는 그대로 표시했습니다.
        </p>
      )}

      <EcosystemToolbar controls={controls} onChange={onControlsChange} snapshots={snapshots} />

      {/*
        두 카드가 같은 선 모양을 쓰므로 범례도 한 번만.
        Dependents 쪽을 기준으로 삼는다 — 표시 버전을 고르면 라벨에 그 사실이 실려서
        (`express 4.x`) 어느 선이 무엇인지 범례만 봐도 알 수 있다.
      */}
      <SeriesLegend series={dependentsSeries} emphasisKeys={expanded} />

      {/*
        좌: 차트 둘, 우: 패키지 카드.

        차트를 세로로 쌓고 그 아래에 카드를 두면, **버전을 고르는 자리와 그 결과가 그려지는
        자리가 한 화면에 같이 안 들어온다.** 카드에서 4.x 를 눌러 놓고 위로 스크롤해서
        확인하고 다시 내려와야 한다. 좌우로 나누면 누르는 즉시 옆에서 선이 바뀌는 것이 보인다.

        차트 쪽을 `sticky` 로 붙여 둔다 — 카드가 길어져도 그래프가 화면에 남는다.

        좁은 화면에서는 한 줄로 무너진다. 그때는 차트가 먼저 오고 카드가 아래로 간다.
      */}
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(380px,1fr)]">
        <div className="flex min-w-0 flex-col gap-5 lg:sticky lg:top-4 lg:self-start">
          <MetricChart
            title="Dependents"
            unit="의존 수 · 버전별 합계"
            series={dependentsSeries}
            window={window}
            intervalKey={intervalKey}
            observedFrom={model.observedFrom.dependents}
            coverageNote="이 지표의 관측 시작"
            emphasisKeys={expanded}
            height={height}
          />
          <MetricChart
            title="Downloads"
            unit="주간 · npm 공식 자료"
            series={model.series.downloads}
            window={window}
            intervalKey={intervalKey}
            observedFrom={model.observedFrom.downloads}
            coverageNote="이 지표의 관측 시작"
            emphasisKeys={expanded}
            height={height}
          />
        </div>

        <div className="grid min-w-0 items-start gap-4">
          {packages.map((p, i) => (
            <PackageCard
              key={p.key}
              model={p}
              index={i}
              expanded={expanded.includes(p.key)}
              selectedVersion={versionByName[p.key] ?? ALL_MAJORS}
              onVersionChange={(next) => selectVersion(p.key, next)}
              onToggle={() =>
                setCollapsed({
                  key: packageKeys,
                  keys: collapsedKeys.includes(p.key)
                    ? collapsedKeys.filter((k) => k !== p.key)
                    : [...collapsedKeys, p.key],
                })
              }
            />
          ))}

          {/*
            카드가 하나도 없으면 접기 안내 자체를 내지 않는다.

            `expanded.length === 0` 은 **"사용자가 다 접었다" 와 "펼칠 것이 애초에 없다"
            두 상태를 같은 값으로 만든다.** 뒤쪽에서 "모든 패키지를 접었습니다" 가 뜨면
            하지도 않은 조작을 했다고 말하게 된다 — 이름이 전부 not_found 인 구간에서
            실제로 그렇게 떴다.
          */}
          {model.packages.length > 0 && (
            <p className="text-base leading-relaxed text-muted-foreground">
              {expanded.length === 0
                ? '모든 패키지를 접었습니다. 카드를 누르면 다시 펼쳐집니다.'
                : expanded.length < model.packages.length
                  ? `접힌 패키지는 차트에서도 흐려집니다. 펼침 ${expanded.length} / ${model.packages.length}`
                  : '카드를 누르면 접히고, 그 패키지 선이 차트에서 물러납니다.'}
            </p>
          )}
        </div>
      </div>

      <p className="font-mono text-base text-muted-foreground">
        {/* 기준일이 없다 = 아직 첫 스냅샷을 못 받았다. 장애가 아니라 자료 축적 중이다. */}
        {model.snapshotAt ? `기준 스냅샷 ${model.snapshotAt}` : '기준 스냅샷 없음 — 데이터 축적 중'}
      </p>
    </div>
  )
}
