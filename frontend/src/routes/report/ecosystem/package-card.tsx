import { ArrowUpRightIcon } from 'lucide-react'

import { errorNotice } from '@/api/client'
import { seriesStyle } from '@/components/charts/tokens'
import { ShareBars, ShareDonut } from '@/components/charts/version-share'
import { InfoDialog } from '@/components/common/info-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyPanel, MissingTile, ObservationBadges } from '@/routes/report/ecosystem/badges'
import {
  ALL_MAJORS,
  type MajorSelection,
  type MetricState,
  type PackageCardModel,
} from '@/routes/report/ecosystem/model'
import { DEPENDENTS_DELTA_TERM, DEPENDENTS_TERM } from '@/routes/report/ecosystem/terms'
import { cn } from '@/lib/utils'

/**
 * 패키지 카드 — 상세 하나 전체.
 *
 * 카드를 세로로 쌓고 각자 접었다 펴던 구조를 버렸다. 비교 대상이 셋까지 늘 수 있어
 * (IA §1-2) 전부 펼치면 오른쪽 열이 차트보다 훨씬 길어졌다. 지금은 위 칩 줄이 고른
 * 하나만 `EcosystemView` 가 렌더한다 — 그래서 이 컴포넌트 안에 접힘 상태가 없다.
 */
