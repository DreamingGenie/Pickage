import type { DependencyKindParam } from '@/api/types'
import { errorNotice } from '@/api/client'
import { MigrationFlowBar } from '@/components/charts/migration-flow'
import { seriesStyle } from '@/components/charts/tokens'
import { InfoDialog } from '@/components/common/info-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import type { MetricState } from '@/routes/report/ecosystem/model'
import {
  crossDirections,
  DEPENDENCY_KINDS,
  EVIDENCE_LABEL,
  type MigrationModel,
} from '@/routes/report/ecosystem/migration-model'
import { cn } from '@/lib/utils'

/**
 * 관측된 교체 흐름 패널 (S15P21A506-424).
 *
 * 위 두 패널이 "얼마나 떠났나"(유지·유입·이탈)와 "대체를 동반했나"(이탈 사유)까지 말한다.
 * 이 패널만 <b>"어디로 갔나"</b> 에 이름으로 답한다 — 이탈 사유의 `with_replacement` 는
 * 수일 뿐 도착지 이름이 없다.
 *
 * <h2>선택기가 구간이 아니라 **의존 종류**다</h2>
 *
 * 위 두 패널의 선택기와 생김새가 같아 기간으로 오해하기 쉬워 라벨에 "의존 종류" 를 적는다.
 * 이 지표에는 구간이라는 축이 없다 — 연속한 릴리스를 전부 훑은 결과라 "몇 년치" 가
 * 성립하지 않는다. 대신 고르면 <b>기준일이 함께 바뀐다</b>(실행용 2026-08-31 ·
 * 개발용 2026-09-16, 16일 차이).
 *
 * <h2>두 종류의 수를 나란히 놓지 않는다</h2>
 *
 * 모집단이 다르다(전이 3,958만 vs 726만). 한 화면에 겹쳐 그리면 비교할 수 없는 수가
 * 비교되므로, 선택기로 <b>하나씩만</b> 보여 준다.
 *
 * <h2>원인으로 단정하지 않는다</h2>
 *
 * 관측된 흐름이지 "그래서 옮겨야 한다" 가 아니다. 문구를 전부 관측형으로 쓰고, 같은
 * 물건의 다른 포장(변종)은 지우지 않고 표시만 다르게 한다(S15P21A506-211 결정 4 ③).
 */
