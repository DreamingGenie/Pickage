import { ChevronDownIcon, ExternalLinkIcon } from 'lucide-react'

import { errorNotice } from '@/api/client'
import { seriesStyle } from '@/components/charts/tokens'
import { ShareBars, ShareDonut } from '@/components/charts/version-share'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyPanel, MissingTile, ObservationBadges } from '@/routes/report/ecosystem/badges'
import {
  ALL_MAJORS,
  type MajorSelection,
  type MetricState,
  type PackageCardModel,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

/**
 * 패키지 카드.
 *
 * 기본은 전부 펼침. 여러 개를 동시에 펼 수 있고, 직접 접기 전까지 닫히지 않는다.
 *
 * 접힘: 패키지 이름과 최신 버전. 그리고 그 패키지 선이 차트에서 물러난다.
 * 펼침: 뱃지 · Dependents 증감 · Version Share 상세.
 *
 * 접힘 상태에도 선 견본은 남긴다 — 그래프의 어느 선이 이 패키지인지
 * 알 수 없으면 접힌 목록이 쓸모없어진다.
 */
export function PackageCard({
  model,
  index,
  expanded,
  onToggle,
  selectedVersion,
  onVersionChange,
  versionShareState = { status: 'ready' },
}: {
  model: PackageCardModel
  index: number
  expanded: boolean
  onToggle: () => void
  /** 구상안 §5.2 — 이 카드만의 표시 버전들. 다른 카드와 독립이다. 빈 배열이 "전체". */
  selectedVersion: MajorSelection
  onVersionChange: (next: MajorSelection) => void
  /** Version Share 조회의 처지(126) — 응답 하나가 전체 카드를 담으므로 카드마다 갈리지 않는다. */
  versionShareState?: MetricState
}) {
  const style = seriesStyle(index)
  const isBase = index === 0
  const delta = model.dependentsDelta

  const license = model.licenses.length ? model.licenses.join(' · ') : null

  /*
    머리글은 **세 덩어리**다. 접기 버튼이 이름 쪽만 감싸고, 저장소 링크는 그 오른쪽에
    형제로 선다 — button 안의 a 는 HTML 이 허용하지 않고, 넣더라도 링크를 누를 때 클릭이
    바깥으로 새어 카드가 같이 접힌다.

    오른쪽 끝의 버전·화살표도 눌러서 접히게 두되 보조기술에는 숨긴다. 같은 일을 하는
    버튼이 둘로 읽히면 "접기" 가 두 번 들린다.
  */
  const title = (
    <span className="flex min-w-0 items-start gap-2.5">
      <svg width="20" height="8" aria-hidden className="mt-2 shrink-0">
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
      <span className="flex min-w-0 flex-col gap-0.5">
        <span className="flex min-w-0 items-center gap-2.5">
          <span className="truncate font-mono text-base font-medium">{model.key}</span>
          {isBase && (
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-base text-muted-foreground">
              기준
            </span>
          )}
          {model.isDeprecated && (
            <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-base text-amber-800">
              폐기 표시
            </span>
          )}
        </span>
        {/* 라이선스. 이름을 읽는 데 방해가 되면 안 되므로 한 단계 더 죽인다 */}
        {license && (
          <span className="truncate font-mono text-xs text-muted-foreground/60">{license}</span>
        )}
      </span>
    </span>
  )

  const header = (
    <div className="flex items-start gap-3">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex min-w-0 items-start text-left"
      >
        {title}
      </button>
      <RepositoryLink url={model.repoUrl} name={model.key} />
      <button
        type="button"
        onClick={onToggle}
        tabIndex={-1}
        aria-hidden
        className="ml-auto flex shrink-0 items-center gap-2 pt-0.5"
      >
        <span className="font-mono text-base text-muted-foreground">v{model.latestVersion}</span>
        <ChevronDownIcon
          aria-hidden
          className={cn(
            'size-4 text-muted-foreground transition-transform duration-200',
            expanded && 'rotate-180',
          )}
        />
      </button>
    </div>
  )

  if (!expanded) {
    return (
      <div className="rounded-2xl border bg-background px-6 py-5 transition-colors duration-200 hover:border-foreground/30 hover:bg-muted/30">
        {header}
      </div>
    )
  }

  /*
    펼친 카드는 button 이 아니라 div 다. 안에 표시 버전 선택기가 들어가는데,
    button 안의 button 은 HTML 이 허용하지 않고 클릭이 바깥으로 새어 카드가 접힌다.
    접기는 머리글만 담당한다.
  */
  return (
    <div
      /*
        펼칠 때만 살짝 들어온다. `transform`(translate)과 `opacity` 만 건드려 합성
        단계에서 끝나므로 재배치가 일어나지 않는다. 높이를 전이하면 매 프레임 레이아웃이
        다시 계산되고, 옆의 차트가 폭을 실측하고 있어 그때마다 같이 다시 그려진다.
        `animate-in` 은 dialog·sheet 와 같은 tw-animate-css 유틸이다.
      */
      className="flex animate-in flex-col gap-6 rounded-2xl border border-foreground/40 bg-background p-6 text-left shadow-[0_4px_24px_-12px_rgba(15,23,42,0.35)] duration-200 fade-in-0 slide-in-from-top-1 motion-reduce:animate-none"
    >
      {header}

      {model.description && (
        <p className="-mt-2 text-base leading-relaxed text-muted-foreground">{model.description}</p>
      )}

      <ObservationBadges model={model} />

      {/* Dependents — 표시 버전과 증감. 증감은 유입·이탈로 나누지 않는다(합계값이라 나눌 수 없다) */}
      <div className="flex flex-col gap-3 border-t pt-5">
        {/*
          값이 없을 때 `—` 만 찍으면 "0 인가" 와 "못 구했나" 가 구분되지 않는다. 위 네 타일이
          이미 그 구분을 모양으로 하고 있으므로 같은 타일을 쓴다 — 빈 자리 모양이 화면에
          하나뿐이어야 사용자가 다른 뜻으로 읽지 않는다.
        */}
        {delta === null ? (
          <MissingTile
            label="Dependents 증감"
            title="이 구간에 값이 있는 점이 둘 이상 있어야 증감을 낼 수 있습니다"
          />
        ) : (
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-base text-muted-foreground">Dependents 증감</span>
            <span className="flex items-baseline gap-2">
              {/* 뱃지 타일의 변량과 같은 약속 — 오름은 붉게, 내림은 푸르게, 부호를 항상 붙인다 */}
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
              <span className="text-base text-muted-foreground">화면에 뜬 구간</span>
            </span>
          </div>
        )}
        {/*
          311c — 표시 간격에 따라 "화면에 뜬 첫 점"이 구간 시작과 정확히 같지 않을 수 있다
          (`sampleEvery`가 뒤에서부터 솎기 때문). 그래서 실제로 증감을 낸 두 날짜를 그대로 적는다.
        */}
        {delta !== null && model.dependentsDeltaFrom && model.dependentsDeltaTo && (
          <p className="-mt-1.5 font-mono text-base text-muted-foreground">
            {model.dependentsDeltaFrom} ~ {model.dependentsDeltaTo}
          </p>
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
        <span className="text-base text-muted-foreground">Version Share</span>
        {versionShareState.status === 'loading' ? (
          <Skeleton className="h-28 w-full rounded-xl" />
        ) : versionShareState.status === 'error' ? (
          <VersionShareError error={versionShareState.error} onRetry={versionShareState.onRetry} />
        ) : model.versionShare.length === 0 ? (
          /* 도넛이 들어갈 자리라 넓다. 한 줄 문장만 두면 카드에 구멍이 뚫린 것처럼 보인다 */
          <EmptyPanel
            message="이 시점의 버전 분포 자료가 없습니다"
            hint="다음 집계에서 채워집니다"
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
            {/*
              명세 §5·§6 — 조각 합계는 버전별 합산이라 실제 사용처 수보다 크다.
              그래서 비율만 적고 총계를 쓰지 않는다.
            */}
            <p className="text-base leading-relaxed text-muted-foreground">
              공개된 의존 조건을 major 단위로 묶은 비율입니다. 실제 설치 버전이 아니고, 한
              프로젝트가 여러 버전에 걸릴 수 있어 합계는 실제 사용처 수보다 큽니다.
            </p>
          </>
        )}
        {versionShareState.status === 'ready' && versionShareState.refreshError !== undefined && (
          <p className="-mt-1.5 flex flex-wrap items-baseline gap-2 text-base leading-relaxed text-muted-foreground">
            <span>최신 자료를 받지 못해 마지막으로 받은 것을 그렸습니다.</span>
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
 * <p>주소를 그대로 적지 않는다. `https://github.com/...` 는 한 줄을 다 먹으면서도
 * 누를 수 없었고, 잘라 쓰면 어디로 가는지 알 수 없다. 아이콘 버튼으로 두고 주소는
 * `title` 로 옮긴다 — 확인하고 싶은 사람은 올려 보면 된다.
 *
 * <p><b>http(s) 가 아니면 아예 그리지 않는다.</b> 주소는 수집한 자료라 우리가 쓴 값이
 * 아니다. `javascript:` 같은 스킴이 섞여 들어오면 클릭 한 번이 스크립트 실행이 된다.
 */
function RepositoryLink({ url, name }: { url: string | null; name: string }) {
  if (!url || !/^https?:\/\//i.test(url)) return null
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      title={url}
      aria-label={`${name} 저장소 열기 (새 탭)`}
      className="ml-auto inline-flex size-8 shrink-0 items-center justify-center rounded-md border transition-colors hover:border-foreground/40 hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40 focus-visible:outline-none"
    >
      <ExternalLinkIcon className="size-4" aria-hidden />
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
      </div>
      <p className="text-base leading-relaxed text-muted-foreground">
        {isAll
          ? '전 버전을 합한 값입니다. 여러 개를 골라 합쳐 볼 수 있습니다.'
          : `고른 ${selected.length}개 버전을 합한 값입니다. 다른 패키지의 선택과는 무관합니다.`}
      </p>
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
