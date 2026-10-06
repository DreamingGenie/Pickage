import { CheckIcon, ChevronDownIcon } from 'lucide-react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

import { ToneBadge } from '@/components/common/tone-badge'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
import { StartButton } from '@/routes/report/features/ai-comparison-section'
import type { PackageVersions } from '@/routes/report/features/model'

/**
 * 기능 비교 버전 선택 (IA §9.3).
 *
 * - 최신 안정 버전이 자동으로 골라져 있고, 그 결과가 곧바로 보인다. 설정을 마쳐야 표를 보는
 *   흐름이 아니다.
 * - 드롭다운을 바꿔도 **분석은 시작하지 않는다.** `재분석 필요` 로만 표시하고 기존 결과는
 *   유지한다. 사용자가 아래 AI 영역에서 `선택한 버전으로 재분석` 을 눌러야 시작한다(구상안 §9.2).
 * - 고른 버전은 위 핵심 비교 요약(`package_env` 단순 조회)에도 그대로 쓰인다. 그쪽은 AI 실행과
 *   무관하게 즉시 갱신된다.
 * - 선택지는 소비 조건이 있는 서로 다른 major의 최신 정식 버전 최대 3개다. 하나도 없으면
 *   자동 선택을 하지 않고 그 사실을 적는다.
 * - 이 버전은 Dependency 그래프의 major 선택과 별개의 축이다(IA §7.1).
 *
 * <h2>재분석 버튼은 완료된 뒤에만, 오른쪽에 (QA 피드백, S15P21A506-465 후속)</h2>
 *
 * 첫 실행 버튼(`기능 비교 시작`)은 여전히 아래 AI 영역에 있다 — "보통 1~2분 걸립니다" 같은
 * 안내문과 붙어 있어야 하는 문구다. 하지만 **재분석** 버튼은 다르다: 한 번 완료된 뒤에는
 * 결과·해설표까지 다 그려진 카드 맨 아래에 있었는데, 그러면 여기서 버전을 바꾸고 나서 그
 * 버튼을 누르려면 페이지 전체를 오갔다. 버전을 바꾸는 자리 바로 옆에 두면 그 왕복이 없다 —
 * 이 카드가 AI 실행의 진입점이 아니라 **AI 실행이 쓰는 입력값의 주인**이라는 점은 그대로다.
 */
