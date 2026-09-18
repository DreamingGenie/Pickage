import { ExternalLinkIcon, InfoIcon } from 'lucide-react'

import { errorNotice } from '@/api/client'
import { seriesStyle } from '@/components/charts/tokens'
import { ShareBars, ShareDonut } from '@/components/charts/version-share'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
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
            <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-base text-amber-800">
              폐기 표시
            </span>
          )}
        </div>
        <span className="pl-[30px] font-mono text-xs text-muted-foreground/60">
          {model.licenses.length ? model.licenses.join(' · ') : '라이선스 미상'} · v
          {model.latestVersion}
        </span>
      </div>
      <RepositoryLink url={model.repoUrl} name={model.key} />
    </div>
  )

  return (
    <div className="flex animate-in flex-col gap-6 rounded-2xl border border-foreground/40 bg-background p-6 text-left shadow-[0_4px_24px_-12px_rgba(15,23,42,0.35)] duration-200 fade-in-0 slide-in-from-top-1">
      {header}

      {model.description && (
        <p className="-mt-2 text-base leading-relaxed text-muted-foreground">{model.description}</p>
      )}

      <ObservationBadges model={model} />

      {/* Dependents — 표시 버전과 증감. 증감은 유입·이탈로 나누지 않는다(합계값이라 나눌 수 없다) */}
      <div className="flex flex-col gap-3 border-t pt-5">
        {/*
          값이 없을 때를 위 네 타일과 **같은 모양**으로 그린다. 여기만 "—" 로 두면 같은
          카드 안에서 빈 자리 모양이 둘이 되어, 사용자가 둘을 다른 뜻으로 읽는다.

          있을 때는 증감 자체가 결론이라 부호와 색을 값에 바로 붙인다 — 늘면 붉게,
          줄면 푸르게. 날짜 구간은 적지 않는다. 이 카드는 화면에 뜬 구간을 그대로 따라가고,
          그 구간은 바로 위 조작줄이 이미 보여 주고 있다.
        */}
        {delta === null ? (
          <MissingTile label="Dependents 증감" title="증감을 내려면 관측치가 둘 이상 필요합니다" />
        ) : (
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-base text-muted-foreground">Dependents 증감</span>
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
          <Dialog>
            <DialogTrigger asChild>
              <button
                type="button"
                aria-label="Version Share 안내"
                className="rounded-full p-0.5 text-muted-foreground/70 transition-colors hover:text-foreground"
              >
                <InfoIcon aria-hidden className="size-3.5" />
              </button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-sm">
              <DialogHeader>
                <DialogTitle>Version Share</DialogTitle>
              </DialogHeader>
              <p className="text-base leading-relaxed text-muted-foreground">
                공개된 의존 조건을 major 단위로 묶은 비율입니다. 실제 설치 버전이 아니고, 한
                프로젝트가 여러 버전에 걸릴 수 있어 합계는 실제 사용처 수보다 큽니다.
              </p>
            </DialogContent>
          </Dialog>
        </div>
        {versionShareState.status === 'loading' ? (
          <Skeleton className="h-28 w-full rounded-xl" />
        ) : versionShareState.status === 'error' ? (
          <VersionShareError error={versionShareState.error} onRetry={versionShareState.onRetry} />
        ) : model.versionShare.length === 0 ? (
          <EmptyPanel
            message="버전 분포를 불러올 수 없습니다"
            hint="이 시점에 집계된 자료가 없습니다"
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
      title={`${name} 저장소 열기`}
      aria-label={`${name} 저장소 열기`}
      className="shrink-0 rounded-md border p-1.5 text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
    >
      <ExternalLinkIcon aria-hidden className="size-4" />
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
