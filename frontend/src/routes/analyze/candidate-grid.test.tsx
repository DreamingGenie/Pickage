import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { SimilarCandidate } from '@/api/types'

import { CandidateGrid } from '@/routes/analyze/candidate-grid'

/**
 * S15P21A506-437: 이름이 긴 후보가 카드 박스 밖으로 넘쳤다. 실제 넘침 여부는 jsdom 이 계산하지
 * 못해 화면으로 확인하고, 여기서는 "줄여서 보여주고 전체 이름은 따로 확인할 수 있다"는 계약만 본다.
 */

afterEach(cleanup)

const LONG_NAME = '@some-org/an-extremely-long-scoped-package-name-that-does-not-fit-in-the-card'

const candidate: SimilarCandidate = {
  rank: 1,
  score: 0.9,
  name: LONG_NAME,
  latest_version: '1.0.0',
  description: '설명',
}

describe('CandidateGrid', () => {
  it('긴 이름을 줄임 처리하고 title 속성으로 전체 이름을 남긴다', () => {
    render(<CandidateGrid candidates={[candidate]} picked={[]} onToggle={() => {}} />)

    const nameEl = screen.getByText(LONG_NAME)
    expect(nameEl).toHaveClass('truncate')
    expect(nameEl).toHaveAttribute('title', LONG_NAME)
  })
})
