import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { CommunityLimitation, CommunityResult } from '@/api/types'
import { CommunityResultView } from '@/routes/report/community/result'
import { SAMPLE_COMMUNITY_RESULT } from '@/routes/report/community/sample'

/**
 * GitHub 커뮤니티 결과 화면(S15P21A506-406): 중복 정보 제거와 설명 문구의 모달 이전.
 *
 * 지키는 것은 두 가지다. ① 같은 사실을 두 번 말하지 않는다(요약과 겹치는 논의 흐름, 배지와 겹치는 수집
 * 한계 문구). ② 그렇다고 **한계 자체를 잃지 않는다** — 불완전 수집을 완전한 논의로 오해하게 하면 안 되므로
 * 모달을 열면 남은 한계가 전부 있어야 한다(요구사항 확장-03-R12·R16).
 */

// vitest 전역을 켜지 않아 RTL 이 자동 정리하지 않는다.
afterEach(cleanup)

const limitation = (
  code: CommunityLimitation['code'],
  message: string,
  issue_number: number | null,
): CommunityLimitation => ({ code, message, issue_number })

/** 논의 흐름이 있고, 댓글이 일부만 수집됐고, 요약 입력이 잘린 Issue 하나가 든 결과. */
function resultWith(overrides: Partial<CommunityResult> = {}): CommunityResult {
  const topic = SAMPLE_COMMUNITY_RESULT.topics[0]
  return {
    ...SAMPLE_COMMUNITY_RESULT,
    topics: [
      {
        ...topic,
        collection_status: 'TRUNCATED',
        flow: [
          { text: '첫째 단계 문장이다.' },
          { text: '둘째 단계 문장이다.' },
          { text: '셋째 단계 문장이다.' },
        ],
      },
    ],
    limitations: [
      limitation(
        'ROOT_PACKAGE_SCOPE_HEURISTIC',
        '루트 package.json 연결에 기반한 패키지 범위 추정입니다.',
        null,
      ),
      limitation('ISSUE_FILTERED', '수집 범위에 포함되지 않는 이슈를 제외했습니다.', null),
      limitation('COMMENTS_TRUNCATED', '댓글 일부만 수집했습니다.', topic.issue_number),
      limitation(
        'SUMMARY_INPUT_LIMITED',
        '입력 한도로 원문 일부만 요약에 사용했습니다.',
        topic.issue_number,
      ),
    ],
    ...overrides,
  }
}

function renderView(result: CommunityResult) {
  return render(<CommunityResultView result={result} freshness="FRESH" />)
}

describe('중복 정보 제거', () => {
  it('요약과 같은 내용을 되풀이하는 논의 흐름 단계 목록을 그리지 않는다', () => {
    const { container } = renderView(resultWith())

    expect(container.textContent).not.toContain('첫째 단계 문장이다.')
    expect(container.textContent).not.toContain('둘째 단계 문장이다.')
    expect(container.querySelector('ol')).toBeNull()
    // 요약과 대표 발화는 그대로 있다.
    expect(container.textContent).toContain(resultWith().topics[0].summary_ko)
    expect(container.textContent).toContain(resultWith().topics[0].messages[0].text)
  })

  it('배지가 이미 말하는 "댓글 일부만 수집했습니다." 문구는 다시 쓰지 않는다', () => {
    renderView(resultWith())

    // 배지(수집 상태)는 남는다.
    expect(screen.getByText('댓글 일부만 수집')).toBeInTheDocument()
    // 같은 뜻의 문장은 어디에도 없다 — 모달을 열기 전에도, 열어도 없다.
    expect(screen.queryByText('댓글 일부만 수집했습니다.')).toBeNull()
  })

  it('댓글 수집 실패 배지와 같은 뜻의 문구("댓글을 확인하지 못했습니다.")도 쓰지 않는다', async () => {
    const user = userEvent.setup()
    const base = resultWith()
    const topic = { ...base.topics[0], collection_status: 'FAILED' as const }
    renderView({
      ...base,
      topics: [topic],
      limitations: [
        limitation('COMMENTS_UNAVAILABLE', '댓글을 확인하지 못했습니다.', topic.issue_number),
      ],
    })

    expect(screen.getByText('댓글 수집 실패')).toBeInTheDocument()
    expect(screen.queryByText('댓글을 확인하지 못했습니다.')).toBeNull()
    // 남는 한계가 없으면 이 Issue 에는 ⓘ 도 없다 — 열어 볼 것이 없는 버튼을 두지 않는다.
    expect(screen.queryByRole('button', { name: `#${topic.issue_number} 요약 안내` })).toBeNull()
    await user.click(screen.getByRole('button', { name: '수집 기준 안내' })) // 저장소 ⓘ 는 그대로 있다
    expect(await screen.findByRole('dialog', { name: '수집 기준과 한계' })).toBeInTheDocument()
  })
})

