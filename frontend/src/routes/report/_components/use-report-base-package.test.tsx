import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'

import { useReportBasePackage } from '@/routes/report/_components/use-report-base-package'

function wrapperWithState(state: unknown) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter initialEntries={[{ pathname: '/report/draft', state }]}>
        {children}
      </MemoryRouter>
    )
  }
}

describe('useReportBasePackage', () => {
  it('명시 state 가 없으면 packages[0] 으로 대체한다(새로고침·공유 링크 호환)', () => {
    const { result } = renderHook(() => useReportBasePackage(['winston', 'pino']), {
      wrapper: wrapperWithState(null),
    })
    expect(result.current).toEqual({ basePackage: 'winston', conflict: false })
  })

  it('명시 basePackage 가 packages[0] 과 같으면 그대로 쓴다', () => {
    const { result } = renderHook(() => useReportBasePackage(['winston', 'pino']), {
      wrapper: wrapperWithState({ basePackage: 'winston' }),
    })
    expect(result.current).toEqual({ basePackage: 'winston', conflict: false })
  })

  it('명시 basePackage 가 packages[0] 과 다르면 임의로 고치지 않고 충돌로 표시한다', () => {
    const { result } = renderHook(() => useReportBasePackage(['pino', 'winston']), {
      wrapper: wrapperWithState({ basePackage: 'winston' }),
    })
    expect(result.current).toEqual({ basePackage: null, conflict: true })
  })

  it('packages 가 비어 있고 명시 state 도 없으면 문맥 없음(null, 충돌 아님)이다', () => {
    const { result } = renderHook(() => useReportBasePackage([]), {
      wrapper: wrapperWithState(null),
    })
    expect(result.current).toEqual({ basePackage: null, conflict: false })
  })
})