export function PackageCard({
  model,
  index,
  selectedVersion,
  onVersionChange,
  versionShareState = { status: 'ready' },
}: {
  model: PackageCardModel
  index: number
  /** 구상안 §5.2 — 이 카드만의 표시 버전들. 다른 카드와 독립이다. 빈 배열이 "전체". */
  selectedVersion: MajorSelection
  onVersionChange: (next: MajorSelection) => void
  /** Version Share 조회의 처지(126) — 응답 하나가 전체 카드를 담으므로 카드마다 갈리지 않는다. */
  versionShareState?: MetricState
}) {
  const style = seriesStyle(index)
  const isBase = index === 0
  const delta = model.dependentsDelta

  /*
    머리글. 이름 아래 줄에 라이선스와 버전을 둔다 — 라이선스는 "이걸 써도 되나" 를
    가르는 값이라 카드 맨 아래에 있으면 스크롤해야 보였다. 저장소는 주소를 그대로
    늘어놓지 않고 아이콘 하나로 줄여 이름에서 떨어진 오른쪽 끝에 둔다.
  */
  const header = (
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex min-w-0 items-center gap-2.5">
          <svg width="20" height="8" aria-hidden className="shrink-0">
            <line
              x1="0"
              y1="4"
              x2="20"
              y2="4"
              stroke={style.color}
              strokeWidth="2.6"
              strokeDasharray={style.dash}
              strokeLinecap="round"
            />
          </svg>
          <span className="truncate font-mono text-base font-medium">{model.key}</span>
          {isBase && (
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-base text-muted-foreground">
              기준
            </span>
          )}
          {model.isDeprecated && (
            <span className="shrink-0 rounded bg-tone-down px-1.5 py-0.5 text-base text-tone-down-foreground">
              지원 종료
            </span>
          )}
        </div>
        <span className="pl-[30px] font-mono text-xs text-muted-foreground/60">
          {model.licenses.length ? model.licenses.join(' · ') : '라이선스 정보 없음'} · v
          {model.latestVersion}
        </span>
      </div>
      <RepositoryLink url={model.repoUrl} name={model.key} />
    </div>
  )

  return (
    /*
      justify-center: 왼쪽 그래프 열이 더 길면 이 카드가 그 높이로 늘어난다(`EcosystemView` 의 그리드).
      그때 남는 자리가 아래에만 몰리지 않도록 안의 요소를 세로 중앙에 둔다(S15P21A506-405).
    */
    <div className="flex animate-in flex-col justify-center gap-6 rounded-2xl border border-foreground/40 bg-background p-6 text-left shadow-[0_4px_24px_-12px_rgba(15,23,42,0.35)] duration-200 fade-in-0 slide-in-from-top-1">
      {header}

      {model.description && (
        <p className="-mt-2 text-base leading-relaxed text-muted-foreground">{model.description}</p>
      )}

      {/* "최신 버전 폐기 표시" 가 무슨 뜻인지 모르겠다는 의견 — 배지만 두지 않고 뜻을 풀어 준다 */}
      {model.isDeprecated && (
        <div role="note" className="flex flex-col gap-1 rounded-xl bg-tone-down px-4 py-3">
          <p className="font-semibold text-tone-down-foreground">
            만든 사람이 더 이상 쓰지 말라고 안내하고 있어요
          </p>
          <p className="text-sm leading-relaxed text-tone-down-foreground/90">
            최신 버전에 &lsquo;지원 종료(deprecated)&rsquo; 표시가 붙어 있어요. 설치는 되지만 앞으로
            고쳐지지 않을 수 있어요.
          </p>
        </div>
      )}

      <ObservationBadges model={model} />

      {/* 의존 수 — 표시 버전과 증감. 증감은 유입·이탈로 나누지 않는다(합계값이라 나눌 수 없다) */}
      <div className="flex flex-col gap-3 border-t pt-5">
        {/*
          값이 없을 때를 위 네 타일과 **같은 모양**으로 그린다. 여기만 "—" 로 두면 같은
          카드 안에서 빈 자리 모양이 둘이 되어, 사용자가 둘을 다른 뜻으로 읽는다.

          있을 때는 증감 자체가 결론이라 부호와 색을 값에 바로 붙인다 — 늘면 붉게,
          줄면 푸르게. 날짜 구간은 적지 않는다. 이 카드는 화면에 뜬 구간을 그대로 따라가고,
          그 구간은 바로 위 조작줄이 이미 보여 주고 있다.
        */}
        {delta === null ? (
          <MissingTile
            label={DEPENDENTS_DELTA_TERM}
            title="증감을 보려면 두 번 이상 모은 자료가 필요해요"
          />
        ) : (
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-base text-muted-foreground">{DEPENDENTS_DELTA_TERM}</span>
            <span
              className={cn(
                'font-mono text-lg leading-none font-semibold tabular-nums',
                delta > 0
                  ? 'text-rose-600 dark:text-rose-400'
                  : delta < 0
                    ? 'text-blue-600 dark:text-blue-400'
                    : 'text-muted-foreground',
              )}
            >
              {delta > 0 ? '+' : delta < 0 ? '−' : '±'}
              {Math.abs(delta).toLocaleString()}
            </span>
          </div>
        )}

        <VersionPicker
          majors={model.availableMajors}
          selected={selectedVersion}
          onChange={onVersionChange}
          label={`${model.key} 표시 버전`}
        />
      </div>

      {/* Version Share — 126: "이 시점 자료 없음"과 "조회 실패"를 다른 문구로 분리한다 */}
      <div className="flex flex-col gap-3 border-t pt-5">
        <div className="flex items-center gap-1.5">
          <span className="text-base text-muted-foreground">Version Share</span>
          {/*
            안내 문단을 인라인에 상시 노출하면 카드가 길어져 옆 차트 열과 하단이
            어긋난다. 문구 자체(조각 합계가 실제 사용처 수보다 크다는 것)는 매번
            읽어야 하는 경고가 아니라 궁금할 때 찾아보는 설명이라 모달로 옮긴다.
          */}
          <InfoDialog label="Version Share 안내" title="Version Share">
            <p>
              이 패키지를 적어 둔 쪽이 어떤 큰 버전(major, 예: 4.x · 5.x)을 조건으로 걸었는지 나눈
              비율이에요. 실제로 설치된 버전은 아니에요. 한 프로젝트가 여러 버전에 걸릴 수 있어서
              조각을 모두 더하면 실제 프로젝트 수보다 커요.
            </p>
          </InfoDialog>
        </div>
        {versionShareState.status === 'loading' ? (
          <Skeleton className="h-28 w-full rounded-xl" />
        ) : versionShareState.status === 'error' ? (
          <VersionShareError error={versionShareState.error} onRetry={versionShareState.onRetry} />
        ) : model.versionShare.length === 0 ? (
          <EmptyPanel
            message="버전 분포를 보여 드릴 수 없어요"
            hint="이 날짜에 모아 둔 자료가 없어요"
          />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-5">
              <ShareDonut
                groups={model.versionShare}
                size={104}
                ariaLabel={`${model.key} major 버전 분포`}
              />
              <ShareBars groups={model.versionShare} />
            </div>
            {/* 명세 §5·§6 — 조각 합계는 버전별 합산이라 실제 사용처 수보다 크다.
                그 설명은 위 정보 버튼 모달로 옮겼다(비율만 적고 총계를 쓰지 않는 이유). */}
          </>
        )}
        {versionShareState.status === 'ready' && versionShareState.refreshError !== undefined && (
          <p className="-mt-1.5 flex flex-wrap items-baseline gap-2 text-base leading-relaxed text-muted-foreground">
            <span>새 자료를 받지 못해서, 마지막으로 받은 자료로 그렸어요.</span>
            {versionShareState.onRetry && errorNotice(versionShareState.refreshError).retryable && (
              <button
                type="button"
                onClick={versionShareState.onRetry}
                className="underline underline-offset-2 hover:text-foreground"
              >
                다시 시도
              </button>
            )}
          </p>
        )}
      </div>
    </div>
  )
}