describe('설명 문구의 모달 이전', () => {
  it('저장소 한계·수집 기준·요약 입력 한도는 화면에 상시 노출하지 않는다', () => {
    const { container } = renderView(resultWith())
    const text = container.textContent ?? ''

    expect(text).not.toContain('루트 package.json 연결에 기반한 패키지 범위 추정입니다.')
    expect(text).not.toContain('수집 범위에 포함되지 않는 이슈를 제외했습니다.')
    expect(text).not.toContain('입력 한도로 원문 일부만 요약에 사용했습니다.')
    expect(text).not.toContain(SAMPLE_COMMUNITY_RESULT.data_limits.source_note)
    expect(text).not.toContain('lookback') // 개발자 표기 각주
  })

  it('수집 기준 ⓘ 를 열면 저장소 한계와 수집 기준이 모두 들어 있다', async () => {
    const user = userEvent.setup()
    renderView(resultWith())

    await user.click(screen.getByRole('button', { name: '수집 기준 안내' }))

    const dialog = await screen.findByRole('dialog', { name: '수집 기준과 한계' })
    expect(dialog).toHaveTextContent('루트 package.json 연결에 기반한 패키지 범위 추정입니다.')
    expect(dialog).toHaveTextContent('수집 범위에 포함되지 않는 이슈를 제외했습니다.')
    expect(dialog).toHaveTextContent(SAMPLE_COMMUNITY_RESULT.data_limits.source_note)
    // 조회 기간은 응답 값이다. 이슈·댓글 상한은 source_note 가 이미 말하므로 같은 숫자를 두 번 적지 않는다.
    expect(dialog).toHaveTextContent('조회 기간은 최근 180일입니다.')
    expect(dialog).not.toHaveTextContent('Issue는 최대')
    // Issue 하나에 붙는 한계는 저장소 모달이 아니라 그 카드의 ⓘ 가 낸다.
    expect(dialog).not.toHaveTextContent('입력 한도로 원문 일부만')
  })

  it('Issue 의 요약 안내 ⓘ 를 열면 요약 입력 한도가 있고, 배지와 겹치는 문구는 없다', async () => {
    const user = userEvent.setup()
    const issueNumber = SAMPLE_COMMUNITY_RESULT.topics[0].issue_number
    renderView(resultWith())

    await user.click(screen.getByRole('button', { name: `#${issueNumber} 요약 안내` }))

    const dialog = await screen.findByRole('dialog', { name: '요약 안내' })
    expect(
      within(dialog).getByText('입력 한도로 원문 일부만 요약에 사용했습니다.'),
    ).toBeInTheDocument()
    expect(dialog).not.toHaveTextContent('댓글 일부만 수집했습니다.')
  })

  it('한계가 하나도 없는 Issue 에는 요약 안내 ⓘ 를 두지 않는다', () => {
    renderView({ ...SAMPLE_COMMUNITY_RESULT, limitations: [] })

    expect(screen.queryByRole('button', { name: /요약 안내/ })).toBeNull()
    // 저장소 ⓘ 는 수집 기준 때문에 항상 있다.
    expect(screen.getByRole('button', { name: '수집 기준 안내' })).toBeInTheDocument()
  })

  it('저장소를 확인하지 못한 터미널 상태에서도 수집 기준을 볼 수 있다', () => {
    renderView({
      ...SAMPLE_COMMUNITY_RESULT,
      data_status: 'UNVERIFIED_REPOSITORY',
      repository: null,
      topics: [],
      limitations: [],
    })

    expect(screen.getByText('공개 저장소 연결을 확인하지 못했습니다.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '수집 기준 안내' })).toBeInTheDocument()
  })
})
