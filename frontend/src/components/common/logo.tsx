import { cn } from '@/lib/utils'

/**
 * 로고. 원본 아트워크를 그대로 쓴다.
 *
 * `public/logo-mark.png`      큐브 (favicon.png 원본에서 흰 배경을 지우고 정사각 캔버스로)
 * `public/logo-wordmark.png`  Pickage 글자 (wordart.jpg 에서 태그라인 제외)
 *
 * 라스터라 색을 바꿀 수 없다. 어두운 배경에 얹어야 하면 반전 버전을 따로 만들어야 한다.
 * 태그라인(SMART NPM PACKAGE SELECTOR)은 화면에 쓰지 않는다 —
 * "SELECTOR" 가 서비스가 골라 준다는 뜻으로 읽혀 IA 1.10 과 부딪힌다.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <img
      src="/logo-mark.png"
      alt=""
      width={512}
      height={512}
      className={cn('size-6 object-contain', className)}
    />
  )
}

/** 헤더용 마크 + 워드마크. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn('flex items-center gap-2.5', className)}>
      <LogoMark className="size-7" />
      <img
        src="/logo-wordmark.png"
        alt="Pickage"
        width={600}
        height={158}
        className="h-[19px] w-auto object-contain"
      />
    </span>
  )
}
