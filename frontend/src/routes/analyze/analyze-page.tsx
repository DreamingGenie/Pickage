import { CheckIcon, Loader2Icon, PencilIcon, SearchIcon, XIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { usePackageAutocomplete } from '@/api/autocomplete'
import { fetchPackageSearch, postCommunityRefresh } from '@/api/endpoints'
import { useSimilarPackages } from '@/api/queries'
import { MAX_NAMES, SEARCH_LIMIT_MAX } from '@/api/types'
import { paths } from '@/app/routes'
import { EmptyState } from '@/components/common/empty-state'
import { LoadingOverlay } from '@/components/common/loading-overlay'
import { Notice } from '@/components/common/notice'
import { Stepper } from '@/components/common/stepper'
import { Button } from '@/components/ui/button'
import { CandidateGrid } from '@/routes/analyze/candidate-grid'
import { PackageSearch } from '@/routes/analyze/package-search'
import { cn } from '@/lib/utils'

/** 기준 패키지를 포함한 비교 대상 수(IA §1-3). 서버의 `names` 상한과 같은 값이다. */
const MAX_COMPARISON = MAX_NAMES

/**
 * 화면에 깔 후보 수(IA §6.1-4: 기준 제외 최대 3개, 모두 미선택으로 노출).
 *
 * 고를 수 있는 자리는 `MAX_COMPARISON - 1`개뿐이지만, 노출 자체는 선택 가능 수가 아니라
 * IA가 정한 3개다 — 다 고르지 못하더라도 후보 폭은 그대로 보여준다(S15P21A506-309).
 */
const VISIBLE_CANDIDATES = 3

/**
 * 화면-01 · 02 (Figma 220:195 · 220:196).
 *
 * 기준 패키지는 **하나**다. 검색으로 넣는 건 언제나 한 개이고,
 * 최대 3개는 다음 단계에서 확정하는 비교 대상 수다(IA 1.1 · 1.4 · 5.2).
 *
 * IA 3.2 는 01 과 02 를 별도 화면으로 두지만 여기서는 같은 경로에서
 * 단계가 아래로 쌓인다. 이동 순서는 그대로 01 → 02 → 보고서다.
 */
export function AnalyzePage() {
  const navigate = useNavigate()
  /**
   * prefill — 인트로 히어로에서 넘어온 입력값.
   * restore — 보고서에서 "비교 대상 바꾸기"로 되돌아온 경우의 확정 선택.
   *           이미 확인된 패키지들이라 재확인 없이 2단계부터 다시 연다.
   */
  const location = useLocation()
  const nav = location.state as { prefill?: string; restore?: string[] } | null
  const restore = nav?.restore

  /*
    넘겨받은 state 는 첫 렌더에서 한 번만 쓴다. 브라우저는 history state 를 새로고침 뒤에도 남겨서,
    그대로 두면 다른 패키지로 바꾼 뒤 새로고침했을 때 처음 넘어온 패키지로 되돌아갔다.
  */
  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null })
    // 마운트 때 한 번만 비운다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const [draft, setDraft] = useState(nav?.prefill ?? restore?.[0] ?? '')
  const [extraError, setExtraError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>(restore?.slice(1) ?? [])
  const [limitHit, setLimitHit] = useState(false)
  const [extraDraft, setExtraDraft] = useState('')
  const [creating, setCreating] = useState(false)
  /** 방금 추가한 패키지. 선택 패널 아래 "추가했어요 · 되돌리기" 알림에 쓴다. */
  const [lastAdded, setLastAdded] = useState<string | null>(null)

  /**
   * 확인을 요청한 이름. **확정된 기준이 아니다.**
   *
   * 존재 확인과 후보 조회를 <b>한 번에</b> 한다 — 유사 패키지 응답이 이름이 없으면
   * `not_found` 로 알려주기 때문이다. 존재만 보려고 따로 한 번 더 부르면 왕복이 두 번이 되고,
   * 두 응답 사이에 이름이 사라지는 경우까지 다뤄야 한다.
   */
  const [submitted, setSubmitted] = useState<string | null>(nav?.prefill ?? restore?.[0] ?? null)
  /** 직접 추가 왕복 중 기준이 바뀌었는지 판별용 — state 클로저는 await 뒤에도 옛 값이라 ref 로 최신값을 쥔다. */
  const submittedRef = useRef(submitted)
  useEffect(() => {
    submittedRef.current = submitted
  }, [submitted])

  const similar = useSimilarPackages(submitted ?? '')

  /** 이름 자체가 없는 경우. 후보가 아직 없는 것(`NO_DATA`)과 다르다. */
  const missing =
    similar.data && similar.data.not_found.length > 0 ? similar.data.not_found[0] : null

  const base = submitted && similar.data && !missing ? submitted : null
  // isPending 만 보면 실패 후 재조회(isRefetching) 동안 스피너·비활성화가 안 걸린다 — isFetching 은 둘 다 포함
  const checking = Boolean(submitted) && similar.isFetching

  /** 이름을 못 찾은 경우는 `MissingPackage` 가 따로 그린다. 여기는 조회 자체가 실패한 경우다. */
  const error = !missing && similar.error ? 'SIMILAR_FAILED' : null

  /**
   * 서버는 `limit` 만큼 주지만 화면에는 일부만 깐다.
   *
   * **기본 선택을 하지 않는다.** 후보 3개를 모두 미선택으로 띄운다(IA §6.1-4·§6.3,
   * `DEC-RANK-UI-20260910-01`) — 미리 켜 두면 고르는 단계가 사라져 사용자는 자기가
   * 고르지 않은 조합으로 보고서를 받는다.
   */
  const candidates = (similar.data?.candidates ?? []).slice(0, VISIBLE_CANDIDATES)
  const selected = base ? [base, ...picked] : []
  const full = selected.length >= MAX_COMPARISON

  function verify(name: string) {
    const q = name.trim()
    if (!q) return
    // 같은 이름 재확인은 상태가 안 바뀌어 react-query 가 다시 안 보낸다 — 직접 refetch (S15P21A506-332)
    if (q === submitted) {
      void similar.refetch()
      return
    }
    setPicked([])
    setLimitHit(false)
    setSubmitted(q)
  }

  function resetBase() {
    setSubmitted(null)
    setPicked([])
    setLimitHit(false)
    setExtraError(null)
  }

  function toggle(name: string) {
    setLimitHit(false)
    setPicked((prev) => {
      if (prev.includes(name)) return prev.filter((n) => n !== name)
      // 네 번째 요청은 기존 선택을 자동 해제하지 않는다(IA 6.3 · 구상안 4.4)
      if (1 + prev.length >= MAX_COMPARISON) {
        setLimitHit(true)
        return prev
      }
      setLastAdded(name)
      return [...prev, name]
    })
  }

  /**
   * 직접 추가 (IA 6.1).
   *
   * **후보 순위는 바뀌지 않는다.** 사용자가 넣은 이름은 모델이 고른 것이 아니므로
   * 목록에 끼워 넣지 않고 선택에만 더한다(구상안 §4.4 `manualSelection`).
   *
   * 존재 확인은 검색 엔드포인트로 한다 — 접두사 검색이라 정확히 같은 이름이 결과에
   * 들어 있는지를 본다. 앞이 같은 다른 이름(`express-session`)이 통과하면 안 된다.
   * `SEARCH_LIMIT_MAX`(서버 상한)까지 받는다 — 상위 5개만 보면 인기순 밖으로 밀린
   * 정상 패키지를 "없음"으로 오판할 수 있다(부재 증명이 아니다).
   *
   * **왕복 사이 레이스 방어.** `await` 도중 기준이 바뀌거나, 같은 이름이 동시에 또
   * 들어오거나, 다른 추가로 한도가 다 찼을 수 있다 — 응답이 오면 그 시점 최신 상태로
   * 다시 확인한 뒤에만 반영한다(S15P21A506-309).
   */
  async function addManual(name: string) {
    const q = name.trim()
    setExtraError(null)
    if (!q) return
    if (selected.includes(q)) {
      setExtraError('이미 비교할 패키지에 들어 있어요.')
      return
    }
    if (full) {
      setExtraError(`이미 ${MAX_COMPARISON}개를 골랐어요. 하나를 빼면 넣을 수 있어요.`)
      return
    }

    const requestedFor = submitted

    try {
      const found = await fetchPackageSearch(q, SEARCH_LIMIT_MAX)
      if (!found.items.includes(q)) {
        setExtraError(`${q} 라는 패키지를 찾지 못했어요. 이름을 정확히 적었는지 확인해 주세요.`)
        return
      }
    } catch {
      setExtraError('확인하지 못했어요. 잠시 뒤에 다시 해 주세요.')
      return
    }

    // 기준이 바뀐 뒤 늦게 도착한 응답이면 지금 선택 목록과 무관하니 버린다.
    if (submittedRef.current !== requestedFor) return

    let added = false
    setPicked((prev) => {
      if (prev.includes(q) || 1 + prev.length >= MAX_COMPARISON) return prev
      added = true
      return [...prev, q]
    })
    if (added) {
      setExtraDraft('')
      setLastAdded(q)
    }
  }

  /**
   * 보고서 생성. 비교 대상을 확정하고 리포트 id 를 받아 이동한다.
   *
   * **비교 대상은 주소에 싣는다**(`?names=`). 라우터 state 로만 넘기면 그 링크를 받은
   * 사람에게는 state 가 없어 보고서가 조용히 다른 조합으로 떨어진다(S15P21A506-187).
   * `basePackage`는 예외다 — 공유 링크 재현과 무관한, 커뮤니티 탭이 `packages[0]`과
   * 대조해 문맥 충돌을 판정하기 위한 부가 신호일 뿐이라 state 로만 넘긴다(S15P21A506-316).
   *
   * 미해결: id 발급 주체. 지금은 서버 왕복을 흉내 내고 draft 로 들어간다.
   * 실패하면 오버레이를 걷고 이 화면에 남아 선택을 잃지 않게 해야 한다.
   */
  async function createReport() {
    if (!base) return
    setCreating(true)

    // 커뮤니티 수집 선착수(ANALYSIS_CONFIRMED). 비차단 — 응답을 기다리지 않고
    // 보고서 이동을 계속한다. 실패해도 커뮤니티 탭 최초 오픈이 TAB_OPENED 로 다시
    // 시도하므로 여기서는 조용히 삼킨다(구현계획 §2).
    postCommunityRefresh(base, 'ANALYSIS_CONFIRMED').catch(() => {})

    await new Promise((r) => setTimeout(r, CREATE_MS))
    navigate(paths.report('draft', selected), { state: { basePackage: base } })
  }

  /*
    인트로에서 이름을 치고 넘어온 경우와 보고서에서 되돌아온 경우는 `submitted` 의 초기값이
    처리한다 — 조회가 곧 존재 확인이라 도착하자마자 2단계가 열린다.

    예전에는 effect 안에서 확인을 한 번 돌렸는데, 그러면 첫 렌더 뒤에 상태가 또 바뀌어
    화면이 두 번 그려지고 "왜 잠깐 1단계가 보이지" 가 생긴다.
  */

  return (
    <div className="flex flex-col gap-8 py-4">
      <Stepper steps={FLOW_STEPS} currentId={base ? 'candidates' : 'input'} />

      {!base ? (
        /* ① 기준 패키지 — 하나만 받는다 */
        <section className="mx-auto flex w-full max-w-3xl flex-col gap-6">
          <header className="flex flex-col gap-2">
            <h1 className="text-3xl font-bold tracking-tight">
              비교의 기준이 될 패키지를 넣어 주세요
            </h1>
            <p className="text-base text-muted-foreground">
              지금 쓰고 있거나 알아보는 중인 npm 패키지 하나면 돼요. 비슷한 후보는 저희가 찾아
              드려요.
            </p>
          </header>

          <div className="flex flex-col gap-3 rounded-2xl border bg-card p-6">
            <span className="text-base font-semibold">기준 패키지</span>
            <div className="flex items-start gap-2">
              <PackageSearch
                value={draft}
                onChange={(v) => {
                  setDraft(v)
                  /*
                    오류는 상태가 아니라 조회 결과에서 파생된다. 지우려면 "무엇을 확인했는지" 를
                    비워야 한다 — 그래야 조회가 꺼지고 문구도 함께 사라진다.
                  */
                  if (missing) setSubmitted(null)
                }}
                onSubmit={verify}
                ariaLabel="기준 npm 패키지명"
                disabled={checking}
                autoFocus
                showCount
              />
              <Button
                size="lg"
                className="h-11 shrink-0"
                disabled={!draft.trim() || checking}
                onClick={() => verify(draft)}
              >
                {checking ? (
                  <>
                    <Loader2Icon className="size-4 animate-spin" aria-hidden />
                    찾는 중
                  </>
                ) : (
                  '패키지 확인'
                )}
              </Button>
            </div>

            {missing ? (
              <MissingPackage
                name={missing}
                onPick={(n) => {
                  setDraft(n)
                  verify(n)
                }}
              />
            ) : (
              error && (
                <Notice tone="error" title="후보를 불러오지 못했어요">
                  잠시 뒤에 다시 확인해 주세요.
                </Notice>
              )
            )}

            <p className="text-sm text-muted-foreground">
              버전은 여기서 고르지 않아요. 보고서의 기능 비교 탭에서 골라요.
            </p>
          </div>
        </section>
      ) : (
        <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
          {/* ② 후보 고르기 */}
          <section className="flex min-w-0 flex-col gap-7">
            <header className="flex flex-wrap items-end justify-between gap-3">
              <div className="flex flex-col gap-2">
                <h1 className="text-3xl font-bold tracking-tight">
                  함께 비교할 패키지를 골라 주세요
                </h1>
                <p className="text-base text-muted-foreground">
                  <span className="font-mono text-foreground">{base}</span> 와 비슷한 패키지를
                  찾았어요. 최대 {MAX_COMPARISON - 1}개를 더 고를 수 있어요.
                </p>
              </div>
              <Button variant="outline" size="sm" onClick={resetBase}>
                <PencilIcon className="size-3.5" aria-hidden />
                기준 바꾸기
              </Button>
            </header>

            {/*
              직접 찾기를 후보 위로 올렸다. 아래에 두면 원하는 패키지가 후보에 없을 때 한참 내려가야
              찾을 수 있었다. 후보 순위는 바뀌지 않는다(IA 6.1).
            */}
            <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <span className="text-base font-semibold">목록에 없는 패키지 직접 찾기</span>
              <div className="flex items-start gap-2">
                <PackageSearch
                  value={extraDraft}
                  onChange={(v) => {
                    setExtraDraft(v)
                    if (extraError) setExtraError(null)
                  }}
                  onSubmit={(v) => void addManual(v)}
                  placeholder="정확한 패키지 이름"
                  ariaLabel="직접 추가할 패키지명"
                  disabled={full}
                  showCount
                />
                <Button
                  variant="outline"
                  size="lg"
                  className="h-11 shrink-0"
                  disabled={!extraDraft.trim() || full}
                  onClick={() => void addManual(extraDraft)}
                >
                  추가
                </Button>
              </div>
              {extraError ? (
                <p role="alert" className="text-base text-destructive">
                  {extraError}
                </p>
              ) : (
                full && (
                  <p className="text-sm text-muted-foreground">
                    이미 {MAX_COMPARISON}개를 골랐어요. 오른쪽에서 하나를 빼면 새로 넣을 수 있어요.
                  </p>
                )
              )}
            </div>

            <div className="flex flex-col gap-4">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-xl font-semibold tracking-tight">비슷한 패키지</h2>
                <span className="text-sm text-muted-foreground">
                  설명이 비슷한 순서예요 · 품질 순위가 아니에요
                </span>
              </div>

              {/*
                빈 상태가 두 갈래다. **아직 계산되지 않은 것**(`NO_DATA`)과 **관련 후보가 없는 것**은
                사용자가 할 일이 다르다. 앞은 기다리면 되고 뒤는 직접 추가해야 한다.
                "판정 모델" 표시는 사용자에게 뜻이 없어 걷어냈다(모델 버전은 응답에 그대로 남는다).
              */}
              {candidates.length === 0 ? (
                <EmptyState
                  icon={SearchIcon}
                  title={
                    similar.data?.data_status === 'NO_DATA'
                      ? '아직 비슷한 패키지를 찾는 중이에요'
                      : '비슷한 패키지를 찾지 못했어요'
                  }
                  description={
                    similar.data?.data_status === 'NO_DATA'
                      ? '후보는 매주 새로 계산해요. 그동안은 위에서 이름으로 직접 넣을 수 있어요.'
                      : '위에서 이름으로 직접 넣거나, 다른 기준 패키지로 시작해 보세요.'
                  }
                />
              ) : (
                <CandidateGrid candidates={candidates} picked={picked} onToggle={toggle} />
              )}
            </div>
          </section>

          {/* 선택 패널 — 무엇을 골랐는지 늘 보이게 오른쪽에 붙인다 */}
          <aside className="flex flex-col gap-4 lg:sticky lg:top-6">
            <div className="flex flex-col gap-4 rounded-2xl border bg-card p-5">
              <div className="flex items-baseline justify-between">
                <h2 className="text-lg font-semibold">비교할 패키지</h2>
                <span className="font-mono text-base text-muted-foreground tabular-nums">
                  {selected.length} / {MAX_COMPARISON}
                </span>
              </div>
              <ul className="flex flex-col gap-2">
                {selected.map((n, i) => (
                  <li
                    key={n}
                    className={cn(
                      'flex min-w-0 items-center gap-2 rounded-lg border px-3 py-2',
                      i === 0 ? 'bg-muted/50' : 'bg-card',
                    )}
                  >
                    {i === 0 && (
                      <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-sm font-medium text-primary">
                        기준
                      </span>
                    )}
                    <span title={n} className="min-w-0 flex-1 truncate font-mono text-base">
                      {n}
                    </span>
                    {i > 0 && (
                      <button
                        type="button"
                        onClick={() => toggle(n)}
                        aria-label={`${n} 비교에서 빼기`}
                        className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <XIcon className="size-4" aria-hidden />
                      </button>
                    )}
                  </li>
                ))}
                {!full && (
                  <li className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
                    {MAX_COMPARISON - selected.length}개 더 고를 수 있어요
                  </li>
                )}
              </ul>

              {limitHit && (
                <Notice tone="warn" title={`한 번에 ${MAX_COMPARISON}개까지 비교할 수 있어요`}>
                  고른 것 중 하나를 빼면 새로 넣을 수 있어요.
                </Notice>
              )}

              <Button
                size="lg"
                className="w-full"
                disabled={creating}
                onClick={() => void createReport()}
              >
                {selected.length === 1
                  ? '기준 패키지만 보고서 보기'
                  : `${selected.length}개로 보고서 보기`}
              </Button>
            </div>

            {/* 방금 넣은 것 — 추가가 눈에 띄지 않는다는 의견으로 넣었다. 되돌리기로 바로 뺄 수 있다. */}
            {lastAdded && picked.includes(lastAdded) && (
              <div
                role="status"
                className="flex items-center gap-2 rounded-xl bg-tone-positive px-4 py-3 text-base text-tone-positive-foreground"
              >
                <CheckIcon className="size-4 shrink-0" aria-hidden />
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-mono font-semibold">{lastAdded}</span> 를 추가했어요
                </span>
                <button
                  type="button"
                  onClick={() => toggle(lastAdded)}
                  className="shrink-0 font-semibold underline underline-offset-2"
                >
                  되돌리기
                </button>
              </div>
            )}

            <p className="rounded-xl bg-brand-soft px-4 py-3 text-base leading-relaxed text-foreground/80">
              <strong className="font-semibold text-foreground">처음이신가요?</strong> 비슷한 기능을
              하는 패키지 2~3개를 고르면 비교가 잘 돼요. 너무 다른 패키지를 섞으면 공통 기능이 적게
              나와요.
            </p>
          </aside>
        </div>
      )}

      <LoadingOverlay open={creating} title="보고서를 준비하고 있어요" steps={CREATE_STEPS} />
    </div>
  )
}

