import * as React from 'react'

import { TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

/**
 * 밑줄 방식 탭. 보고서 상단 탭(`report-page.tsx`)이 쓴다.
 *
 * `components/ui/tabs.tsx` 는 shadcn 원본이라 고치지 않고, 같은 Radix 탭 위에 스타일만
 * 덮어 감싼다 — 키보드 이동(←/→·Home/End)과 `role="tab"` 시맨틱은 그대로 따라온다.
 * `Tabs`·`TabsContent` 는 원본을 그대로 쓴다.
 *
 * 활성 표시는 밑줄이 **굵기·색·글자 굵기**로 함께 말한다(색만으로 전달하지 않는다).
 * 밑줄은 목록 경계 **안쪽**에 둔다. 구분선에 겹치도록 밖으로 1px 내밀면 `overflow-x-auto`
 * 가 세로 스크롤까지 만든다.
 */
export function UnderlineTabsList({ className, ...props }: React.ComponentProps<typeof TabsList>) {
  return (
    <TabsList
      className={cn(
        // 좁은 화면에서 탭이 넘치면 줄바꿈 대신 가로로 민다
        'h-auto w-full justify-start gap-6 overflow-x-auto overflow-y-hidden rounded-none border-b bg-transparent p-0 sm:gap-8',
        className,
      )}
      {...props}
    />
  )
}

export function UnderlineTabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsTrigger>) {
  return (
    <TabsTrigger
      className={cn(
        'relative h-auto flex-none rounded-none border-0 px-0.5 pt-2 pb-3 text-lg font-medium text-muted-foreground shadow-none transition-colors',
        'hover:text-foreground focus-visible:rounded-sm focus-visible:ring-2',
        'data-[state=active]:bg-transparent data-[state=active]:font-semibold data-[state=active]:text-foreground data-[state=active]:shadow-none',
        // 밑줄. 비활성일 때는 투명이라 자리만 잡고 레이아웃이 움직이지 않는다
        'after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-transparent data-[state=active]:after:bg-foreground',
        className,
      )}
      {...props}
    />
  )
}
