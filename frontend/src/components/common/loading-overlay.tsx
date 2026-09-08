import { useEffect, useState } from 'react'

import { LogoMark } from '@/components/common/logo'
import { cn } from '@/lib/utils'

/**
 * 화면 전체를 덮는 대기 오버레이.
 *
 * 보고서를 만드는 동안처럼 사용자가 다른 조작을 하면 안 되는 구간에만 쓴다.
 * 이미 결과가 있는 자리(재분석 등)에는 쓰지 않는다 — 그쪽은 기존 결과를 덮지 않고
 * 상태 카드만 얹는 게 맞다(IA 9.4).
 */
export function LoadingOverlay({
  open,
  title,
  steps,
  className,
}: {
  open: boolean
  title: string
  /** 무엇을 하고 있는지 차례로 보여줄 문구. 없으면 제목만 뜬다. */
  steps?: readonly string[]
  className?: string
}) {
  const [i, setI] = useState(0)

  useEffect(() => {
    if (!open || !steps || steps.length < 2) return
    setI(0)
    const id = window.setInterval(() => {
      setI((n) => (n + 1 < steps.length ? n + 1 : n))
    }, 900)
    return () => clearInterval(id)
  }, [open, steps])

  if (!open) return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy
      className={cn(
        'fixed inset-0 z-50 grid place-items-center bg-background/70 backdrop-blur-[3px]',
        'animate-oss-rise',
        className,
      )}
    >
      <div className="flex w-[min(360px,calc(100vw-2.5rem))] flex-col items-center gap-5 rounded-2xl border bg-background px-8 py-9 text-center shadow-[0_16px_48px_-24px_rgba(15,23,42,0.5)]">
        {/* 로고 마크가 도는 게 스피너 역할을 한다 */}
        <LogoMark className="size-9 [animation-duration:2.4s] [animation-timing-function:linear] motion-safe:animate-spin" />

        <div className="flex flex-col gap-1.5">
          <p className="text-[15px] font-semibold">{title}</p>
          {steps && steps.length > 0 && (
            <p className="min-h-[20px] text-[13px] text-muted-foreground">{steps[i]}</p>
          )}
        </div>

        {steps && steps.length > 1 && (
          <div className="flex gap-1.5" aria-hidden>
            {steps.map((s, n) => (
              <span
                key={s}
                className={cn(
                  'h-1 rounded-full transition-all duration-300',
                  n <= i ? 'w-5 bg-foreground' : 'w-2 bg-border',
                )}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