/**
 * 이름을 못 찾았을 때. "철자를 확인해 주세요" 로 끝내지 않고 **비슷한 이름을 내민다.**
 *
 * 따로 오타 교정 API 가 없어서 접두사 자동완성을 그대로 쓴다 — 끝 글자 하나를 뗀 앞부분으로 찾으면
 * `expres` → express 처럼 끝이 잘리거나 한 글자 틀린 경우 대부분이 걸린다. 못 찾으면 안내만 남긴다.
 */
function MissingPackage({ name, onPick }: { name: string; onPick: (name: string) => void }) {
  const prefix = name.length > 2 ? name.slice(0, -1) : name
  const { suggestions } = usePackageAutocomplete(prefix)
  const options = suggestions
    .map((s) => s.name)
    .filter((n) => n !== name)
    .slice(0, 3)

  return (
    <Notice
      tone="error"
      title={
        <>
          <span className="font-mono">{name}</span> 라는 패키지는 없어요
        </>
      }
    >
      {options.length > 0 ? (
        <div className="flex flex-col gap-2">
          <span>혹시 이 패키지를 찾으셨나요?</span>
          <span className="flex flex-wrap gap-2">
            {options.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => onPick(n)}
                className="rounded-full border bg-card px-3 py-1 font-mono text-sm text-foreground transition-colors hover:border-primary/50 hover:text-primary"
              >
                {n}
              </button>
            ))}
          </span>
        </div>
      ) : (
        '철자를 한 번 더 확인해 주세요. 앞 글자만 적으면 목록에서 고를 수 있어요.'
      )}
    </Notice>
  )
}

/** 화면 위 진행 표시. 인트로의 3단계와 같은 이름을 쓴다. */
const FLOW_STEPS = [
  { id: 'input', label: '기준 패키지' },
  { id: 'candidates', label: '비교할 후보 고르기' },
  { id: 'report', label: '보고서' },
]

/** 보고서 생성 왕복 흉내. 실제로는 id 발급 + 사전 집계 조회다. */
const CREATE_MS = 2700

const CREATE_STEPS = ['비교 대상 확정', '모아 둔 자료 불러오기', '보고서 준비'] as const
