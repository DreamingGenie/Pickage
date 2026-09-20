import { AnalysisProgress } from '@/routes/report/_components/analysis-progress'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
import {
  AnalysisFailure,
  AnalysisStatusCard,
  NoAnalysis,
  SelectionPrompt,
} from '@/routes/report/features/analysis-status-card'
import { EnvironmentTable } from '@/routes/report/features/environment-table'
import { FeatureTable } from '@/routes/report/features/feature-table'
import { NarrativeSection } from '@/routes/report/features/narrative-section'
import { VersionPickerCard } from '@/routes/report/features/version-picker-card'

/**
 * v1-OSS-03B-feature-compare (IA §9)
 *
 * 순서: 버전 선택 → 분석 상태 → 핵심 비교 요약 → 핵심 기능 비교 → 해설.
 *
 * <h2>상태는 결과를 지우지 않는다</h2>
 *
 * 최초 분석이 끝나기 전에는 진행 카드 + skeleton 을 보여준다(IA §9.4). 한 번이라도 완료된 뒤
 * 에는 재분석 중이든, 버전을 바꿔 재분석이 필요하든, 재분석이 실패했든 **이전 완료 결과가
 * 그대로 남는다.** 성공해야만 결과가 교체된다(구상안 §9.3). 생태계 변화 탭은 이 분석을
 * 기다리지 않는다 — 대기 상태는 이 탭 안에만 있다.
 *
 * <h2>값은 어디서 오나</h2>
 *
 * `useAnalysisRun` 이 들고 있는 완료 결과다. 실 분석 API 는 아직 없어서(BE S15P21A506-130)
 * mock 이 아닌 배포본은 구상안 16장 POC 실측을 그 조합에만 돌려준다(`api/poc-features.ts`).
 * 다른 조합은 "아직 준비되지 않음"이다 — 남의 결과를 대신 띄우지 않는다.
 *
 * 셀을 눌렀을 때 열리는 근거 Drawer 는 이 탭의 일이 아니다(`EvidenceDrawer`).
 */
export function FeatureCompareTab({
  packages,
  run,
  onOpenEvidence,
}: {
  /** 보고서가 다루는 비교 대상. 주소의 `?names=` 에서 온다. */
  packages: readonly string[]
  run: FeatureAnalysis
  onOpenEvidence: (evidenceId: string) => void
}) {
  const running = run.status === 'RUNNING'
  const view = run.completed

  // 이 조합의 기능 비교가 없다. 고를 버전도, 다시 해 볼 일도 없다.
  if (run.status === 'UNAVAILABLE') return <NoAnalysis packages={packages} />

  // 버전 목록조차 못 받았다 — 버전 선택 카드를 그릴 수 없다
  if (!view && run.failure?.kind === 'VERSIONS') {
    return (
      <AnalysisFailure
        message={run.failure.message}
        retryable={run.failure.retryable}
        onRetry={run.retryVersions}
      />
    )
  }

  const progressLabels = packages.map((name) =>
    run.selected[name] ? `${name}@${run.selected[name]}` : name,
  )

  return (
    <div className="flex flex-col gap-5">
      <VersionPickerCard run={run} />

      {/* 최초 분석: 결과가 아직 없으니 자리를 skeleton 으로 잡고 진행만 보여준다 */}
      {!view && running && <AnalysisProgress run={run} packages={progressLabels} />}

      {!view && run.status === 'FAILED' && run.failure && (
        <AnalysisFailure
          message={run.failure.message}
          retryable={run.failure.retryable}
          onRetry={run.restart}
        />
      )}

      {!view && run.status === 'IDLE' && <SelectionPrompt />}

      {/* 재분석: 이전 결과를 그대로 두고 상태 카드만 위에 얹는다 (IA §9.4) */}
      {view && running && <AnalysisProgress run={run} packages={progressLabels} compactCard />}
      {view && !running && <AnalysisStatusCard run={run} />}

      {view && (
        <>
          <EnvironmentTable view={view} dimmed={running} />
          <FeatureTable view={view} dimmed={running} onOpenEvidence={onOpenEvidence} />
          <NarrativeSection view={view} dimmed={running} />
        </>
      )}
    </div>
  )
}
