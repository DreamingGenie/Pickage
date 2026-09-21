import { useMemo, useState } from 'react'

import { errorNotice } from '@/api/client'
import { TransitionBars, type TransitionBarsMode } from '@/components/charts/transition-bars'
import { seriesStyle } from '@/components/charts/tokens'
import { InfoDialog } from '@/components/common/info-dialog'
import { SegmentedControl } from '@/components/common/segmented-control'
import { Skeleton } from '@/components/ui/skeleton'
import type { MetricState } from '@/routes/report/ecosystem/model'
import { DEPENDENTS_TERM } from '@/routes/report/ecosystem/terms'
import {
  populationLabel,
  TRANSITION_KIND_INFO,
  TRANSITION_KINDS,
  TRANSITION_PERIODS,
  unobservedShare,
  type TransitionKind,
  type TransitionPeriod,
  type TransitionsModel,
} from '@/routes/report/ecosystem/transitions-model'
import { cn } from '@/lib/utils'

/**
 * 유지·유입·이탈 패널 (S15P21A506-391).
 *
 * 그리드(Dependents·Downloads·PackageCard) 아래 **전체 폭 섹션**으로 둔다 — 좌측
 * sticky 칼럼은 "칩 강조가 두 차트에 동시에 걸리는" 용도인데 이 패널은 자체 날짜축을
 * 가진 구조적으로 독립된 데이터라 그 관계에 안 낀다. 3패키지×4범주를 좁은 칼럼에
 * 욱여넣지 않기 위한 선택이기도 하다.
 *
 * 기간(`period`)은 **부모가 들고 있다** — `ecosystem-view.tsx`의 `window`/`intervalKey`와
 * 같은 이유(39행)의 반대쪽이다: 그건 서버 왕복이 없어 로컬에 두지만, 이건 프리셋을
 * 바꿀 때마다 새 요청이 나가므로 그 요청을 쏘는 층(`EcosystemReportTab`)이 정본이어야
 * 한다. `kind`는 서버 왕복이 없는 순수 재배치라 이 컴포넌트 로컬 상태로 둔다.
 */
