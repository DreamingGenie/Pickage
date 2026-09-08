import { Link } from 'react-router'

import { paths } from '@/app/routes'
import { Logo } from '@/components/common/logo'

/**
 * 공통 헤더.
 *
 * IA 3.1 은 상단 메뉴로 `서비스 소개` / `패키지 분석` 두 개를 두지만 지금은 걷어냈다.
 * 화면이 다섯뿐이고 흐름이 한 줄이라, 메뉴가 오히려 어디에 있는지 흐린다.
 * 이동은 로고(→ 서비스 소개)와 각 화면의 행동 버튼이 맡는다.
 */
export function Header() {
  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center px-10">
        <Link to={paths.intro} aria-label="Pickage 홈">
          <Logo />
        </Link>
      </div>
    </header>
  )
}
