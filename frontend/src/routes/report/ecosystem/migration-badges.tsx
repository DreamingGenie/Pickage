import type { ReactNode } from 'react'

import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  EVIDENCE_HINT,
  EVIDENCE_LABEL,
  VARIANT_HINT,
  VARIANT_LABEL,
  type MigrationEvidence,
} from '@/routes/report/ecosystem/migration-model'
import { cn } from '@/lib/utils'

/**
 * 교체 흐름 배지 둘 (S15P21A506-424).
 *
 * 패널(비교 패키지끼리의 이동 줄)과 막대(도착지 줄) **두 곳에 같은 배지가 뜬다.** 각자
 * 만들면 툴팁 문장이나 강조 규칙이 갈라지는데, 그 차이는 "같은 배지가 자리에 따라 다른
 * 뜻으로 보인다" 로 나타나서 눈으로 잡기 어렵다. 그래서 한 파일에 둔다.
 *
 * `components/charts` 가 아니라 여기 있는 이유는 이 배지가 그림이 아니라 **이 지표의
 * 용어**이기 때문이다 — 문장이 {@link EVIDENCE_HINT} 와 묶여 있어 모델 옆이 제자리다.
 * (형제 차트도 이미 이 폴더의 모델을 가져다 쓴다.)
 */

/**
 * 배지 + 설명 말풍선.
 *
 * <b>브라우저 기본 `title` 속성을 쓰지 않는다.</b> 처음에는 그것으로 뒀는데 커서만
 * 물음표로 바뀌고 말풍선이 뜨지 않는 일이 잦았다 — 기본 툴팁은 1초 넘게 가만히 있어야
 * 뜨고, 마우스가 조금만 움직여도 취소되며, 키보드 포커스로는 아예 뜨지 않는다. 설명을
 * 달아 놓고 읽히지 않으면 배지는 여전히 "서비스가 임의로 매긴 점수" 다.
 *
 * 대신 디자인 시스템의 `Tooltip`(Radix)을 쓴다. `delayDuration` 이 0 이라 바로 뜨고,
 * 트리거에 포커스가 가면 키보드로도 열린다.
 */
function Badge({
  hint,
  children,
  className,
}: {
  hint: string
  children: ReactNode
  className?: string
}) {
  return (
    <Tooltip>
      {/*
        `tabIndex={0}` — 배지는 버튼이 아니라 글자라서 기본으로는 포커스를 받지 못한다.
        그러면 키보드만 쓰는 사람에게는 설명이 없는 것과 같다.
      */}
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          className={cn(
            'shrink-0 cursor-help rounded px-1 text-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40',
            className,
          )}
        >
          {children}
        </span>
      </TooltipTrigger>
      {/* 기본 폭은 한 줄짜리 말풍선용이라 이 문장들에는 좁다. */}
      <TooltipContent className="max-w-72 text-xs leading-relaxed">{hint}</TooltipContent>
    </Tooltip>
  )
}

/**
 * 근거 배지. **말풍선에 판정 기준을 싣는다.**
 *
 * 낱말만 떠 있으면 서비스가 임의로 매긴 점수처럼 읽힌다. 실제로는 계산 파이프라인이 원래
 * 쓰던 고정 문턱이고, 그 문턱을 사람 말로 적은 것이 말풍선이다. 모달의 풀이표도 같은
 * 상수를 읽으므로 두 설명이 갈라질 수 없다.
 */
export function EvidenceBadge({
  evidence,
  className,
}: {
  evidence: MigrationEvidence
  className?: string
}) {
  return (
    <Badge
      hint={EVIDENCE_HINT[evidence]}
      className={cn(
        evidence === 'strict' ? 'bg-foreground/10 text-foreground' : 'text-muted-foreground',
        className,
      )}
    >
      {EVIDENCE_LABEL[evidence]}
    </Badge>
  )
}

/**
 * "양방향" 배지 — 반대 방향 이동도 관측된 쌍.
 *
 * **지우지 않고 표시만 다르게 한다**(S15P21A506-211 결정 4 ③). 다만 이름은 "변종" 이
 * 아니다 — 상위 5 자리의 38.2%가 이 플래그를 달아서, 단정하면 대부분 거짓이 된다
 * ({@link VARIANT_LABEL} 주석의 실측).
 */
export function VariantBadge({ className }: { className?: string }) {
  return (
    <Badge hint={VARIANT_HINT} className={cn('border text-muted-foreground', className)}>
      {VARIANT_LABEL}
    </Badge>
  )
}
