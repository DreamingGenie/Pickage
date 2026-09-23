import { useMemo, useState } from 'react'

import { errorNotice } from '@/api/client'
import { TransitionBars } from '@/components/charts/transition-bars'
import { seriesStyle } from '@/components/charts/tokens'
import { InfoDialog } from '@/components/common/info-dialog'
import { SegmentedControl } from '@/components/common/segmented-control'
import { Skeleton } from '@/components/ui/skeleton'
import type { MetricState } from '@/routes/report/ecosystem/model'
import { DEPENDENTS_TERM } from '@/routes/report/ecosystem/terms'
import {
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
      : '준비 중 — 이 기간은 아직 계산하지 않았어요'

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
          {/*
            **세 문단만 남긴다** (S15P21A506-468). 열 문단짜리였는데 읽히지 않는다는 지적을
            받았다. 다만 통째로 빼지는 않았다 — 아래 둘은 없으면 화면이 거짓으로 읽힌다.

              · "릴리스 없음" 이 자료 없음으로 읽히는 것 (그 칸이 npm 의 76.1%다)
              · 기간을 넓히면 나아질 것처럼 보이는 것 (3년이 가장 많다)

            분해(3년 안 · 3~5년 전 · 5년 초과) 설명은 뺐다. 값 모드와 함께 화면에서 사라져
            설명할 대상이 없다.
          */}
          <InfoDialog label="유지·유입·이탈 계산 기준 안내" title="계산 기준">
            <p>
              {DEPENDENTS_TERM} 그래프와 세는 방법이 달라요. 그쪽은 버전마다 센 값을 더한 것이고,
              이쪽은 프로젝트를 이름으로 하나씩 센 거예요. 개발할 때만 쓰는 의존(devDependencies)은
              세지 않아요.
            </p>
            <p>
              <strong>판정하지 못한 프로젝트가 많아요.</strong> 기간의 처음과 끝 모두 이 패키지를
              적어 두었지만 그 사이에 새 버전을 내지 않았다면, 계속 쓸지 다시 생각했는지 알 수
              없어요. npm 패키지의 76.1%가 최근 1년 동안 새 버전을 내지 않았어요.{' '}
              <strong>자료를 못 구한 것이 아니에요.</strong>
            </p>
            <p>
              기간을 넓혀도 판정할 수 있는 수는 늘지 않아요 — 기간이 길수록 새로 생긴 패키지가 많이
              섞이기 때문이에요. 가장 많은 기간은 5년이 아니라 <strong>3년</strong>이에요.
            </p>
          </InfoDialog>
        </div>
        <span className="font-mono text-base text-muted-foreground">{dateLabel}</span>
      </div>

      {/*
        3칸 그리드 — 양 끝에 "조회 기간"·"의존 종류" 를 밀어 두는 배치다. 가운데 칸은
        값/비율 토글이 있던 자리로, 지금은 비어 있지만 그리드를 2칸으로 줄이지 않는다.
        양 끝 정렬이 위 패널들과 같아야 줄이 맞는다.
      */}
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="justify-self-start">
          <SegmentedControl
            label="조회 기간"
            value={period}
            onChange={(k) => onPeriodChange(k as TransitionPeriod)}
            options={TRANSITION_PERIODS.map((p) => ({ key: p.key, label: p.label }))}
          />
        </div>
        {/*
          **값/비율 토글을 없앴다** (S15P21A506-468). 두 모드의 분모가 달라서
          (값=전체 대비 · 비율=판정한 것만) 고르는 것이 아니라 헷갈리는 자리였다.
          비율만 남기되 분모를 도넛 옆에 글자로 남긴다 — "의존자 N 중 M 판정".
          그 줄이 없으면 1년 구간 유지율이 87.2% 가 아니라 98.8% 로 보인다.
        */}
        <span aria-hidden />
        <div className="flex items-center gap-1.5 justify-self-end">
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
              일부 패키지는 이 자료를 찾지 못했어요:{' '}
              <span className="font-mono text-foreground">{model.notFound.join(', ')}</span>
            </p>
          )}

          {period === '1y' && unobservedPct !== null && (
            <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              1년은 판단할 수 있는 프로젝트가 가장 적은 기간이에요 — 지금 비교에서{' '}
              <strong className="font-medium text-foreground">
                {unobservedPct.toFixed(1)}%가 릴리스 없음
              </strong>
              예요. 처음 골라져 있는 3년이 판단할 수 있는 수가 가장 많아요.
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
              return (
                <div
                  key={pkg.key}
                  className={cn(
                    'flex w-full flex-none flex-col gap-3 transition-opacity duration-150',
                    'sm:basis-[calc(50%-10px)] lg:basis-[calc(33.333%-14px)]',
                    !emphasized && 'opacity-40',
                  )}
                >
                  <div className="flex items-center gap-1.5">
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
                  {row ? (
                    <TransitionBars counts={row.counts} dataStatus={row.dataStatus} max={max} />
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
