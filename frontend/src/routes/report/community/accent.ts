/**
 * Issue 를 구분하는 색(S15P21A506-407). "핵심 논의" 카드와 같은 Issue 의 "실제 논의 흐름" 카드가 같은 색을
 * 써서 둘을 눈으로 잇는다. **색은 장식**이다 — 어느 Issue 인지는 언제나 `#번호` 글자가 말한다(IA §1-13).
 *
 * 클래스 이름은 Tailwind 가 소스에서 찾을 수 있게 통째로 적는다(조립하지 않는다).
 */
export interface IssueAccent {
  /** 카드 왼쪽 굵은 선 */
  bar: string
  /** `#번호` 글자 */
  text: string
}

const ACCENTS: IssueAccent[] = [
  { bar: 'border-l-emerald-700', text: 'text-emerald-700' },
  { bar: 'border-l-blue-700', text: 'text-blue-700' },
]

/** 수집 상한이 Issue 2개라 두 색이면 충분하지만, 늘어나도 깨지지 않게 돌려 쓴다. */
export function issueAccent(index: number): IssueAccent {
  return ACCENTS[index % ACCENTS.length]
}
