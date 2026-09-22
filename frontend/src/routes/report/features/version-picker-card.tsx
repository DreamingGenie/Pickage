import { useId } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
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
            버전 고르기
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