export function VersionPickerCard({ run }: { run: FeatureAnalysis }) {
  const running = run.status === 'RUNNING'
  const completed = run.completed

  return (
    <section
      aria-labelledby="version-picker-title"
      className="flex flex-col gap-5 rounded-2xl border p-6"
    >
      {/* items-center — 오른쪽 재분석 버튼을 왼쪽 블록(제목+드롭다운) 높이의 중앙에 맞춘다 */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-1 flex-col gap-5">
          <header className="flex flex-col gap-1.5">
            <h3 id="version-picker-title" className="text-sm font-semibold">
              어느 버전끼리 비교할까요?
            </h3>
            <p className="text-base text-muted-foreground">
              최신 정식 버전이 먼저 골라져 있어요. 지금 쓰는 버전이 있다면 바꿔 보세요. 생태계
              변화의 표시 버전과는 따로 움직여요.
            </p>
          </header>

          <div className="flex flex-wrap items-start gap-4">
            {run.versions ? (
              run.versions.map((pkg) => {
                const done = completed?.packages.find((p) => p.name === pkg.name)?.version
                return (
                  <VersionSelect
                    key={pkg.name}
                    pkg={pkg}
                    value={run.selected[pkg.name] ?? ''}
                    disabled={running}
                    completedVersion={done}
                    onChange={(version) => run.select(pkg.name, version)}
                  />
                )
              })
            ) : (
              // 버전 목록을 받는 동안 자리를 잡는다
              <Skeleton aria-hidden className="h-9 w-56" />
            )}
          </div>
        </div>

        {/* 완료된 뒤에만 — 첫 실행 버튼은 아래 AI 영역의 안내문과 붙어 있어야 한다 */}
        {completed && !running && <StartButton run={run} />}
      </div>
    </section>
  )
}

function VersionSelect({
  pkg,
  value,
  disabled,
  completedVersion,
  onChange,
}: {
  pkg: PackageVersions
  value: string
  disabled: boolean
  /** 화면에 떠 있는 완료 결과의 버전. 선택과 다르면 함께 적어 둘을 구분한다(IA §9.3) */
  completedVersion: string | undefined
  onChange: (version: string) => void
}) {
  const labelId = useId()
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const boxRef = useRef<HTMLDivElement>(null)
  const noStable = pkg.latestStable === null
  const differs = completedVersion !== undefined && value !== '' && value !== completedVersion
  const current = pkg.choices.find((c) => c.version === value)

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  function openList() {
    const at = pkg.choices.findIndex((c) => c.version === value)
    setActive(at < 0 ? 0 : at)
    setOpen(true)
  }

  function pick(version: string) {
    onChange(version)
    setOpen(false)
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      setOpen(false)
      return
    }
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        openList()
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => Math.min(pkg.choices.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      const choice = pkg.choices[active]
      if (choice) pick(choice.version)
    }
  }

  return (
    <div ref={boxRef} className="relative flex min-w-48 flex-1 flex-col gap-1.5 sm:max-w-64">
      <span id={labelId} className="font-mono text-base text-muted-foreground">
        {pkg.name}
      </span>
      {/*
        기본 select 는 옵션 안에 라벨(최신)을 그릴 수 없어 목록을 직접 그린다. 버전 문자열과
        '최신' 딱지를 나눠 보여 준다 — "최신 6.0" 처럼 한 줄 글자로 섞으면 버전을 읽기 어렵다.
      */}
      <button
        type="button"
        role="combobox"
        aria-labelledby={labelId}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled || pkg.choices.length === 0}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
        className="flex h-10 items-center justify-between gap-2 rounded-md border bg-background px-3 text-base tabular-nums transition-colors hover:border-foreground/40 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50"
      >
        {current ? (
          <ChoiceLabel
            version={current.version}
            latest={current.version === pkg.latestStable}
            prerelease={current.prerelease}
          />
        ) : (
          <span className="text-muted-foreground">버전 고르기</span>
        )}
        <ChevronDownIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-labelledby={labelId}
          className="absolute top-full right-0 left-0 z-30 mt-1.5 max-h-64 overflow-y-auto rounded-xl border bg-card p-1 shadow-lg"
        >
          {pkg.choices.map((choice, i) => {
            const selected = choice.version === value
            return (
              <li
                key={choice.version}
                role="option"
                aria-selected={selected}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(choice.version)}
                className={cn(
                  'flex cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-base tabular-nums',
                  i === active && 'bg-muted',
                )}
              >
                <ChoiceLabel
                  version={choice.version}
                  latest={choice.version === pkg.latestStable}
                  prerelease={choice.prerelease}
                />
                {selected && <CheckIcon aria-hidden className="size-4 shrink-0" />}
              </li>
            )
          })}
        </ul>
      )}

      {noStable && (
        <p className="text-base text-muted-foreground">비교할 수 있는 버전이 아직 없어요.</p>
      )}
      {differs && (
        <p className="text-base text-muted-foreground">
          아래 결과는 아직 <span className="font-mono">{completedVersion}</span> 기준이에요.
        </p>
      )}
    </div>
  )
}

/** 버전 + 딱지. 딱지는 글자로 뜻을 말한다(색만으로 알리지 않는다, IA 1-13) */
function ChoiceLabel({
  version,
  latest,
  prerelease,
}: {
  version: string
  latest: boolean
  prerelease: boolean
}) {
  return (
    <span className="flex min-w-0 items-center gap-2">
      <span className="truncate">{version}</span>
      {latest && <ToneBadge tone="brand">최신</ToneBadge>}
      {prerelease && <ToneBadge tone="neutral">사전 배포</ToneBadge>}
    </span>
  )
}
