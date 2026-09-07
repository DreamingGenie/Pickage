import { useQuery } from '@tanstack/react-query'

import { get } from '@/api/client'
import { queryKeys } from '@/api/queries/keys'
import type {
  CandidateListResponse,
  EcosystemReport,
  Evidence,
  FeatureCompareReport,
  PackageRef,
  PackageResolution,
  ReportId,
} from '@/api/types'

export { queryKeys }

export function usePackageResolution(input: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.packages.resolve(input),
    queryFn: () => get<PackageResolution>('/packages/resolve', { q: input }),
    enabled: enabled && input.trim().length > 0,
  })
}

export function useCandidates(source: PackageRef | null) {
  return useQuery({
    queryKey: queryKeys.candidates.list(source ?? { name: '', range: null }),
    queryFn: () =>
      get<CandidateListResponse>('/candidates', {
        name: source?.name,
        range: source?.range ?? undefined,
      }),
    enabled: Boolean(source?.name),
  })
}

export function useEcosystemReport(reportId: ReportId | undefined) {
  return useQuery({
    queryKey: queryKeys.report.ecosystem(reportId ?? ''),
    queryFn: () => get<EcosystemReport>(`/reports/${reportId}/ecosystem`),
    enabled: Boolean(reportId),
  })
}

export function useFeatureCompareReport(reportId: ReportId | undefined) {
  return useQuery({
    queryKey: queryKeys.report.features(reportId ?? ''),
    queryFn: () => get<FeatureCompareReport>(`/reports/${reportId}/features`),
    enabled: Boolean(reportId),
  })
}

export function useEvidence(evidenceId: string | null) {
  return useQuery({
    queryKey: queryKeys.report.evidence(evidenceId ?? ''),
    queryFn: () => get<Evidence>(`/evidence/${evidenceId}`),
    enabled: Boolean(evidenceId),
  })
}