/**
 * 저장소 바로가기.
 *
 * 주소를 그대로 적지 않는다 — 카드 폭에서 잘려 읽을 수도 없고, 읽을 필요도 없다.
 *
 * `http(s)` 로 시작하는 주소만 링크로 만든다. 수집원이 `git@…` 이나 `git+ssh://` 를
 * 그대로 주는 경우가 있는데, 그걸 `href` 에 넣으면 눌러도 아무 일이 안 일어난다.
 */
function RepositoryLink({ url, name }: { url: string | null; name: string }) {
  if (!url || !/^https?:\/\//.test(url)) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={`${name} 소스 코드 보기 (새 탭)`}
      className="flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm font-medium text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
    >
      {/* 아이콘만 두면 누르면 무엇이 열리는지 알 수 없다 — 글자와 바깥으로 나가는 화살표를 함께 둔다 */}
      <ArrowUpRightIcon aria-hidden className="size-4" />
      소스 코드 보기
    </a>
  )
}

/**
 * 표시 버전 선택기 (구상안 §5.2). **여러 개를 고를 수 있고, 고른 것을 합한다.**
 *
 * **이 카드의 Dependents 선만 바꾼다.** 다른 카드도, 버전 분포도, 기능 비교도 건드리지 않는다.
 * 서버에 다시 묻지도 않는다 — major 별 시리즈를 이미 다 받아 두었다.
 *
 * "전체" 는 **모두 끄는 버튼**이지 다른 버전들과 나란한 선택지가 아니다. 같은 줄에 두면
 * "전체 + 4.x" 를 동시에 누를 수 있어 보이는데, 그건 뜻이 없는 상태다.
 *
 * 마지막 하나를 끄면 자동으로 전체로 돌아간다 — 아무것도 안 고른 빈 그래프는 조작 실수이지
 * 보고 싶은 화면이 아니다.
 *
 * 고를 것이 없으면(자료 없음, 또는 major 가 하나뿐) 선택기를 그리지 않는다.
 * 누를 수 없는 버튼 한 개는 조작할 수 있다는 잘못된 신호를 준다.
 *
 * 선택 상태를 색으로만 알리지 않는다 — `aria-pressed` 와 테두리를 함께 쓴다.
 */
function VersionPicker({
  majors,
  selected,
  onChange,
  label,
}: {
  majors: string[]
  selected: MajorSelection
  onChange: (next: MajorSelection) => void
  label: string
}) {
  if (majors.length < 2) return null

  const isAll = selected.length === 0

  function toggle(major: string) {
    const next = selected.includes(major)
      ? selected.filter((m) => m !== major)
      : [...selected, major]
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-pressed={isAll}
          onClick={() => onChange(ALL_MAJORS)}
          className={cn(
            'rounded-md border px-2 py-1 text-base transition-colors duration-150',
            isAll
              ? 'border-foreground/50 bg-foreground/[0.06] font-medium text-foreground'
              : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
          )}
        >
          전체
        </button>

        <span aria-hidden className="mx-0.5 h-4 w-px bg-border" />

        {majors.map((m) => {
          const active = selected.includes(m)
          return (
            <button
              key={m}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(m)}
              className={cn(
                'rounded-md border px-2 py-1 font-mono text-base transition-colors duration-150',
                active
                  ? 'border-foreground/50 bg-foreground/[0.06] font-medium text-foreground'
                  : 'text-muted-foreground hover:border-foreground/30 hover:text-foreground',
              )}
            >
              {m}.x
            </button>
          )
        })}

        {/*
          "전 버전을 합한 값입니다 …" 문장을 여기로 옮겼다(S15P21A506-405). 버튼이 무엇을 하는지는
          눌린 상태로 보이고, 왜 그런 값인지는 궁금할 때만 찾아보면 된다.
        */}
        <InfoDialog label="표시 버전 안내" title="표시 버전" className="ml-0.5">
          <p>
            &lsquo;전체&rsquo;는 모든 큰 버전(major)을 합한 값이에요. 4.x 처럼 하나 이상 골라 합쳐
            볼 수 있고, 고른 버전의 합계가 {DEPENDENTS_TERM} 그래프와 {DEPENDENTS_TERM} 증감에
            반영돼요.
          </p>
          <p>
            {isAll
              ? '지금은 전체를 보고 있어요.'
              : `지금은 고른 ${selected.length}개 버전을 합해 보고 있어요.`}{' '}
            이 선택은 이 패키지에만 적용되고, 다른 패키지에는 영향을 주지 않아요.
          </p>
        </InfoDialog>
      </div>
    </div>
  )
}

/**
 * Version Share 조회 자체가 실패했을 때. "이 시점 자료 없음"(정상 200, 빈 배열)과는
 * 다른 문구를 쓴다 — 전자는 조회했지만 그 시점 자료가 없다는 뜻이고, 이건 조회를 못 했다는 뜻이다.
 */
function VersionShareError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
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
