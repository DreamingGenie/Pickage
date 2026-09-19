import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import type { CommunityLimitation, CommunityMessage, CommunityResult } from '@/api/types'
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

/**
 * 와이어프레임 형태(S15P21A506-407): 요약 수치 · 핵심 논의 · 실제 논의 흐름, 그리고 운영 측 발화는 오른쪽.
 */
describe('와이어프레임 구성', () => {
  const message = (
    author_login: string,
    role: CommunityMessage['role'],
    kind: CommunityMessage['kind'],
  ): CommunityMessage => ({
    author_login,
    role,
    kind,
    created_at: '2026-04-03T20:13:21Z', // 한국 시간으로는 다음 날 05:13
    text: `${author_login} 의 발화다.`,
  })

  function resultWithMessages(): CommunityResult {
    const topic = SAMPLE_COMMUNITY_RESULT.topics[0]
    return {
      ...SAMPLE_COMMUNITY_RESULT,
      topics: [
        {
          ...topic,
          messages: [
            message('asker', 'ISSUE_AUTHOR', 'DISCUSSION'),
            message('maint', 'COLLABORATOR', 'USER_SOLUTION'),
            message('member', 'ORGANIZATION_MEMBER', 'DISCUSSION'),
            message('owner', 'REPOSITORY_OWNER', 'DISCUSSION'),
            message('helper', 'CONTRIBUTOR', 'DISCUSSION'),
            message('anon', null, 'DISCUSSION'),
          ],
        },
      ],
    }
  }

  const side = (login: string) => screen.getByText(login).closest('li')?.getAttribute('data-side')

  it('패키지를 운영하는 쪽(협업자·조직 구성원·저장소 소유자)의 발화는 오른쪽, 나머지는 왼쪽이다', () => {
    render(<CommunityResultView result={resultWithMessages()} freshness="FRESH" />)

    expect(side('maint')).toBe('right')
    expect(side('member')).toBe('right')
    expect(side('owner')).toBe('right')
    expect(side('asker')).toBe('left')
    expect(side('helper')).toBe('left')
    expect(side('anon')).toBe('left')
  })

  it('오른쪽 발화도 운영 측임을 역할 글자로 말한다 — 위치만으로 전달하지 않는다', () => {
    render(<CommunityResultView result={resultWithMessages()} freshness="FRESH" />)

    expect(screen.getByText('협업자')).toBeInTheDocument()
    expect(screen.getByText('조직 구성원')).toBeInTheDocument()
    expect(screen.getByText('저장소 소유자')).toBeInTheDocument()
  })

  it('"해결 방법 제시"만 표시하고, 평범한 논의에는 라벨을 달지 않는다', () => {
    render(<CommunityResultView result={resultWithMessages()} freshness="FRESH" />)

    expect(screen.getAllByText('해결 방법 제시')).toHaveLength(1)
    expect(screen.queryByText('논의')).toBeNull()
  })

  it('발화 날짜는 한국 시간 기준이다', () => {
    render(<CommunityResultView result={resultWithMessages()} freshness="FRESH" />)

    expect(screen.getAllByText('2026-04-04').length).toBeGreaterThan(0)
    expect(screen.queryByText('2026-04-03')).toBeNull()
  })

  it('요약 수치 4칸을 응답 값으로 채운다', () => {
    render(<CommunityResultView result={SAMPLE_COMMUNITY_RESULT} freshness="FRESH" />)
    const s = SAMPLE_COMMUNITY_RESULT.summary
    // 수치는 라벨과 같은 칸에 있다. (같은 "1건" 이 두 칸에 나올 수 있어 칸 단위로 본다)
    const cell = (label: string) => screen.getByText(label).parentElement

    expect(cell('분석 Issue')).toHaveTextContent(`${s.issue_count}건`)
    expect(cell('누적 댓글')).toHaveTextContent(`${s.comment_count}개`)
    expect(cell('사용자 반응')).toHaveTextContent(`${s.reaction_count}개`)
    expect(cell('사용자 반응')).toHaveTextContent('GitHub 반응 합계')
    expect(cell('열린 Issue')).toHaveTextContent(`${s.open_issue_count}건`)
  })

  it('열린 Issue 가 없으면 "지금 이어지는" 같은 말을 하지 않고 종료라고 적는다', () => {
    const topic = { ...SAMPLE_COMMUNITY_RESULT.topics[0], state: 'CLOSED' as const }
    const { container } = render(
      <CommunityResultView
        result={{
          ...SAMPLE_COMMUNITY_RESULT,
          summary: { ...SAMPLE_COMMUNITY_RESULT.summary, open_issue_count: 0 },
          topics: [topic],
        }}
        freshness="FRESH"
      />,
    )

    expect(screen.getByText('분석한 Issue 모두 종료')).toBeInTheDocument()
    expect(container.textContent).toContain('· 종료 ·')
    expect(container.textContent).not.toContain('지금 이어지는')
  })

  it('두 섹션 제목이 있고, "댓글 N개 중 대표 발화 N개" 같은 부가 문구는 없다', () => {
    const { container } = render(
      <CommunityResultView result={resultWithMessages()} freshness="FRESH" />,
    )

    expect(screen.getByRole('heading', { name: '핵심 논의' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '실제 논의 흐름' })).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/대표 발화 \d+개/)
  })

  it('저장소는 링크가 아니라 글자로만 보인다', () => {
    const { container } = render(
      <CommunityResultView result={SAMPLE_COMMUNITY_RESULT} freshness="FRESH" />,
    )

    expect(
      screen.getByText(`github.com/${SAMPLE_COMMUNITY_RESULT.repository!.full_name}`),
    ).toBeInTheDocument()
    expect(container.querySelector('a')).toBeNull()
  })

  it('기준 패키지 이름으로 제목을 만든다', () => {
    render(
      <CommunityResultView
        result={SAMPLE_COMMUNITY_RESULT}
        freshness="FRESH"
        packageName="axios"
      />,
    )

    expect(screen.getByRole('heading', { name: 'axios 커뮤니티 현황' })).toBeInTheDocument()
    expect(screen.getByText('AXIOS · GITHUB COMMUNITY')).toBeInTheDocument()
  })
})
