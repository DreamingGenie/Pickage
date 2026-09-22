import { Outlet, useNavigation } from 'react-router'

import { Header } from '@/components/common/header'
import { cn } from '@/lib/utils'

export function AppLayout() {
  const navigation = useNavigation()
  const isPending = navigation.state === 'loading'

  return (
    // overflow-x-clip: 전폭 히어로(`w-screen`)는 세로 스크롤바 폭만큼 뷰포트보다 넓다. 그 넘침이
    // 가로 스크롤을 만들지 않게 자른다. clip 은 스크롤 컨테이너를 만들지 않아 sticky 에 영향이 없다.
    // bg-canvas: 페이지 바탕은 옅은 회색, 카드는 흰색이라 한 덩어리씩 떠 보인다.
    <div className="min-h-svh overflow-x-clip bg-canvas">
      {/* 라우트 청크를 받는 동안의 대기 표시. 화면 전체를 스켈레톤으로 덮지 않는다. */}
      <div
        aria-hidden
        className={cn(
          'fixed inset-x-0 top-0 z-50 h-0.5 origin-left bg-primary transition-transform duration-300',
          isPending ? 'scale-x-100' : 'scale-x-0',
        )}
      />
      <Header />
      <main
        className={cn(
          'mx-auto w-full max-w-[1440px] px-10 py-8 transition-opacity',
          isPending && 'opacity-60',
        )}
      >
        <Outlet />
      </main>
    </div>
  )
}
