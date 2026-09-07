import { Outlet, useNavigation } from 'react-router'

import { Header } from '@/components/common/header'
import { cn } from '@/lib/utils'

export function AppLayout() {
  const navigation = useNavigation()
  const isPending = navigation.state === 'loading'

  return (
    <div className="min-h-svh bg-background">
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
