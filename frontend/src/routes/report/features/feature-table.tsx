import { cn } from '@/lib/utils'
import {
  cellReason,
  evidenceLabel,
  type ComparisonView,
  type FeatureCell,
} from '@/routes/report/features/model'
import { VERDICT_LABEL } from '@/routes/report/features/sample'
import { VerdictPill } from '@/routes/report/features/verdict-pill'

/**
 * 핵심 기능 비교표 (IA §9.2).
 *
 * 긴 조건 설명과 발췌는 표에 넣지 않는다 — 근거 Drawer 와 하단 해설이 맡는다. 데이터 셀
 * 전체가 Drawer 열기 대상이다. 미확인 셀에는 **왜 미확인인지**를 글자로 적는다(색만으로
 * 구분하지 않는다).
 */
export function FeatureTable({
  view,
  dimmed,
  onOpenEvidence,
}: {
  view: ComparisonView
  /** 재분석 중 — 이전 결과를 그대로 두되 흐리게 */
  dimmed: boolean
  onOpenEvidence: (evidenceId: string) => void
}) {
  const count = view.rows.length

  return (
    <section
      aria-labelledby="feature-table-title"
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 transition-opacity',
        dimmed && 'opacity-60',
      )}
    >
      <header className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-baseline gap-2">
          <h3 id="feature-table-title" className="text-sm font-semibold">
            핵심 기능 비교
          </h3>
          {/*
            분석 서버가 그 자리에서 만든 값이 아니라 미리 확인해 둔 POC 실측이다.
            어디서 온 숫자인지 화면에 적지 않으면 구분할 방법이 없다.
          */}
          {view.isExample && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10.5px] text-muted-foreground">
              구상안 16장 POC 실측 예시
            </span>
          )}
        </div>
        {count > 0 && (
          <p className="text-base text-muted-foreground">
            선택한 버전의 README 에서 찾은 기능 {count}가지입니다.
          </p>
        )}
      </header>

      {/* 억지 표를 만들지 않는다(구상안 §8) — 확인 가능한 항목만 두고 제한을 밝힌다 */}
      {view.limited && (
        <p
          role="note"
          className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground"
        >
          직접 비교 가능한 기능이 제한적입니다
        </p>
      )}

      {count > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-base">
            <thead>
              <tr className="text-muted-foreground">
                <th scope="col" className="pb-3 text-left font-normal">
                  기능
                </th>
                {view.packages.map((pkg) => (
                  <th key={pkg.name} scope="col" className="pb-3 text-left font-normal">
                    <span className="font-mono text-foreground">{pkg.name}</span>
                    <span className="ml-1.5 font-mono">{pkg.version}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {view.rows.map((row) => (
                <tr key={row.id} className="border-t align-top">
                  <th scope="row" className="py-3 pr-3 text-left font-normal text-muted-foreground">
                    {row.label}
                  </th>
                  {row.cells.map((cell) => (
                    <td key={cell.packageName} className="py-2">
                      <Cell feature={row.label} cell={cell} onOpenEvidence={onOpenEvidence} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="border-t pt-4 text-base leading-relaxed text-muted-foreground">
        <strong className="font-medium text-foreground">미확인</strong>은 &lsquo;기능이
        없다&rsquo;가 아니라 README 에서 찾지 못했다는 뜻입니다.{' '}
        <strong className="font-medium text-foreground">미지원</strong>은 README 에 지원하지
        않는다고 적혀 있을 때만 씁니다.
      </p>
    </section>
  )
}

function Cell({
  feature,
  cell,
  onOpenEvidence,
}: {
  feature: string
  cell: FeatureCell
  onOpenEvidence: (evidenceId: string) => void
}) {
  const reason = cellReason(cell)
  const label = evidenceLabel(cell)
  const evidenceId = cell.evidenceIds[0]

  const body = (
    <>
      <VerdictPill verdict={cell.verdict} />
      {cell.note && (
        <span className="text-base leading-snug text-muted-foreground">{cell.note}</span>
      )}
      {reason && <span className="text-base leading-tight text-muted-foreground">{reason}</span>}
      {label && (
        <span className="text-sm text-muted-foreground underline underline-offset-2">
          출처 · {label}
        </span>
      )}
    </>
  )

  // 근거가 없는 셀은 열 것이 없다 — 버튼처럼 보이지 않게 한다
  if (!evidenceId) {
    return <div className="-mx-2 flex flex-col items-start gap-1 px-2 py-1.5">{body}</div>
  }

  return (
    <button
      type="button"
      onClick={() => onOpenEvidence(evidenceId)}
      aria-label={`${feature} ${cell.packageName} ${VERDICT_LABEL[cell.verdict]} — 출처 열기`}
      className="-mx-2 flex w-full flex-col items-start gap-1 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
    >
      {body}
    </button>
  )
}
