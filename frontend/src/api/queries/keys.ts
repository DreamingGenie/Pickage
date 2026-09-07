import type { PackageRef, ReportId } from '@/api/types'

export const queryKeys = {
  packages: {
    all: ['packages'] as const,
    resolve: (input: string) => [...queryKeys.packages.all, 'resolve', input] as const,
  },
  candidates: {
    all: ['candidates'] as const,
    list: (source: PackageRef) => [...queryKeys.candidates.all, source.name, source.range] as const,
  },
  report: {
    all: ['report'] as const,
    ecosystem: (id: ReportId) => [...queryKeys.report.all, id, 'ecosystem'] as const,
    features: (id: ReportId) => [...queryKeys.report.all, id, 'features'] as const,
    evidence: (id: string) => [...queryKeys.report.all, 'evidence', id] as const,
  },
} as const
