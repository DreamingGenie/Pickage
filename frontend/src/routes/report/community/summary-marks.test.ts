import { describe, expect, it } from 'vitest'

import { githubIssueUrl } from '@/routes/report/community/summary-marks'

describe('githubIssueUrl', () => {
  it('검증된 저장소 이름과 번호로 Issue 주소를 만든다', () => {
    expect(githubIssueUrl('axios/axios', 10636)).toBe('https://github.com/axios/axios/issues/10636')
    expect(githubIssueUrl('pinojs/pino', 1)).toBe('https://github.com/pinojs/pino/issues/1')
    expect(githubIssueUrl('a.b/c_d-e', 7)).toBe('https://github.com/a.b/c_d-e/issues/7')
  })

  it('이름이나 번호가 이상하면 null — 링크를 만들지 않는다', () => {
    for (const bad of [
      null,
      undefined,
      '',
      'axios',
      'axios/axios/extra',
      'a b/c',
      '../etc/passwd',
      'axios/axios?x=1',
      'axios/axios#frag',
      'https://evil.example/x',
    ]) {
      expect(githubIssueUrl(bad, 1)).toBeNull()
    }
    for (const bad of [0, -1, 1.5, Number.NaN]) {
      expect(githubIssueUrl('axios/axios', bad)).toBeNull()
    }
  })
})
