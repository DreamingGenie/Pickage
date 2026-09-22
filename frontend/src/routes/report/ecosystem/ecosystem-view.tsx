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
  DEFAULT_PERIOD_PRESET,
  stepOf,
  type EcosystemModel,
  type MajorSelection,
  type MetricKey,
  type MetricState,
  type PeriodPresetKey,
} from '@/routes/report/ecosystem/model'
import {
  DEPENDENTS_CAPTION,
  DEPENDENTS_TERM,
  DependentsConcept,
} from '@/routes/report/ecosystem/terms'
import { RemovalReasonsPanel } from '@/routes/report/ecosystem/removal-reasons-panel'
import {
  EMPTY_REMOVAL_REASONS_MODEL,
  type RemovalReasonsModel,
} from '@/routes/report/ecosystem/removal-reasons-model'
import { TransitionsPanel } from '@/routes/report/ecosystem/transitions-panel'
import {
  DEFAULT_TRANSITION_PERIOD,
  EMPTY_TRANSITIONS_MODEL,
  type TransitionPeriod,
  type TransitionsModel,
} from '@/routes/report/ecosystem/transitions-model'
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
/** 서버 왕복이 없는 no-op — 인트로 미리보기처럼 조작이 필요 없는 자리의 기본값. */
const NOOP_PERIOD_CHANGE = () => {}

