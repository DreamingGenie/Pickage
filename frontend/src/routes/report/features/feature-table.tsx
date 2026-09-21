import { cn } from '@/lib/utils'
import { cellReason, type ComparisonView, type FeatureCell } from '@/routes/report/features/model'
import { VerdictPill } from '@/routes/report/features/verdict-pill'

/**
 * 핵심 기능 비교표 (IA §9.2).
 *
 * 칸에는 **판정과 한 줄 설명**만 둔다. 출처 표기와 근거 Drawer 는 뺐다(기획 협의) — 칸마다
 * 출처가 붙으면 표가 난잡해져 판정이 안 읽힌다. 미확인 칸에는 **왜 미확인인지**를 글자로
 * 적는다(색만으로 구분하지 않는다).
 *
 * README 가 아니라 AI 의 일반 지식으로 답한 칸만 `일반 지식` 태그를 붙인다. 출처를 안 적어도
 * 이 구분은 남겨야 한다 — 확인한 판정과 짐작한 판정이 똑같아 보이면 안 된다.
 */
export function FeatureTable({
  view,
  dimmed,
}: {
  view: ComparisonView
  /** 재분석 중 — 이전 결과를 그대로 두되 흐리게 */
  dimmed: boolean
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
                    <td key={cell.packageName} className="py-3 pr-3">
                      <Cell cell={cell} />
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

function Cell({ cell }: { cell: FeatureCell }) {
  const reason = cellReason(cell)
  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <VerdictPill verdict={cell.verdict} />
        {cell.generalKnowledge && (
          <span
            title="README 에서 확인한 것이 아니라 AI 의 일반 지식으로 판단했습니다"
            className="rounded border px-1 py-px text-xs text-muted-foreground"
          >
            일반 지식
          </span>
        )}
      </div>
      {cell.note && <span className="text-sm leading-snug text-muted-foreground">{cell.note}</span>}
      {reason && <span className="text-sm leading-snug text-muted-foreground">{reason}</span>}
    </div>
  )
}
