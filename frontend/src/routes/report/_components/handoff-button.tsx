import { FileCode2Icon, Loader2Icon } from 'lucide-react'

import { errorNotice } from '@/api/client'
import { markdownDownloadUrl } from '@/api/endpoints'
import { useGenerateHandoff } from '@/api/queries'
import type { TransitionPeriodParam } from '@/api/types'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  featuresExportable,
  reportExportReady,
} from '@/routes/report/_components/report-export-eligibility'
import type { AnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { toFeaturesPdfPayload } from '@/routes/report/features/rag-adapter'

/**
 * HAND-OFF — agent 친화적 Markdown 다운로드 (S15P21A506-467).
 *
 * <h2>PDF와 달리 모달이 없다</h2>
 *
 * 구역 선택도 없다 — 항상 전체(커뮤니티·기능 심화 분석)를 시도한다. agent가 읽을 파일이라
 * 인쇄 분량 걱정이 없고, 판단에 쓸 정보는 많을수록 낫다(기획 결정). 그래서 PDF처럼 "더할
 * 구역을 고르는" 확인 화면이 필요 없다 — 누르면 바로 만들고 바로 받는다.
 *
 * 클릭 → 생성(버튼이 스스로 스피너로 바뀐다) → 성공하면 숨은 `<a>`로 즉시 다운로드를 튼다.
 * `pdf-export-dialog.tsx`의 다운로드 링크와 같은 "blob 안 쓴다" 철학이다 — 서버가
 * `attachment`로 보내므로 앵커를 여는 것만으로 저장된다. 여기서는 그 클릭을 프로그램이
 * 대신할 뿐이다.
 *
 * <h2>자격 조건은 PDF와 같다</h2>
 *
 * `report-export-eligibility.ts`를 그대로 쓴다. 기능 비교는 선행 조건이 아니다(2026-09-22) —
 * 완료 결과가 있을 때만 싣고, 없으면 그 구역만 빠진다.
 */
export function HandoffButton({
  packages,
  from,
  to,
  snapshotAt,
  transitionPeriod,
  run,
}: {
  packages: string[]
  from?: string
  to?: string
  snapshotAt?: string
  transitionPeriod: TransitionPeriodParam
  run: AnalysisRun
}) {
  const generate = useGenerateHandoff()
  const ready = reportExportReady(run)

  function submit() {
    if (!ready || generate.isPending) return
    generate.mutate(
      {
        names: packages,
        from,
        to,
        snapshot_at: snapshotAt,
        period: transitionPeriod,
        // 서버는 판정을 저장하지 않는다(DEC-FEATURE-CACHE-20260917-01) — 세션이 들고 있는
        // 완료 결과를 요청에 실어 보낸다. PDF와 같은 규칙(pdf-export-dialog.tsx 참고).
        // 지금 고른 버전의 완료 결과일 때만 싣는다. 없으면 기능 비교 구역만 빠진다.
        features:
          featuresExportable(run) && run.rawResult
            ? toFeaturesPdfPayload(run.rawResult)
            : undefined,
      },
      { onSuccess: triggerDownload },
    )
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button
        type="button"
        size="sm"
        variant={ready ? 'default' : 'outline'}
        aria-describedby={ready ? undefined : 'pdf-hint'}
        aria-busy={generate.isPending}
        className={cn(!ready && 'text-muted-foreground')}
        onClick={submit}
      >
        {generate.isPending ? (
          <Loader2Icon className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <FileCode2Icon className="size-3.5" aria-hidden />
        )}
        {generate.isPending ? '만드는 중' : 'HAND-OFF'}
      </Button>
      {generate.isError && (
        <span role="alert" className="text-xs text-destructive">
          {errorNotice(generate.error).message}
        </span>
      )}
    </div>
  )
}

/**
 * 숨은 앵커를 만들어 한 번 클릭하고 지운다. `URL.createObjectURL`/blob 을 안 쓴다 — 서버가
 * 이미 `attachment` 로 응답하므로 주소를 여는 것만으로 브라우저가 저장한다.
 */
function triggerDownload(job: { report_id: string; file_name: string }) {
  const a = document.createElement('a')
  a.href = markdownDownloadUrl(job.report_id)
  a.download = job.file_name
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