export function EcosystemView({
  model,
  metricState = READY,
  versionShareState = READY_STATE,
  transitionsModel = EMPTY_TRANSITIONS_MODEL,
  transitionsState = READY_STATE,
  removalReasonsModel = EMPTY_REMOVAL_REASONS_MODEL,
  removalReasonsState = READY_STATE,
  transitionPeriod = DEFAULT_TRANSITION_PERIOD,
  onTransitionPeriodChange = NOOP_PERIOD_CHANGE,
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
  /** 유지·유입·이탈 조회 결과(S15P21A506-391). 개요·추이와 독립된 다섯 번째 쿼리다. */
  transitionsModel?: TransitionsModel
  transitionsState?: MetricState
  /** 이탈 사유(S15P21A506-410). 위와 같은 `period` 를 쓰되 **단위가 다르다**(전이 건수). */
  removalReasonsModel?: RemovalReasonsModel
  removalReasonsState?: MetricState
  /**
   * 값 자체의 정본은 `ReportPage`다(S15P21A506-394) — PDF 내보내기 다이얼로그가 "화면이
   * 지금 보는 기간"을 읽어야 해서 이 탭보다 위로 올렸다. 다만 그 값이 바뀔 때 서버
   * 왕복이 있는 새 요청을 쏘는 자리는 여전히 `EcosystemReportTab`이다(39행 규칙의 반대쪽).
   */
  transitionPeriod?: TransitionPeriod
  onTransitionPeriodChange?: (next: TransitionPeriod) => void
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
  const [local, setLocal] = useState<{
    key: string
    window: EcosystemControls['window']
    presetKey: PeriodPresetKey | null
  }>(() => ({
    key: `${bounds.start}~${bounds.end}`,
    window: bounds,
    // 처음에는 받아 둔 전 구간을 그대로 보여 주므로 "전체 기간" 이 눌려 있다(S15P21A506-405).
    presetKey: DEFAULT_PERIOD_PRESET,
  }))
  const [intervalKey, setIntervalKey] = useState('1w')

  const boundsKey = `${bounds.start}~${bounds.end}`
  const window = local.key === boundsKey ? local.window : bounds
  const presetKey = local.key === boundsKey ? local.presetKey : DEFAULT_PERIOD_PRESET

  const controls: EcosystemControls = { window, presetKey, intervalKey }

  function onControlsChange(next: EcosystemControls) {
    setIntervalKey(next.intervalKey)
    setLocal({ key: boundsKey, window: next.window, presetKey: next.presetKey })
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
   * 상세를 보는 패키지. **한 번에 하나만 고른다.**
   *
   * 여러 개를 고르게 해 봤지만, 고른 수만큼 카드가 쌓여 오른쪽 열이 차트보다 길어지고
   * "지금 무엇을 보는 중인가" 가 흐려졌다. 탭은 하나를 고르는 물건이라는 감각이 더 강하다.
   *
   * **"아무도 고르지 않은" 상태가 기본이다.** 처음부터 하나가 강조돼 있으면 나머지가
   * 흐려진 채로 화면이 열려 공정한 비교가 안 된다. 그때 차트는 전부 같은 굵기로 그리고,
   * 카드는 기준 패키지를 보여 준다 — 오른쪽 열이 통째로 비는 것보다 낫고, 기준은 사용자가
   * 고른 것이 아니라 비교의 출발점이라 "골랐다" 고 말하지 않는다(그래서 그 칩은 눌린
   * 것처럼 보이지 않는다).
   *
   * 비교 조합이 바뀌면 선택을 되돌린다. 없어진 패키지의 key 가 남아 있으면 강조가
   * 아무 선에도 걸리지 않아 전부 흐려진 화면이 된다.
   */
  const packageKeys = model.packages.map((p) => p.key).join(',')
  const [picked, setPicked] = useState<{ key: string; name: string | null }>({
    key: packageKeys,
    name: null,
  })
  const selected = picked.key === packageKeys ? picked.name : null
  const emphasisKeys = selected ? [selected] : null

  /** 고른 것이 없으면 기준 패키지. 강조와 달리 카드는 항상 하나가 떠 있어야 한다. */
  const shownIndex = Math.max(
    0,
    packages.findIndex((p) => p.key === selected),
  )
  const shown = packages[shownIndex]

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
          <span className="font-mono text-foreground">{model.notFound.join(', ')}</span> 는 찾지
          못했어요. 이름을 확인해 주세요.
          {model.packages.length > 0 && ' 나머지 패키지는 그대로 보여 드려요.'}
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
        active 여야 해서 "아무것도 고르지 않은" 상태를 표현할 수 없다.

        맨 앞 `모두` 는 선택을 비우는 자리다. 누른 칩을 다시 누르는 것으로도 풀린다.
      */}
      {model.packages.length > 0 && (
        <div
          role="group"
          aria-label="강조할 패키지 선택"
          className="flex flex-wrap items-center gap-1.5"
        >
          <button
            type="button"
            aria-pressed={selected === null}
            onClick={() => setPicked({ key: packageKeys, name: null })}
            className={cn(
              'rounded-xl border bg-background px-3 py-2 text-base transition-colors duration-150',
              selected === null
                ? 'border-foreground/40 bg-foreground/[0.05] font-medium text-foreground'
                : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
            )}
          >
            모두
          </button>
          {packages.map((p, i) => {
            const style = seriesStyle(i)
            const active = selected === p.key
            return (
              <button
                key={p.key}
                type="button"
                aria-pressed={active}
                onClick={() => setPicked({ key: packageKeys, name: active ? null : p.key })}
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

        **두 열의 높이는 언제나 같다**(S15P21A506-405). 짧은 쪽이 늘어나 긴 쪽에 맞춘다 — 아래에
        이유 없는 빈 공간이 생기지 않는다.
        · 왼쪽이 길면 오른쪽 카드가 늘어나고 안의 요소는 세로 중앙에 놓인다(`PackageCard`).
        · 오른쪽이 길면 왼쪽 열이 늘어나고, 그래프 카드 둘이 그 높이를 **똑같이 나눠** 갖는다
          (`flex-1`). 그래프는 늘어난 만큼 함께 커진다(`MetricChart` 의 `fill`).
        예전에는 왼쪽 열을 `sticky` 로 붙여 카드가 길어져도 그래프가 화면에 남게 했는데, 그 구조는
        열 높이를 맞추는 것과 양립하지 않아 뺐다.

        좁은 화면에서는 한 줄로 무너진다. 그때는 차트가 먼저 오고 카드가 아래로 간다.
      */}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(380px,1fr)]">
        <div className="flex min-w-0 flex-col gap-5">
          <MetricChart
            title={DEPENDENTS_TERM}
            info={<DependentsConcept />}
            infoTitle={`${DEPENDENTS_TERM}란?`}
            unit={DEPENDENTS_CAPTION}
            series={windowedDependents}
            step={step}
            window={window}
            observedFrom={model.observedFrom.dependents}
            emphasisKeys={emphasisKeys}
            height={height}
            fill
            className="lg:flex-1"
            state={metricState.dependents}
          />
          <MetricChart
            title="Downloads"
            unit="1주 동안 내려받은 횟수예요 · npm 공식 자료"
            series={windowedDownloads}
            step={step}
            window={window}
            observedFrom={model.observedFrom.downloads}
            emphasisKeys={emphasisKeys}
            height={height}
            fill
            className="lg:flex-1"
            state={metricState.downloads}
            /*
              Downloads 는 실제값 하나로 고정한다. 이미 주간 흐름값이라 "구간 시작 대비
              몇 %" 가 누적 총합만큼 와닿지 않고, 주간 값은 그 자체로 오르내려서 기준으로
              잡은 첫 주가 어쩌다 높거나 낮으면 이후 전 구간이 그만큼 통째로 밀린다.
              누적인 Dependents 에는 그 흔들림이 없다.
            */
            allowIndex={false}
          />
        </div>

        {/*
          카드는 위 칩이 가리키는 하나뿐이다. 고른 것이 없으면 기준 패키지를 보여 준다 —
          차트는 그때 전부 같은 굵기로 그려도, 오른쪽 열까지 비워 두면 화면의 절반이
          이유 없이 빈다.

          `key` 에 패키지 이름을 준다. 탭을 바꿀 때 React 가 같은 노드를 재사용하면
          펼침 애니메이션도, 안쪽 스크롤 위치도 이전 패키지 것을 물고 온다.
        */}
        {shown && (
          <PackageCard
            key={shown.key}
            model={shown}
            index={shownIndex}
            selectedVersion={versionByName[shown.key] ?? ALL_MAJORS}
            onVersionChange={(next) => selectVersion(shown.key, next)}
            versionShareState={versionShareState}
          />
        )}
      </div>

      {/*
        그리드 아래 전체 폭 섹션이다. 위 두 칼럼과 달리 이 패널은 자체 날짜축을 가진
        구조적으로 독립된 데이터라 sticky 칼럼의 "칩 강조가 두 차트에 동시에 걸리는"
        관계에 안 낀다 — 강조(`emphasisKeys`)만 그대로 물려받아 패키지 식별은 일관되게 유지한다.

        **자기 모델을 보고 판단한다** (S15P21A506-410). `model.packages` 를 보면 인트로
        미리보기처럼 이 모델을 안 넘기는 자리에서도 빈 패널이 떴다(service-intro-page.tsx).
        아래 이탈 사유 패널과 같은 조건이다 — 로딩·오류는 그대로 보여 준다.
      */}
      {(transitionsModel.packages.length > 0 || transitionsState.status !== 'ready') && (
        <TransitionsPanel
          model={transitionsModel}
          state={transitionsState}
          period={transitionPeriod}
          onPeriodChange={onTransitionPeriodChange}
          emphasisKeys={emphasisKeys}
        />
      )}

      {/*
        유지·유입·이탈 **바로 아래**에 둔다. 저 패널이 "떠났다" 까지만 말하고 이 패널이
        그 이탈을 둘로 가르므로, 떨어뜨려 놓으면 둘의 관계가 안 보인다. 구간 선택기는
        위 패널 것 하나를 공유한다 — 같은 값을 바꾸는 컨트롤이 둘이면 고장처럼 보인다.
      */}
      {/*
        **자기 모델을 보고 판단한다.** `model.packages` 를 보면 인트로 미리보기처럼
        이탈 사유 모델을 안 넘기는 자리에서도 빈 패널이 뜬다(service-intro-page.tsx).
        로딩·오류는 그대로 보여 줘야 하므로 상태도 함께 본다.
      */}
      {(removalReasonsModel.packages.length > 0 || removalReasonsState.status !== 'ready') && (
        <RemovalReasonsPanel
          model={removalReasonsModel}
          state={removalReasonsState}
          period={transitionPeriod}
          emphasisKeys={emphasisKeys}
        />
      )}
    </div>
  )
}
