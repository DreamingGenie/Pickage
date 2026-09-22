import { InfoIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/**
 * ⓘ 버튼과, 누르면 열리는 설명 모달.
 *
 * 화면에 상시 노출하면 카드가 길어지고 산만해지지만 **없어서도 안 되는** 설명은 이 모달로 옮긴다
 * (S15P21A506-405). 매번 읽어야 하는 경고가 아니라 궁금할 때 찾아보는 설명이어야 한다 — 값을 잘못
 * 읽게 만들 수 있는 한계(실제 설치량이 아님 등)는 이 안에 두되 **제목이나 라벨에서 그 사실을
 * 부정하지 않는다.**
 *
 * `Version Share` 카드가 처음 만들었고(카드 안에 직접 `Dialog` 를 썼다), 같은 모양을 쓰는 곳이 여럿이
 * 되어 공용으로 뺐다. 두 군데서 각자 구현하면 버튼 크기·포커스 링이 갈린다.
 *
 * - `label`: 버튼의 접근성 이름. 스크린리더는 "안내" 라는 말만으로는 무엇에 대한 것인지 모른다.
 * - `title`: 모달 제목.
 * - `children`: 본문. 문단이 여럿이면 여러 개를 넘긴다 — 사이 간격은 여기서 준다.
 * - `contentClassName`: 모달 폭을 넓히는 자리. **기본은 그대로 두었다** — 대부분의 안내는
 *   짧은 문단 두어 개라 좁은 폭이 오히려 읽기 좋다. 표가 들어가는 안내만 넓힌다.
 */
export function InfoDialog({
  label,
  title,
  children,
  className,
  contentClassName,
}: {
  label: string
  title: string
  children: ReactNode
  className?: string
  contentClassName?: string
}) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label={label}
          className={cn(
            'inline-flex shrink-0 rounded-full p-0.5 text-muted-foreground/70 transition-colors outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/40',
            className,
          )}
        >
          <InfoIcon aria-hidden className="size-3.5" />
        </button>
      </DialogTrigger>
      {/*
        `aria-describedby={undefined}`: Radix 는 설명 요소가 없으면 경고한다. 본문이 곧 설명이고 제목 바로
        아래에 이어지므로 따로 "○○ 설명" 을 만들어 스크린리더에 한 번 더 읽히지 않는다.
      */}
      <DialogContent className={cn('sm:max-w-sm', contentClassName)} aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 text-base leading-relaxed text-muted-foreground">
          {children}
        </div>
      </DialogContent>
    </Dialog>
  )
}
