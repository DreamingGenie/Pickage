import { useId } from 'react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
import type { PackageVersions } from '@/routes/report/features/model'

/**
 * 기능 비교 버전 선택 (IA §9.3).
 *
 * - 최신 안정 버전이 자동으로 골라져 있고, 그 결과가 곧바로 보인다. 설정을 마쳐야 표를 보는
 *   흐름이 아니다.
 * - 드롭다운을 바꿔도 **분석은 시작하지 않는다.** `재분석 필요` 로만 표시하고 기존 결과는
 *   유지한다. 사용자가 `선택한 버전으로 재분석` 을 눌러야 시작한다(구상안 §9.2).
 * - 정식 버전이 없으면 사전 배포 버전을 대신 고르지 않는다. 사용자의 선택을 기다린다.
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
          최신 안정 버전이 자동 선택되어 결과가 즉시 표시됩니다. 버전 변경은 Dependency 그래프
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

        <Button
          type="button"
          size="sm"
          // 드롭다운은 위쪽에 맞추고, 버튼은 라벨 높이만큼 내려 드롭다운과 같은 줄에 둔다
          className="mt-[26px] ml-auto"
          onClick={run.restart}
          disabled={!run.canStart}
        >
          {completed ? '선택한 버전으로 재분석' : '선택한 버전으로 분석'}
        </Button>
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
        <p className="text-base text-muted-foreground">
          정식 버전이 없습니다. 사전 배포 버전 중에서 직접 선택해 주세요.
        </p>
      )}
      {differs && (
        <p className="text-base text-muted-foreground">
          표시 중인 결과는 <span className="font-mono">{completedVersion}</span> 기준입니다.
        </p>
      )}
    </div>
  )
}
