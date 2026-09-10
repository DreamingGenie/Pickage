import { useMemo, useState } from 'react'

import { SeriesLegend } from '@/components/charts/line-chart'
import {
  EcosystemToolbar,
  type EcosystemControls,
} from '@/routes/report/ecosystem/ecosystem-toolbar'
import { MetricChart } from '@/routes/report/ecosystem/metric-chart'
import { PackageCard } from '@/routes/report/ecosystem/package-card'
import { type EcosystemModel } from '@/routes/report/ecosystem/model'
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
      {/*
        0.2 — 부분 실패. 못 찾은 이름은 조용히 사라지면 안 된다.

        **"나머지" 가 실제로 있을 때만 그렇게 말한다.** 요청한 이름이 전부 없으면
        부분 실패가 아니라 전부 실패이고, 그때 "나머지는 그대로 표시했습니다" 는
        화면에 보이지도 않는 무언가가 있다고 말하는 셈이다. 적재 직후 이름이
        하나도 안 맞는 구간에서 실제로 밟힌다.
      */}
      {model.notFound.length > 0 && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-[11.5px] text-muted-foreground">
          찾지 못한 패키지:{' '}
          <span className="font-mono text-foreground">{model.notFound.join(', ')}</span> — 이름을
          확인해 주세요.
          {model.packages.length > 0 && ' 나머지는 그대로 표시했습니다.'}
        </p>
      )}

      <EcosystemToolbar controls={controls} onChange={onControlsChange} snapshots={snapshots} />

      {/* 두 카드가 같은 시리즈·같은 선 모양을 쓰므로 범례도 한 번만 */}
      <SeriesLegend series={model.series.dependents} emphasisKeys={expanded} />

      {/* 세로로 쌓는다. 같은 시간축을 위아래로 겹쳐 읽는 게 나란히 두는 것보다 낫다 */}
      <div className="flex flex-col gap-5">
        <MetricChart
          title="Dependents"
          unit="의존 수 · 버전별 합계"
          series={model.series.dependents}
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

      <div className="grid items-start gap-4">
        {model.packages.map((p, i) => (
          <PackageCard
            key={p.key}
            model={p}
            index={i}
            expanded={expanded.includes(p.key)}
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
      </div>

      {/*
        카드가 하나도 없으면 접기 안내 자체를 내지 않는다.

        `expanded.length === 0` 은 **"사용자가 다 접었다" 와 "펼칠 것이 애초에 없다"
        두 상태를 같은 값으로 만든다.** 뒤쪽에서 "모든 패키지를 접었습니다" 가 뜨면
        하지도 않은 조작을 했다고 말하게 된다 — 이름이 전부 not_found 인 구간에서
        실제로 그렇게 떴다.
      */}
      {model.packages.length > 0 && (
        <p className="text-[11px] text-muted-foreground">
          {expanded.length === 0
            ? '모든 패키지를 접었습니다. 카드를 누르면 다시 펼쳐집니다.'
            : expanded.length < model.packages.length
              ? `접힌 패키지는 차트에서도 흐려집니다. 펼침 ${expanded.length} / ${model.packages.length}`
              : '카드를 누르면 접히고, 그 패키지 선이 차트에서 물러납니다.'}
        </p>
      )}

      <p className="font-mono text-[10.5px] text-muted-foreground">
        {/* 기준일이 없다 = 아직 첫 스냅샷을 못 받았다. 장애가 아니라 자료 축적 중이다. */}
        {model.snapshotAt ? `기준 스냅샷 ${model.snapshotAt}` : '기준 스냅샷 없음 — 데이터 축적 중'}
      </p>
    </div>
  )
}
