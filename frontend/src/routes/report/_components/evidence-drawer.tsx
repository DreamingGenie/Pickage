import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { EVIDENCE } from '@/routes/report/features/sample'

/**
 * 셀 근거 드로어 (IA 10).
 *
 * 열림 여부의 단일 출처는 `?evidence=` 다. 닫으면 쿼리에서 지운다.
 * 원본 URL·내부 경로·전체 integrity 는 내보내지 않는다(구상안 10).
 * 발췌는 기본 3줄 분량이며 전체 문서를 싣지 않는다.
 */
export function EvidenceDrawer({
  evidenceId,
  onClose,
}: {
  evidenceId: string | null
  onClose: () => void
}) {
  const record = evidenceId ? EVIDENCE[evidenceId] : undefined

  return (
    <Sheet open={Boolean(evidenceId)} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-full sm:max-w-[560px]">
        <SheetHeader>
          <SheetTitle>근거</SheetTitle>
          <SheetDescription>이 판정이 어디서 나왔는지 확인합니다.</SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-5 px-4 pb-6">
          {!evidenceId ? null : !record ? (
            <p className="text-sm text-muted-foreground">
              연결된 근거를 찾지 못했습니다. 분석을 다시 실행하면 복구될 수 있습니다.
            </p>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <h3 className="text-sm font-semibold">{record.title}</h3>
                <span className="font-mono text-[11px] text-muted-foreground">{evidenceId}</span>
              </div>

              {/* 원문 발췌와 서비스 해석을 다른 구역에 둔다 (구상안 10) */}
              <div className="flex flex-col gap-2 rounded-xl border bg-muted/40 p-4">
                <span className="text-[11px] text-muted-foreground">원문 발췌</span>
                <p className="font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap">
                  {record.excerpt}
                </p>
              </div>

              <dl className="flex flex-col gap-2 border-t pt-4 text-[12px]">
                <Row label="출처" value={record.source} />
                <Row label="수집 시각" value={record.collectedAt} />
              </dl>

              <p className="text-[11px] leading-relaxed text-muted-foreground">
                출처는 표시 문자열입니다. 외부로 이동하는 링크는 제공하지 않습니다.
              </p>
            </>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[64px_1fr] gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-[11.5px] break-words">{value}</dd>
    </div>
  )
}
