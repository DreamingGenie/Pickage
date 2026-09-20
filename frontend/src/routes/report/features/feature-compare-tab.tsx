import { usePackageEnv } from '@/api/queries'
import type { FeatureAnalysis } from '@/routes/report/_components/use-analysis-run'
import { AiComparisonSection } from '@/routes/report/features/ai-comparison-section'
import { AnalysisFailure, NoAnalysis } from '@/routes/report/features/analysis-status-card'
import { environmentNote, toEnvironmentRows } from '@/routes/report/features/environment-adapter'
import { EnvironmentTable } from '@/routes/report/features/environment-table'
import type { ComparisonPackage } from '@/routes/report/features/model'
import { VersionPickerCard } from '@/routes/report/features/version-picker-card'

/**
 * v1-OSS-03B-feature-compare (IA §9)
 *
 * 순서: 버전 선택 → **핵심 비교 요약** → AI 기능 비교.
 *
 * <h2>두 영역은 독립이다</h2>
 *
 * 핵심 비교 요약은 `GET /api/packages/env` 에서 온다 — 배치가 미리 접어 둔 표를 키 조회하는
 * **단순 비교**라 버전을 고르는 즉시 뜨고, AI 가 돌든 실패하든 상관하지 않는다. 아래 AI
 * 영역은 눌러야 시작하고 분 단위로 간다. 묶으면 **확인된 사실까지 생성이 끝날 때까지 못
 * 보여 준다**(기능-10-R06).
 *
 * 그래서 분석이 도는 중에도 위 표는 흐려지지 않는다. 흐리면 "이것도 아직 확정이 아니다" 로
 * 읽히는데, 그 값들은 LLM 이 만든 것이 아니라 배포 산출물에서 기계적으로 읽은 것이다.
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
  /**
   * 버전이 정해진 것만 소비 조건을 묻는다.
   *
   * 버전을 모르는 채로 물으면 서버가 V004 로 거절한다 — 정확한 버전에 붙는 표라서
   * "최신" 같은 것을 대신 고르지 않는다(기능-10-R01).
   */
  const targets: ComparisonPackage[] = packages
    .filter((name) => run.selected[name])
    .map((name) => ({ name, version: run.selected[name] as string }))

  const env = usePackageEnv(targets.map((t) => ({ package_name: t.name, version: t.version })))

  // 이 조합의 기능 비교가 없다. 고를 버전도, 다시 해 볼 일도 없다.
  if (run.status === 'UNAVAILABLE') return <NoAnalysis packages={packages} />

  // 버전 목록조차 못 받았다 — 버전 선택 카드를 그릴 수 없다
  if (run.failure?.kind === 'VERSIONS') {
    return (
      <AnalysisFailure
        message={run.failure.message}
        retryable={run.failure.retryable}
        onRetry={run.retryVersions}
      />
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <VersionPickerCard run={run} />

      {/* 배치 산출물의 단순 조회다. AI 를 기다리지 않고, 분석 중에도 흐려지지 않는다. */}
      <EnvironmentTable
        packages={targets}
        rows={toEnvironmentRows(targets, env.data)}
        note={environmentNote(env.data)}
        loading={env.isPending && targets.length > 0}
      />

      {/*
        여기부터 AI 영역이다. 위와 시각적으로 갈라 둔다 — 값의 출처가 다르다는 것이 화면에서
        보여야 한다. 위는 배포 산출물에서 읽은 사실이고, 아래는 그 사실 위에 LLM 이 붙인 판정이다.
      */}
      <AiComparisonSection run={run} onOpenEvidence={onOpenEvidence} />
    </div>
  )
}
