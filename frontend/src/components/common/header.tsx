import { Link, NavLink } from 'react-router'

import { paths } from '@/app/routes'
import { Logo } from '@/components/common/logo'
import { cn } from '@/lib/utils'

/**
 * 공통 헤더.
 *
 * IA 3.1 의 상단 메뉴 두 개만 둔다 — 화면 표기는 `Intro` / `Analyze`(서비스 소개 / 패키지 분석). 보고서는 최상위 메뉴가 아니다.
 * 예전에는 메뉴를 걷어내고 로고만 뒀는데, 처음 온 사람이 "여기서 무엇을 할 수 있는지"를
 * 찾을 곳이 없다는 의견이 많아 되살렸다. 지금 있는 화면은 `aria-current` 와 밑줄로 함께 알린다
 * — 색만으로 알리지 않는다(IA 1-13).
 */
const NAV = [
  { to: paths.intro, label: 'Intro', end: true },
  { to: paths.analyze, label: 'Analyze', end: false },
] as const

export function Header() {
  return (
    <header className="border-b bg-background">
      <div className="mx-auto flex h-20 w-full max-w-[1440px] items-center justify-between gap-6 px-10">
        <Link to={paths.intro} aria-label="Pickage 홈">
          <Logo />
        </Link>
        <nav aria-label="주요 메뉴" className="flex h-full items-stretch gap-7">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'flex items-center border-b-2 border-transparent text-lg transition-colors outline-none focus-visible:text-primary',
                  isActive
                    ? 'border-foreground font-semibold text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  )
}
