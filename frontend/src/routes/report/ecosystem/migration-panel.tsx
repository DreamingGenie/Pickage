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
  EVIDENCE_RULE,
  observationHint,
  VARIANT_HINT,
  VARIANT_LABEL,
  VARIANT_RULE,
  type MigrationEvidence,
  type MigrationModel,
} from '@/routes/report/ecosystem/migration-model'
import { EvidenceBadge, VariantBadge } from '@/routes/report/ecosystem/migration-badges'
import { MIGRATION_CAPTION, MIGRATION_TERM } from '@/routes/report/ecosystem/terms'
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

  return (
    <div
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 text-left',
        state.status === 'error' && 'items-start',
        className,
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5">
            <h3 className="text-lg font-semibold">{MIGRATION_TERM}</h3>
            {/*
              **배지 풀이를 맨 위에 둔다.** 이 모달을 여는 가장 잦은 이유가 "근거 강함이
              무슨 뜻이지" 라서다. 나머지 두 줄은 그 아래 주의사항이다.

              실행용·개발용 차이는 여기 적지 않는다 — 선택기 옆에 늘 떠 있다. 화면에 이미
              있는 말을 모달이 되풀이하면 읽을 것이 두 배로 보인다.
            */}
            <InfoDialog
              label="교체 흐름 계산 기준 안내"
              title="계산 기준"
              /* 표가 들어가서 기본 폭(sm)에서는 한 줄이 두세 단어마다 끊긴다. */
              contentClassName="sm:max-w-lg"
            >
              <EvidenceKey />
              <p>
                <strong>옮기라는 추천이 아니에요.</strong> 실제로 그렇게 했다는 기록이에요.
              </p>
              <p>
                <strong>막대가 100%를 다 채우지 않아요.</strong> 근거가 약한 이동은 뺐고, 남는
                자리가 빗금이에요.
              </p>
            </InfoDialog>
          </div>
          <p className="text-base text-muted-foreground">{MIGRATION_CAPTION}</p>
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

          {/*
            **열은 그리드가 나눈다.** 고정 폭(`sm:w-72`)으로 두었더니 위 패널(이탈 사유)은
            세 칸인데 이쪽만 2+1 로 접히는 폭 구간이 생겼다 — 같은 화면에서 두 패널의
            리듬이 어긋난다. 비율로 나누면 그 구간이 없어지고, 칸 수와 간격을 손으로 빼는
            매직 넘버도 필요 없다(그리드가 계산한다).

            칸 수를 패키지 수로 묶는 것은 **1~2개일 때 오른쪽에 빈 칸을 남기지 않기**
            위해서다. 셋을 전제로 `lg:grid-cols-3` 를 고정하면 하나만 비교할 때 왼쪽으로
            쏠린다.
          */}
          <div
            className={cn(
              'grid gap-5',
              model.packages.length >= 2 && 'sm:grid-cols-2',
              model.packages.length >= 3 && 'lg:grid-cols-3',
            )}
          >
            {model.packages.map((pkg, i) => {
              const style = seriesStyle(i)
              const emphasized = !emphasisKeys || emphasisKeys.includes(pkg.key)
              return (
                <div
                  key={pkg.key}
                  className={cn(
                    'flex min-w-0 flex-col items-center gap-3 transition-opacity duration-150',
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
 * 배지 넷의 <b>판정 문턱</b>. 모달에서 가장 자주 찾는 부분이라 문단이 아니라 표로 둔다.
 *
 * <h2>용어를 따로 정의하지 않는다</h2>
 *
 * 한때 "널리 · 자주" 로 줄이고 표 위에서 그 두 낱말을 정의했는데,
 * <b>용어집을 먼저 읽어야 이해되는 설명은 설명이 아니다.</b> 반복이 생기더라도
 * 단위를 문구 안에 넣어 한 줄이 혼자 읽히게 한다({@link EVIDENCE_RULE}).
 *
 * 각 배지의 "뜻" 은 여기 없다. 말풍선이 <b>그 행의 실제 수</b>로 말하기 때문이다 —
 * 등급마다 같은 문장을 되풀이하면 표가 길어지기만 하고 새로 알려 주는 것이 없다.
 */
function EvidenceKey() {
  const rows = [
    ...(['strict', 'recommended', 'loose'] as MigrationEvidence[]).map((key) => ({
      label: EVIDENCE_LABEL[key],
      rule: EVIDENCE_RULE[key],
    })),
    { label: VARIANT_LABEL, rule: `${VARIANT_HINT} — ${VARIANT_RULE}` },
  ]

  return (
    <div className="flex flex-col gap-3">
      <dl className="flex flex-col gap-2.5">
        {rows.map((row) => (
          <div key={row.label} className="flex flex-col gap-0.5">
            <dt className="font-medium text-foreground">{row.label}</dt>
            <dd className="text-sm">{row.rule}</dd>
          </div>
        ))}
      </dl>
      {/*
        남기는 단서는 하나뿐이다. 용어를 정의하는 것이 아니라, 그 수를 **오해하지 않게**
        하는 말이다 — (만든 사람 × 달) 을 "사람 수" 로 읽으면 뜻이 달라진다.
      */}
      <p className="text-sm text-muted-foreground/80">
        (만든 사람 × 달) 은 같은 사람이 한 달에 여럿을 바꿔도 <strong>1</strong>로 세요. 한 회사의
        일괄 변경이 수를 부풀리지 않게 하려는 거예요.
      </p>
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
      {/*
        **한 방향이 한 덩어리로 묶여 줄바꿈된다.** 예전에는 한 줄을 가로로 꽉 채우고 비율만
        `ml-auto` 로 오른쪽 끝에 붙였는데, 넓은 화면에서 이름과 비율이 손가락 두 뼘쯤 떨어져
        어느 줄의 값인지 눈으로 되짚어야 했다. 비율은 이름 바로 옆에 있어야 읽힌다.
      */}
      <ul className="flex flex-wrap gap-x-6 gap-y-2">
        {directions.map((d) => (
          <li key={`${d.from}->${d.to}`} className="flex items-center gap-1.5">
            <span className="font-mono text-base text-foreground">{d.from}</span>
            <span aria-label="에서" className="shrink-0 text-muted-foreground">
              →
            </span>
            <span className="font-mono text-base text-foreground">{d.to}</span>
            <span className="font-mono text-base text-foreground tabular-nums">
              {d.sharePmPct.toFixed(1)}%
            </span>
            <EvidenceBadge evidence={d.evidence} hint={observationHint(d)} />
            {d.variant && <VariantBadge />}
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