export function MigrationPanel({
  model,
  state,
  kind,
  onKindChange,
  emphasisKeys,
  className,
}: {
  model: MigrationModel
  state: MetricState
  kind: DependencyKindParam
  onKindChange: (next: DependencyKindParam) => void
  emphasisKeys: string[] | null
  className?: string
}) {
  /**
   * 기준일은 <b>행에서 읽는다.</b> 서버가 종류로 계산하지 않고 표가 가진 값을 주므로,
   * 화면도 상수로 적지 않는다 — 원천을 다시 뽑으면 날짜가 바뀐다.
   */
  const snapshot = model.packages.find((p) => p.snapshotAt)?.snapshotAt ?? null
  const directions = crossDirections(model)
  const shareBasis = model.packages[0]?.shareBasis ?? 'publisher_months'

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
          <h3 className="text-lg font-semibold">어디로 옮겨 갔나</h3>
          <InfoDialog label="교체 흐름 계산 기준 안내" title="계산 기준">
            <p>
              어떤 패키지를 <strong>빼면서 같은 버전에 새로 넣은 것</strong>을 모아 도착지별로 센
              거예요. 바로 위 <strong>이탈 사유</strong> 의 &ldquo;다른 것과 함께 제거&rdquo; 에
              이름을 붙인 것이라고 보면 돼요.
            </p>
            <p>
              <strong>옮기라는 추천이 아니에요.</strong> 사람들이 실제로 그렇게 했다는 기록일
              뿐이고, 왜 그랬는지는 이 자료로 알 수 없어요.
            </p>
            <p>
              비율의 분모는 <strong>바꾼 횟수가 아니라 서로 다른 (만든 사람 × 달)</strong> 의
              수예요({shareBasis}). 한 회사가 자기 패키지 수십 개를 한 달에 한꺼번에 바꿔도 1로
              세요.
            </p>
            <p>
              <strong>막대가 100%를 다 채우지 않아요.</strong> 근거가 약한 이동(같은 달, 같은 만든
              사람에서 한 번만 보인 것)은 집계에서 뺐거든요. 남는 자리는 빗금으로 그려 두고 비율을
              100으로 늘리지 않아요 — 늘리면 각 도착지가 실제보다 훨씬 커 보여요.
            </p>
            <p>
              <strong>실행용과 개발용은 따로 봐야 해요.</strong> 센 대상이 아예 달라서(npm 전체 vs
              다운로드 상위 10만) 두 수를 더하거나 크기를 비교할 수 없어요. 고른 쪽에 따라 기준일도
              달라져요.
            </p>
          </InfoDialog>
        </div>
        <span className="font-mono text-base text-muted-foreground">
          {snapshot ?? '준비 중 — 이 기준은 아직 적재하지 않았어요'}
        </span>
      </div>

      {/* 구간 선택기가 아니라는 것을 라벨로 못박는다. 생김새만 보면 착각하기 쉽다. */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-base text-muted-foreground">의존 종류</span>
        <div className="flex gap-1 rounded-lg border p-1">
          {DEPENDENCY_KINDS.map((k) => (
            <button
              key={k.key}
              type="button"
              onClick={() => onKindChange(k.key)}
              aria-pressed={kind === k.key}
              title={k.hint}
              className={cn(
                'rounded-md px-3 py-1 text-base transition-colors',
                kind === k.key
                  ? 'bg-foreground text-background'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {k.label}
            </button>
          ))}
        </div>
        <span className="text-base text-muted-foreground">
          {DEPENDENCY_KINDS.find((k) => k.key === kind)?.hint}
        </span>
      </div>

      {state.status === 'loading' ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : state.status === 'error' ? (
        <PanelError error={state.error} onRetry={state.onRetry} />
      ) : (
        <>
          {model.notFound.length > 0 && (
            <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
              일부 패키지는 교체 흐름을 찾지 못했어요:{' '}
              <span className="font-mono text-foreground">{model.notFound.join(', ')}</span>
            </p>
          )}

          {directions.length > 0 && <CrossDirections directions={directions} />}

          <div className="flex flex-wrap justify-center gap-5">
            {model.packages.map((pkg, i) => {
              const style = seriesStyle(i)
              const emphasized = !emphasisKeys || emphasisKeys.includes(pkg.key)
              return (
                <div
                  key={pkg.key}
                  className={cn(
                    'flex w-full flex-none flex-col items-center gap-3 transition-opacity duration-150',
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
                    <span className="text-base text-muted-foreground">에서</span>
                  </div>
                  <MigrationFlowBar pkg={pkg} />
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

/**
 * 비교 중인 패키지끼리의 이동 — 기획의 "최대 6개 방향"(S15P21A506-136).
 *
 * 아래 패키지별 막대에도 같은 값이 들어 있지만, 거기서는 <b>어느 도착지가 지금 비교 중인
 * 다른 패키지인지</b>를 이름으로 대조해야 알 수 있다. 사용자가 실제로 궁금해하는 것이
 * 그 대조에 묻히므로 따로 뽑아 맨 위에 둔다.
 *
 * 관측된 방향만 나온다 — 0 인 방향은 줄을 만들지 않는다. "이동이 없었다" 와 "관측 범위
 * 밖이라 모른다" 를 한 줄로 뭉개지 않기 위해서다.
 */
function CrossDirections({ directions }: { directions: ReturnType<typeof crossDirections> }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-dashed p-4">
      <p className="text-base text-muted-foreground">비교 중인 패키지끼리 오간 이동</p>
      <ul className="flex flex-col gap-1.5">
        {directions.map((d) => (
          <li key={`${d.from}->${d.to}`} className="flex items-center gap-2">
            <span className="truncate font-mono text-base text-foreground">{d.from}</span>
            <span aria-label="에서" className="shrink-0 text-muted-foreground">
              →
            </span>
            <span className="truncate font-mono text-base text-foreground">{d.to}</span>
            {d.variant && (
              <span
                className="shrink-0 rounded border px-1 text-xs text-muted-foreground"
                title="양방향으로 관측됐어요. 같은 물건의 다른 포장일 수 있어요"
              >
                변종
              </span>
            )}
            <span className="shrink-0 text-xs text-muted-foreground">
              {EVIDENCE_LABEL[d.evidence]}
            </span>
            <span className="ml-auto shrink-0 font-mono text-base tabular-nums">
              {d.sharePmPct.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function PanelError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
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
