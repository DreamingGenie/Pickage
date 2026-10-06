import type { CommunityDataLimits, CommunityLimitation } from '@/api/types'

/**
 * 수집 기준과 저장소 수준의 한계 — "수집 기준" ⓘ 모달의 본문(S15P21A506-406).
 *
 * 예전에는 화면 맨 아래 각주와 맨 위의 점선 상자들로 상시 노출했다. 매번 읽을 필요는 없지만 **불완전
 * 수집을 완전한 논의로 오해하지 않게 하려면 없어서는 안 되는** 설명이라 모달로 옮긴다(요구사항 확장-03-R12·R16).
 *
 * 문구는 서버가 준 것을 그대로 쓴다 — `source_note` 와 한계 `message` 는 서버 템플릿이 만들고 검증한다.
 * 조회 기간은 응답의 `data_limits.lookback_days` 값이다. 화면이 다시 만들면 정책이 바뀔 때 여기만 낡은 값으로
 * 남는다(구현계획 §6.2·8.3). 예전의 `(lookback 180d · issues ≤2 …)` 개발자 표기는 없앴다 — 이슈·댓글 상한은
 * `source_note` 가 이미 말하고 있어 같은 숫자를 두 번 적을 이유가 없다.
 */
export function CommunityScopeInfo({
  limits,
  limitations,
}: {
  limits: CommunityDataLimits
  limitations: CommunityLimitation[]
}) {
  // issue_number 가 없는 것이 저장소 수준이다. Issue 하나에 붙는 한계는 각 카드의 ⓘ 가 낸다.
  const repoLimitations = limitations.filter((l) => l.issue_number === null)

  return (
    <>
      <p>{limits.source_note}</p>
      {/* 이슈·댓글 상한은 `source_note` 가 이미 말한다. 여기서 같은 숫자를 다시 적지 않고 노트에 없는 조회 기간만 더한다. */}
      <p>조회 기간은 최근 {limits.lookback_days}일입니다.</p>
      {repoLimitations.length > 0 && (
        <ul className="flex list-disc flex-col gap-1.5 pl-5">
          {repoLimitations.map((l) => (
            <li key={l.code}>{l.message}</li>
          ))}
        </ul>
      )}
    </>
  )
}