export function TransitionsPanel({
  model,
  state,
  period,
  onPeriodChange,
  emphasisKeys,
  className,
}: {
  model: TransitionsModel
  state: MetricState
  period: TransitionPeriod
  onPeriodChange: (next: TransitionPeriod) => void
  /** 위 칩 줄이 고른 패키지 — 다른 차트·카드와 같은 강조를 이 패널에도 건다. */
  emphasisKeys: string[] | null
  className?: string
}) {
  const [kind, setKind] = useState<TransitionKind>('regular')
  /**
   * 값(전체 대비 막대) · 비율(활동 대비 도넛) — **패키지마다** 따로 고른다(S15P21A506-427
   * 후속 리뷰). 처음엔 패널 전역 토글로 만들었으나, 패키지별로 보고 싶은 표시 방식이 다를 수
   * 있다는 피드백을 받아 각 패키지 카드 머리글로 옮겼다. 없는 키는 기본값 `'value'`다.
   */
  const [modes, setModes] = useState<Record<string, TransitionBarsMode>>({})

  const rowsOf = (pkg: TransitionsModel['packages'][number]) =>
    pkg.rows.find((r) => r.kind === kind) ?? null

  /**
   * 비교 패키지 전체에서 공유하는 스케일. 개별 컴포넌트가 각자 최댓값을 잡으면
   * 패키지끼리 막대 길이로 비교할 수 없다 — Dependents·Downloads 차트가 이미 비교
   * 패키지 간 공유 축을 쓰는 것과 같은 이유다. `OUT_OF_SCOPE`·`NOT_COMPUTED`는
   * 고정 placeholder 폭이라 스케일 계산에서 뺀다.
   */
  const max = useMemo(() => {
    let m = 0
    for (const pkg of model.packages) {
      const row = rowsOf(pkg)
      if (!row?.counts) continue
      m = Math.max(
        m,
        row.counts.retained,
        row.counts.inflowAdopted,
        row.counts.outflow,
        row.counts.unobserved,
      )
    }
    return m
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model.packages, kind])

  /**
   * 1년 경고에 쓸 실측값. 지금 고른 `kind`의 행만 합친다 — 종류를 바꾸면 비율도 달라진다.
   * 문장에 상수를 박아 두지 않는 이유는 `unobservedShare` 주석에 있다.
   */
  const unobservedPct = useMemo(
    () => unobservedShare(model.packages.flatMap((pkg) => pkg.rows.filter((r) => r.kind === kind))),
    [model.packages, kind],
  )

  const dateLabel =
    model.t1 && model.t2
      ? `${model.t1} ~ ${model.t2}`
      : '적재 전 — 아직 이 구간이 계산되지 않았습니다'

  return (
    <div
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 text-left',
        state.status === 'error' && 'items-start',
        className,
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <h3 className="text-lg font-semibold">유지 · 유입 · 이탈</h3>
          {/*
            제목 밑에 상시 노출하던 두 문장을 여기로 옮겼다(S15P21A506-405). 하나는 이 수치가 위
            그래프의 증감과 왜 다른지, 하나는 무엇을 세지 않는지 — 둘 다 이 패널의 **계산 기준**이라
            한 모달에 둔다.
          */}
          <InfoDialog label="유지·유입·이탈 계산 기준 안내" title="계산 기준">
            <p>
              {DEPENDENTS_TERM} 그래프의 증감과는 다른 기준입니다. 그쪽은 버전별 합계이고, 이 수치는{' '}
              {model.population ? populationLabel(model.population) : '집계 대상'} 중 프로젝트를
              이름으로 센 결과라 계산 방식 자체가 다릅니다.
            </p>
            <p>devDependencies는 포함하지 않습니다.</p>
            {/*
              S15P21A506-427. 막대 라벨은 "릴리스 없음"이라는 사실만 짧게 말한다 — 왜 그것이
              "모른다"와 다른지는 여기서 밝힌다. 1년 구간에서 화면의 대부분을 먹는 칸이라
              이 설명이 없으면 우리가 자료를 못 구한 것처럼 읽힌다.
            */}
            <p>
              <strong>릴리스 없음</strong>은 자료를 구하지 못했다는 뜻이 아닙니다. 그 프로젝트는
              기간의 양 끝에서 이 패키지를 그대로 선언하고 있습니다. 다만 그 사이에 릴리스를 내지
              않아, 계속 쓸지 다시 검토했는지를 판단하지 않았습니다. npm 패키지의 76.1%가 최근 1년간
              릴리스가 없습니다.
            </p>
            <p>
              기간을 넓히면 <strong>릴리스 없음</strong>의 비율은 떨어지지만 실제로 판정하는 수는
              늘지 않습니다 — 구간이 길수록 신생 패키지가 유입으로 옮겨가 분모가 부풀기 때문입니다.
              판정 수가 가장 많은 것은 5년이 아니라 <strong>3년</strong>입니다.
            </p>
          </InfoDialog>
        </div>
        <span className="font-mono text-base text-muted-foreground">{dateLabel}</span>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <SegmentedControl
          label="조회 기간"
          value={period}
          onChange={(k) => onPeriodChange(k as TransitionPeriod)}
          options={TRANSITION_PERIODS.map((p) => ({ key: p.key, label: p.label }))}
        />
        <div className="flex items-center gap-1.5">
          <SegmentedControl
            label="의존 종류"
            value={kind}
            onChange={(k) => setKind(k as TransitionKind)}
            options={TRANSITION_KINDS.map((k) => ({ key: k.key, label: k.label }))}
          />
          <InfoDialog label="의존 종류 안내" title="의존 종류">
            <dl className="flex flex-col gap-3">
              {TRANSITION_KIND_INFO.map((info) => (
                <div key={info.key}>
                  <dt className="text-base font-medium">{info.label}</dt>
                  <dd className="text-base leading-relaxed text-muted-foreground">
                    {info.description}
                  </dd>
                </div>
              ))}
            </dl>
          </InfoDialog>
        </div>
      </div>

      {state.status === 'loading' ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : state.status === 'error' ? (
        <TransitionsError error={state.error} onRetry={state.onRetry} />
      ) : (
        <>
          {model.notFound.length > 0 && (
            <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              일부 패키지의 전환 데이터를 찾지 못했습니다:{' '}
              <span className="font-mono text-foreground">{model.notFound.join(', ')}</span>
            </p>
          )}

          {period === '1y' && unobservedPct !== null && (
            <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              1년은 판정할 수 있는 의존자가 가장 적은 구간입니다 — 지금 비교에서{' '}
              <strong className="font-medium text-foreground">
                {unobservedPct.toFixed(1)}%가 릴리스 없음
              </strong>
              입니다. 기본값인 3년이 실제로 판정하는 수가 가장 많습니다.
            </p>
          )}

          {/*
            `justify-center` + 고정 폭 — 3패키지면 기존 grid-cols-3 처럼 한 줄을 꽉 채우지만,
            1~2개면 그리드가 비운 칸만큼 오른쪽에 통째로 남던 공백을 양옆으로 고르게 돌린다
            (리뷰 지적: 패키지 1~2개 비교에서 균형이 안 맞아 보였다).
          */}
          <div className="flex flex-wrap justify-center gap-5">
            {model.packages.map((pkg, i) => {
              const row = rowsOf(pkg)
              const style = seriesStyle(i)
              const emphasized = !emphasisKeys || emphasisKeys.includes(pkg.key)
              const mode = modes[pkg.key] ?? 'value'
              return (
                <div
                  key={pkg.key}
                  className={cn(
                    'flex w-full flex-none flex-col gap-3 transition-opacity duration-150',
                    'sm:basis-[calc(50%-10px)] lg:basis-[calc(33.333%-14px)]',
                    !emphasized && 'opacity-40',
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-1.5">
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
                      <span className="truncate font-mono text-base font-medium">{pkg.key}</span>
                    </div>
                    {/* 값(막대)·비율(도넛) — 이 패키지만 바꾼다. */}
                    <SegmentedControl
                      label={`${pkg.key} 표시 방식`}
                      value={mode}
                      onChange={(k) =>
                        setModes((prev) => ({ ...prev, [pkg.key]: k as TransitionBarsMode }))
                      }
                      options={[
                        { key: 'value', label: '값' },
                        { key: 'ratio', label: '비율' },
                      ]}
                    />
                  </div>
                  {row ? (
                    <TransitionBars
                      counts={row.counts}
                      dataStatus={row.dataStatus}
                      max={max}
                      mode={mode}
                    />
                  ) : (
                    <p className="text-base text-muted-foreground">자료 없음</p>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function TransitionsError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
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
