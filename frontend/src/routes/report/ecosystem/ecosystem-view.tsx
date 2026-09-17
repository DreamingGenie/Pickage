import { useMemo, useState } from 'react'

import { windowSeries } from '@/components/charts/geometry'
import { seriesStyle } from '@/components/charts/tokens'
import { deltaOf, dependentsLineOf } from '@/routes/report/ecosystem/adapter'
import {
  EcosystemToolbar,
  type EcosystemControls,
} from '@/routes/report/ecosystem/ecosystem-toolbar'
import { MetricChart } from '@/routes/report/ecosystem/metric-chart'
import { PackageCard } from '@/routes/report/ecosystem/package-card'
import {
  ALL_MAJORS,
  stepOf,
  type EcosystemModel,
  type MajorSelection,
  type MetricKey,
  type MetricState,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/** 지어낸 값을 그리는 자리(인트로 미리보기)의 기본값. 로딩도 실패도 없다. */
const READY: Record<MetricKey, MetricState> = {
  dependents: { status: 'ready' },
  downloads: { status: 'ready' },
}
const READY_STATE: MetricState = { status: 'ready' }

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
  metricState = READY,
  versionShareState = READY_STATE,
  compactChart = false,
  className,
}: {
  model: EcosystemModel
  /**
   * 지표별 처지. 기본은 둘 다 준비됨이다 — 인트로 미리보기처럼 지어낸 값을 그리는
   * 자리에는 로딩도 실패도 없다.
   */
  metricState?: Record<MetricKey, MetricState>
  /**
   * Version Share 조회의 처지. Dependency·Downloads와 별도 호출이라 따로 실패·로딩할 수
   * 있다(126) — 패키지마다 갈리지 않는다(응답 하나가 전체 패키지를 담는다).
   */
  versionShareState?: MetricState
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
  const dependentsSeries = model.packages.map((p, i) =>
    dependentsLineOf(
      p.key,
      model.dependentsByMajor[p.key] ?? [],
      versionByName[p.key] ?? ALL_MAJORS,
      // 선 모양은 자리 번호가 아니라 **비교 순서**를 따른다. 자료가 없어 걸러진 시리즈가
      // 생겨도 카드·범례·차트가 같은 모양을 가리킨다(`ChartSeries.tone`).
      i,
    ),
  )

  /**
   * 표시 구간·간격은 여기서 한 번만 계산해 차트와 카드 증감이 같은 것을 본다(311c).
   * `MetricChart`는 이미 이 결과를 받으므로 안에서 다시 자르지 않는다.
   */
  const step = stepOf(intervalKey)
  const windowedDependents = windowSeries(dependentsSeries, window.start, window.end, step)
  const windowedDownloads = windowSeries(model.series.downloads, window.start, window.end, step)

  const windowedByName = new Map(windowedDependents.map((s) => [s.key, s]))
  const packages = model.packages.map((p) => {
    // 어댑터와 같은 함수를 쓴다. 결측 처리를 두 곳에서 각자 하면 언젠가 갈린다.
    const delta = deltaOf(windowedByName.get(p.key))
    return {
      ...p,
      dependentsDelta: delta?.value ?? null,
      dependentsDeltaFrom: delta?.from ?? null,
      dependentsDeltaTo: delta?.to ?? null,
    }
  })

  /**
   * 상세를 보는 패키지들. 칩 줄에서 **여러 개를 고를 수 있다** — 셋 중 둘만 나란히 보는
   * 것이 비교의 실제 모양이라, 하나만 고르게 하면 그 비교를 못 한다.
   *
   * **"아무도 고르지 않은" 상태가 기본이다.** 처음부터 하나가 강조돼 있으면 나머지가
   * 흐려진 채로 화면이 열려 공정한 비교가 안 된다. 고른 게 없으면 강조도 없고(`null`)
   * 카드도 전부 펼친다 — 오른쪽 열이 통째로 비는 것보다 낫다.
   *
   * 비교 조합이 바뀌면 선택을 되돌린다. 없어진 패키지의 key 가 남아 있으면 강조가
   * 아무 선에도 걸리지 않아 전부 흐려진 화면이 된다.
   */
  const packageKeys = model.packages.map((p) => p.key).join(',')
  const [picked, setPicked] = useState<{ key: string; names: string[] }>({
    key: packageKeys,
    names: [],
  })
  const selected = picked.key === packageKeys ? picked.names : []
  const emphasisKeys = selected.length > 0 ? selected : null

  function togglePackage(name: string) {
    setPicked({
      key: packageKeys,
      names: selected.includes(name) ? selected.filter((k) => k !== name) : [...selected, name],
    })
  }

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
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          찾지 못한 패키지:{' '}
          <span className="font-mono text-foreground">{model.notFound.join(', ')}</span> — 이름을
          확인해 주세요.
          {model.packages.length > 0 && ' 나머지는 그대로 표시했습니다.'}
        </p>
      )}

      <EcosystemToolbar controls={controls} onChange={onControlsChange} snapshots={snapshots} />

      {/*
        칩 줄이 범례이면서 조작이다.

        선 견본과 이름을 이미 달고 있어서 범례가 하던 일을 그대로 한다 — 같은 정보를 두
        줄로 늘어놓지 않는다. 라벨은 Dependents 선의 것을 그대로 쓴다. 표시 버전을 고르면
        거기에 실려서(`express 4.x`) 어느 선이 무엇인지 이 줄만 봐도 알 수 있다.

        조작줄 바로 아래, 차트 위에 둔다. 강조는 **두 차트 모두**에 걸리는 조작이라
        한쪽 차트 옆이나 오른쪽 열에 있으면 무엇에 걸리는 조작인지 읽히지 않는다.

        진짜 tabs(`components/ui/tabs.tsx`)를 쓰지 않는다 — Radix Tabs 는 항상 하나가
        active 여야 해서 "아무것도 고르지 않은" 상태도, "둘을 동시에 고른" 상태도
        표현할 수 없다.

        맨 앞 `모두` 는 선택을 비우는 자리다. 선택이 비어 있을 때 눌린 것처럼 보이는
        유일한 칩이기도 해서, 지금 무엇을 보고 있는지가 줄 하나로 읽힌다.
      */}
      {model.packages.length > 0 && (
        <div
          role="group"
          aria-label="강조할 패키지 선택"
          className="flex flex-wrap items-center gap-1.5"
        >
          <button
            type="button"
            aria-pressed={selected.length === 0}
            onClick={() => setPicked({ key: packageKeys, names: [] })}
            className={cn(
              'rounded-xl border bg-background px-3 py-2 text-base transition-colors duration-150',
              selected.length === 0
                ? 'border-foreground/40 bg-foreground/[0.05] font-medium text-foreground'
                : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
            )}
          >
            모두
          </button>
          {packages.map((p, i) => {
            const style = seriesStyle(i)
            const active = selected.includes(p.key)
            return (
              <button
                key={p.key}
                type="button"
                aria-pressed={active}
                onClick={() => togglePackage(p.key)}
                className={cn(
                  'flex items-center gap-1.5 rounded-xl border bg-background px-3 py-2 text-base transition-colors duration-150',
                  active
                    ? 'border-foreground/40 bg-foreground/[0.05] font-medium text-foreground'
                    : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
                )}
              >
                <svg width="16" height="8" aria-hidden className="shrink-0">
                  <line
                    x1="0"
                    y1="4"
                    x2="16"
                    y2="4"
                    stroke={style.color}
                    strokeWidth="2.4"
                    strokeDasharray={style.dash}
                    strokeLinecap="round"
                  />
                </svg>
                <span className="truncate font-mono">{dependentsSeries[i]?.label ?? p.key}</span>
                <span className="sr-only">{style.patternLabel}</span>
                {i === 0 && (
                  <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-base text-muted-foreground">
                    기준
                  </span>
                )}
              </button>
            )
          })}
        </div>
      )}

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
            series={windowedDependents}
            step={step}
            window={window}
            observedFrom={model.observedFrom.dependents}
            coverageNote="이 지표의 관측 시작"
            emphasisKeys={emphasisKeys}
            height={height}
            state={metricState.dependents}
            allowDelta
          />
          <MetricChart
            title="Downloads"
            unit="주간 · npm 공식 자료"
            series={windowedDownloads}
            step={step}
            window={window}
            observedFrom={model.observedFrom.downloads}
            coverageNote="이 지표의 관측 시작"
            emphasisKeys={emphasisKeys}
            height={height}
            state={metricState.downloads}
          />
        </div>

        {/*
          고른 것은 펼치고 나머지는 접는다. 아무것도 안 골랐으면 전부 펼친다 —
          그 상태는 "다 접었다" 가 아니라 "아직 좁히지 않았다" 이기 때문이다.
          접는 조작은 위 칩 줄에만 있다. 카드 자체를 눌러도 접히면 같은 상태를 두 곳에서
          바꾸게 되어 칩이 가리키는 것과 어긋난다.
        */}
        <div className="flex flex-col gap-4">
          {packages.map((p, i) => (
            <PackageCard
              key={p.key}
              model={p}
              index={i}
              expanded={selected.length === 0 || selected.includes(p.key)}
              selectedVersion={versionByName[p.key] ?? ALL_MAJORS}
              onVersionChange={(next) => selectVersion(p.key, next)}
              versionShareState={versionShareState}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
