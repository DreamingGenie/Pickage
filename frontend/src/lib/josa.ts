/**
 * 조사 붙이기 — 앞말의 받침에 따라 갈리는 것들 (S15P21A506-468).
 *
 * 화면이 "winston 을 지운 프로젝트 중 8.4%가 pino 를 넣었어요" 처럼 **패키지 이름을 문장에
 * 넣으면서** 필요해졌다. 한글이면 종성으로 정해지지만 npm 이름은 대부분 영문이고, 영문은
 * <b>발음으로 정해진다</b> — 글자만 봐서는 완전하게 알 수 없다.
 *
 * <h2>완전하지 않다는 것을 전제로 쓴다</h2>
 *
 * 여기 규칙은 **관용적으로 통하는 근사**다. `chalk`(크), `axios`(스)처럼 끝 자음이
 * 묵음이거나 모음으로 읽히는 이름에서 어긋날 수 있다. 그래도 쓰는 이유는, 대안이
 * "winston을(를)" 같은 괄호 표기이거나 조사를 피해 문장을 비트는 것인데 <b>둘 다 읽기가
 * 더 나쁘기 때문이다.</b>
 *
 * <b>어긋나도 뜻이 달라지지 않는다</b>는 점이 이 근사를 허용하는 근거다. 조사가 어색한 것과
 * 수치가 틀린 것은 무게가 다르다 — 이 파일은 앞쪽만 건드린다.
 */

/** 한글 음절인가 (가~힣). */
const isHangulSyllable = (code: number) => code >= 0xac00 && code <= 0xd7a3

/**
 * 영문 이름의 끝을 **받침처럼 읽는가**.
 *
 * 관용을 따른다 — `-n`(winston), `-m`(npm), `-l`(tslib 아님, `curl`), `-ng`(spring) 은
 * 받침으로 읽고, 모음으로 끝나면(`pino`, `dayjs` 의 s 는 아래 참고) 받침이 없다.
 *
 * `s`·`k`·`t`·`p`·`x` 같은 무성 자음은 실제로는 "스·크·트·프·스" 로 읽혀 <b>받침이 없는
 * 쪽</b>이다(axios 를, chalk 를). 그래서 받침 목록에 넣지 않는다.
 */
const CLOSED_TAIL = /[nmlr]$|ng$/i

/** 숫자로 끝나는 이름(`vue3`)은 그 숫자의 한글 읽기로 정한다. */
const DIGIT_HAS_TAIL: Record<string, boolean> = {
  '0': true, // 영
  '1': true, // 일
  '2': false, // 이
  '3': true, // 삼
  '4': false, // 사
  '5': false, // 오
  '6': true, // 육
  '7': true, // 칠
  '8': true, // 팔
  '9': false, // 구
}

/**
 * 앞말에 받침이 있는가. 판단할 수 없으면 `null` — 부르는 쪽이 조사를 생략할 수 있다.
 */
export function hasFinalConsonant(word: string): boolean | null {
  const trimmed = word.trim()
  if (!trimmed) return null

  const last = trimmed[trimmed.length - 1]!
  const code = last.charCodeAt(0)

  // 한글은 종성으로 정확히 갈린다 — 근사가 아니다.
  if (isHangulSyllable(code)) return (code - 0xac00) % 28 !== 0
  if (/[0-9]/.test(last)) return DIGIT_HAS_TAIL[last] ?? null
  if (/[a-z]/i.test(last)) return CLOSED_TAIL.test(trimmed)

  // 괄호·기호로 끝나는 이름(`@scope/pkg` 는 위에서 걸린다)은 판단하지 않는다.
  return null
}

/**
 * `word` 뒤에 붙일 조사를 고른다.
 *
 * @param withTail  받침이 <b>있을 때</b> 쓰는 형태 (을 · 은 · 이 · 과)
 * @param withoutTail 받침이 <b>없을 때</b> 쓰는 형태 (를 · 는 · 가 · 와)
 *
 * 판단할 수 없으면 받침 없는 쪽을 쓴다. 모르는 채로 "을(를)" 을 내보내는 것보다 낫다 —
 * 문장은 어색해도 읽히고, 괄호는 읽는 흐름을 끊는다.
 */
export function josa(word: string, withTail: string, withoutTail: string): string {
  return hasFinalConsonant(word) ? withTail : withoutTail
}
