import { useState } from 'react'
import { ChevronDownIcon } from 'lucide-react'

import { InfoDialog } from '@/components/common/info-dialog'
import { cn } from '@/lib/utils'
import {
  cellReason,
  type ComparisonView,
  type FeatureCell,
  type FeatureRow,
} from '@/routes/report/features/model'
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
 *
 * **설명 펼치기/접기 (S15P21A506-465).** 뱃지(판정·일반 지식)는 항상 보이고, 설명 문단
 * (`note`·미확인 사유)은 기본적으로 접혀 있다 — 실제 화면은 칸마다 문단이 늘 펼쳐져 있어
 * 표가 길고 읽기 피곤했다. **칸 자체는 여전히 버튼이 아니다** — 위 기획 협의를 다시 뒤집는
 * 게 아니라, 기능명(행 머리글)을 눌러 그 행의 설명만 한꺼번에 펼친다. 새 정보(출처·근거 ID)
 * 를 추가하는 것도 아니라 이미 있던 문단을 숨겼다 보여줄 뿐이다. PDF(`ReportHtmlRenderer`)
 * 는 이 컴포넌트와 무관한 별도 렌더러라 여기 상태와 상관없이 항상 설명을 전부 싣는다.
 *
 * **가시성·정렬 보완 (QA 피드백, S15P21A506-465 후속).**
 * - 기능명은 글이 줄어든 만큼 눈에 먼저 띄어야 한다 — 본문과 같은 굵기·색(`text-foreground
 *   font-medium`)으로 올렸다. 기능명 자체는 평문이다 — 펼치기는 옆의 **별도 아이콘 버튼**이
 *   맡는다(처음엔 기능명 전체를 버튼으로 감쌌으나, 클릭 영역이 넓어 오해를 줘서 분리했다).
 *   그 버튼은 `outline` 버튼(`components/ui/button.tsx`)과 같은 테두리·배경으로 "눌리는
 *   것"임을 확실히 드러낸다.
 * - 미확인/미지원 정의는 매번 읽는 경고가 아니라 궁금할 때 찾아보는 설명이라 `InfoDialog`
 *   (다른 카드들과 같은 ⓘ 모달, `components/common/info-dialog.tsx`)로 옮겼다 — 본문에
 *   상시 노출하지 않는다. 모달 안에 "기능명을 누르면 펼쳐진다"는 안내도 함께 둔다.
 * - 표에 `table-layout: fixed` + `colgroup` 을 줬다. 기본값(auto)에서는 브라우저가 **모든
 *   행의 내용을 보고** 열 너비를 다시 계산한다 — 한 행만 펼쳐 설명 문단이 길어져도 전체 열이
 *   흔들렸다(스크린샷으로 확인된 버그). 열 너비를 고정하면 어떤 셀이 펼쳐져도 정렬이 안 움직인다.
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
  const [expandedRows, setExpandedRows] = useState<ReadonlySet<string>>(() => new Set())
  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

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
          <InfoDialog
            label="핵심 기능 비교 안내"
            title="핵심 기능 비교 안내"
            className="self-center"
          >
            <p>
              <strong className="font-medium text-foreground">미확인</strong>은 &lsquo;기능이
              없다&rsquo;가 아니라 README 에서 찾지 못했다는 뜻입니다.{' '}
              <strong className="font-medium text-foreground">미지원</strong>은 README 에 지원하지
              않는다고 적혀 있을 때만 씁니다.
            </p>
            <p>테두리가 있는 기능명을 누르면 그 기능의 자세한 판정 근거를 펼쳐 볼 수 있습니다.</p>
          </InfoDialog>
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
          <table className="w-full min-w-[560px] table-fixed text-base">
            {/*
              고정 열 너비 — 어떤 행이 펼쳐져도(설명 문단 길이가 달라져도) 열이 움직이지
              않는다. 기능명 열만 너비를 주고 패키지 열은 나머지를 똑같이 나눠 갖는다.
            */}
            <colgroup>
              <col className="w-40 sm:w-56" />
              {view.packages.map((pkg) => (
                <col key={pkg.name} />
              ))}
            </colgroup>
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
              {view.rows.map((row) => {
                const hasDetail = rowHasDetail(row)
                const expanded = hasDetail && expandedRows.has(row.id)
                return (
                  <tr key={row.id} className="border-t align-top">
                    <th scope="row" className="py-3 pr-3 text-left align-top font-normal">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-foreground">{row.label}</span>
                        {hasDetail && (
                          <button
                            type="button"
                            aria-expanded={expanded}
                            onClick={() => toggleRow(row.id)}
                            className="inline-flex shrink-0 items-center justify-center rounded-md border bg-background p-1 text-muted-foreground shadow-xs transition-colors outline-none hover:bg-accent hover:text-accent-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                          >
                            <ChevronDownIcon
                              aria-hidden
                              className={cn(
                                'size-3.5 transition-transform duration-200',
                                expanded && 'rotate-180',
                              )}
                            />
                            <span className="sr-only">
                              {row.label} {expanded ? '설명 접기' : '설명 펼치기'}
                            </span>
                          </button>
                        )}
                      </div>
                    </th>
                    {row.cells.map((cell) => (
                      <td key={cell.packageName} className="py-3 pr-3 align-top">
                        <Cell cell={cell} expanded={expanded} />
                      </td>
                    ))}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

/** 행에 펼칠 설명(`note` 또는 미확인 사유)이 하나라도 있는지 — 없으면 토글을 두지 않는다. */
function rowHasDetail(row: FeatureRow): boolean {
  return row.cells.some((cell) => cell.note || cellReason(cell))
}

function Cell({ cell, expanded }: { cell: FeatureCell; expanded: boolean }) {
  const reason = cellReason(cell)
  return (
    // items-center — 뱃지가 넓은 열 왼쪽에만 붙어 있으면 어색하다(QA 피드백). 펼친 설명
    // 문단은 열 폭을 거의 채우므로 가운데 정렬이어도 줄글이 어색해 보이지 않는다.
    <div className="flex flex-col items-center gap-1">
      <div className="flex flex-wrap items-center gap-1.5">
        <VerdictPill verdict={cell.verdict} />
        {cell.generalKnowledge && (
          <span
            title="README 에서 확인한 것이 아니라 AI 의 일반 지식으로 판단했습니다"
            className="rounded border px-1 py-px text-xs text-muted-foreground"
          >
            AI 일반 지식
          </span>
        )}
      </div>
      {expanded && cell.note && (
        <span className="text-sm leading-snug text-muted-foreground">{cell.note}</span>
      )}
      {expanded && reason && (
        <span className="text-sm leading-snug text-muted-foreground">{reason}</span>
      )}
    </div>
  )
}
