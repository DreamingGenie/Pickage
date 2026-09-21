import { useId } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
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
 * - 선택지는 소비 조건이 있는 최근 정식 버전 3개다(BE S15P21A506-432). 하나도 없으면
 *   자동 선택을 하지 않고 그 사실을 적는다.
 * - 이 버전은 Dependency 그래프의 major 선택과 별개의 축이다(IA §7.1).
 */
export function VersionPickerCard({ run }: { run: FeatureAnalysis }) {
  const running = run.status === 'RUNNING'
  const completed = run.completed

  return (
    <section
      aria-labelledby="version-picker-title"
      className="flex flex-col gap-5 rounded-2xl border p-6"
    >
      <header className="flex flex-col gap-1.5">
        <h3 id="version-picker-title" className="text-sm font-semibold">
          기능 비교 버전 선택
        </h3>
        <p className="text-base text-muted-foreground">
          최신 안정 버전이 자동 선택되어 소비 조건이 즉시 표시됩니다. 버전 변경은 Dependency 그래프
          필터와 별도로 동작합니다.
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

        {/*
          분석 시작 버튼은 여기 없다. 아래 AI 영역이 그 실행의 주인이라 버튼도 거기 둔다 —
          버전 선택은 위 핵심 비교 요약(단순 조회)에도 쓰이므로 이 카드가 AI 실행을
          대표하면 두 영역이 한 덩어리로 읽힌다.
        */}
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
  const id = useId()
  const noStable = pkg.latestStable === null
  const differs = completedVersion !== undefined && value !== '' && value !== completedVersion

  return (
    <div className="flex min-w-48 flex-1 flex-col gap-1.5 sm:max-w-64">
      <label htmlFor={id} className="font-mono text-base text-muted-foreground">
        {pkg.name}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 rounded-md border bg-background px-3 font-mono text-sm focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50"
      >
        {value === '' && (
          <option value="" disabled>
            버전 선택
          </option>
        )}
        {pkg.choices.map((choice) => (
          <option key={choice.version} value={choice.version}>
            {choice.version === pkg.latestStable
              ? `최신 ${choice.version}`
              : choice.prerelease
                ? `${choice.version} (사전 배포)`
                : choice.version}
          </option>
        ))}
      </select>
      {noStable && (
        <p className="text-base text-muted-foreground">비교할 수 있는 버전이 아직 없습니다.</p>
      )}
      {differs && (
        <p className="text-base text-muted-foreground">
          표시 중인 결과는 <span className="font-mono">{completedVersion}</span> 기준입니다.
        </p>
      )}
    </div>
  )
}
