import type { TextMark } from '@/api/types'
import { segmentText } from '@/lib/text-marks'

/**
 * 본문을 읽기 쉽게 핵심어는 굵게, 핵심 문장은 형광펜으로 그린다(S15P21A506-409, S15P21A506-470 에서 공용화).
 *
 * 강조는 **읽기 보조**다 — 구간이 없거나 어긋나면 그 부분은 평문으로 보이고 글 자체는 그대로 읽힌다. 뜻은 굵기(모양)와
 * 배경(명도)이 각각 다르게 전한다. 형광펜은 `<mark>` 라 보조기기도 "강조된 글"임을 안다.
 *
 * `box-decoration-clone`: 형광펜이 줄 끝에서 꺾여도 한 덩어리처럼 이어져 보인다. 가로 패딩은 주지 않는다 — 핵심 문장 안에
 * 핵심어가 끼면 조각이 여럿이 되는데, 조각마다 패딩이 있으면 글자 사이가 벌어져 보인다.
 */
export function EmphasizedText({
  text,
  marks,
}: {
  text: string
  marks: readonly TextMark[] | null | undefined
}) {
  const segments = segmentText(text, marks)
  return (
    <>
      {segments.map((seg, i) => {
        let node: React.ReactNode = seg.text
        if (seg.term) node = <strong className="font-bold text-foreground">{node}</strong>
        if (seg.sentence) {
          node = (
            <mark className="bg-amber-200/70 [box-decoration-break:clone] text-foreground">
              {node}
            </mark>
          )
        }
        return <span key={i}>{node}</span>
      })}
    </>
  )
}
