import { CircleHelpIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { Notice } from '@/components/common/notice'

/**
 * 이름을 못 찾았을 때. 물음표 아이콘으로 "찾지 못했다" 는 사실만 알리고, **비교에 넣지 못하게 한다.**
 *
 * 예전에는 비슷한 이름을 골라 바로 넣을 수 있게 했는데, 없는 이름을 두고 다른 패키지를 권하는 셈이라 뺐다.
 * 1단계(기준 패키지)와 2단계(직접 찾기)가 같은 모양을 쓴다.
 */
export function MissingPackage({ name }: { name: string }) {
  return (
    <Notice
      tone="info"
      icon={CircleHelpIcon}
      title={
        <>
          <span className="font-mono">{name}</span> 라는 패키지를 찾지 못했어요
        </>
      }
    >
      이름을 다시 확인해 주세요. 찾지 못한 패키지는 비교에 넣을 수 없어요.
    </Notice>
  )
}

/**
 * 이름·자료는 있지만 유사 후보(similar_package)가 없을 때. 막지 않고 **한 번 묻는다.**
 * 이런 패키지는 비슷한 후보를 제안할 수 없고, 보고서 일부가 비어 보일 수 있다.
 */
export function NoSimilarWarning({
  name,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  name: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <Notice
      tone="warn"
      title={
        <>
          <span className="font-mono">{name}</span> 는 비교에 쓸 자료가 부족해요
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <span>
          비슷한 패키지 정보가 없어서, 보고서 일부가 비어 보일 수 있어요. 그래도 진행할까요?
        </span>
        <span className="flex flex-wrap gap-2">
          <Button size="sm" onClick={onConfirm}>
            {confirmLabel}
          </Button>
          <Button size="sm" variant="outline" onClick={onCancel}>
            취소
          </Button>
        </span>
      </div>
    </Notice>
  )
}
