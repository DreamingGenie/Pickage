import { SAMPLE_ECOSYSTEM } from '@/components/charts/sample'
import { Skeleton } from '@/components/ui/skeleton'
import { EcosystemView } from '@/routes/report/ecosystem/ecosystem-view'

/**
 * v1-OSS-03A-ecosystem-report
 *
 * 미해결: Spring 스펙이 확정되면 `EcosystemModel` 로 매핑하는 어댑터를 붙인다.
 * 지금은 예시 모델을 그대로 그린다 — 화면에 "예시"로 표시한다.
 */
export function EcosystemReportTab({ reportId }: { reportId: string | undefined }) {
  if (!reportId) return <Skeleton className="h-72 w-full" />

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted-foreground">
        예시 데이터입니다. 서버 연결 후 실제 관측치로 대체됩니다.
      </p>
      <EcosystemView model={SAMPLE_ECOSYSTEM} />
    </div>
  )
}
