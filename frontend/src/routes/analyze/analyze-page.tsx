import { Loader2Icon, SearchIcon } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { fetchPackagesOverview, fetchSimilarPackages, postCommunityRefresh } from '@/api/endpoints'
import { usePackagesOverview, useSimilarPackages } from '@/api/queries'
import {
  ANALYZE_BASE_PARAM,
  ANALYZE_NO_SIMILAR_PARAM,
  ANALYZE_WITH_PARAM,
  paths,
} from '@/app/routes'
import { EmptyState } from '@/components/common/empty-state'
import { InfoDialog } from '@/components/common/info-dialog'
import { LoadingOverlay } from '@/components/common/loading-overlay'
import { Notice } from '@/components/common/notice'
import { Stepper } from '@/components/common/stepper'
import { Button } from '@/components/ui/button'
import { MAX_COMPARISON, useAnalyzeSelection } from '@/routes/analyze/analyze-selection'
import { CandidateGrid } from '@/routes/analyze/candidate-grid'
import { MissingPackage, NoSimilarWarning } from '@/routes/analyze/missing-package'
import { PackageSearch } from '@/routes/analyze/package-search'
import { SelectionPanel } from '@/routes/analyze/selection-panel'

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
  const [searchParams, setSearchParams] = useSearchParams()

  /**
   * 화면의 선택 전체를 주소가 들고 있다(S15P21A506-435).
   *
   * 예전에는 라우터 state 로만 받았다. 브라우저는 history state 를 새로고침 뒤에도 남기므로,
   * 다른 패키지로 바꿔 검색한 뒤 새로고침하면 처음 넘어온 패키지로 되돌아갔다. 주소에
   * 실으면 새로고침·뒤로가기·공유가 전부 같은 화면을 연다.
   *
   * `submitted` 는 확인을 <b>요청한</b> 이름이다. 확정된 기준은 아래 `base` 다.
   * 존재 확인과 후보 조회를 <b>한 번에</b> 한다 — 유사 패키지 응답이 이름이 없으면
   * `not_found` 로 알려주기 때문이다. 존재만 보려고 따로 한 번 더 부르면 왕복이 두 번이 되고,
   * 두 응답 사이에 이름이 사라지는 경우까지 다뤄야 한다.
   *
   * `dropped` 는 자리가 모자라, `rejected` 는 npm 이름 형식이 아니라 쓰지 않은 이름이다.
   * 둘 다 화면에 적는다 — 조용히 버리면 주소와 화면이 다른데 그것을 알 방법이 없다.
   *
   * `acceptedNoSimilar` 는 유사 후보가 없는 기준을 그래도 쓰겠다고 한 확인이다. 이것도
   * 주소에 있어야 한다 — 화면 state 로 두면 새로고침 뒤 기준은 남는데 화면만 1단계
   * 경고로 되돌아가, 이 티켓이 없애려는 실패가 그 경로에만 남는다.
   */
  const rawBase = searchParams.get(ANALYZE_BASE_PARAM)
  const {
    base: submitted,
    picked,
    dropped,
    rejected,
    acceptedNoSimilar,
  } = useAnalyzeSelection(
    rawBase,
    searchParams.get(ANALYZE_WITH_PARAM),
    searchParams.get(ANALYZE_NO_SIMILAR_PARAM),
  )

  /**
   * 기준을 주소에 적는다. 지울 때는 `null`.
   *
   * **고른 후보는 함께 지운다.** 후보는 기준에 딸린 것이라, 기준이 바뀌면 남아 있을 자리가
   * 없다. 그래서 기존 쿼리를 이어받지 않고 새로 만든다.
   *
   * `replace` 는 히스토리에 자국을 남기지 않을 때만 쓴다 — 오타를 고치는 도중처럼
   * 사용자가 "되돌아가고 싶어 할 지점" 이 아닌 변화다.
   */
  function setBase(name: string | null, options?: { replace?: boolean }) {
    const next = new URLSearchParams()
    if (name) next.set(ANALYZE_BASE_PARAM, name)
    setSearchParams(next, { replace: options?.replace ?? false })
  }

  /**
   * 고른 후보만 바꾼다.
   *
   * **언제나 `replace` 다.** 체크박스를 누를 때마다 히스토리에 항목이 쌓이면 뒤로가기가
   * 화면을 떠나는 대신 체크를 하나씩 되감게 된다.
   */
  function setPicked(names: readonly string[]) {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        if (names.length) next.set(ANALYZE_WITH_PARAM, names.join(','))
        else next.delete(ANALYZE_WITH_PARAM)
        return next
      },
      { replace: true },
    )
  }

  /**
   * "유사 후보가 없어도 그래도 쓰겠다" 를 주소에 적는다.
   *
   * 1단계에서 2단계로 넘어가는 변화라 `push` 다 — 뒤로가기를 누르면 경고로 돌아간다.
   * 기준을 바꾸면 `setBase` 가 쿼리를 새로 만들면서 이 확인도 함께 지운다. 확인은 그
   * 기준에 대한 것이라 다른 이름으로 넘어가면 안 된다.
   */
  function acceptNoSimilar() {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set(ANALYZE_NO_SIMILAR_PARAM, '1')
      return next
    })
  }

  const [draft, setDraft] = useState(submitted ?? '')
  const [extraError, setExtraError] = useState<string | null>(null)
  /**
   * 직접 추가하려는데 유사 후보가 없어 확인을 기다리는 이름.
   *
   * 기준 쪽의 같은 확인은 주소에 있다(`acceptedNoSimilar`) — 그쪽은 어느 단계를 볼지
   * 정하므로 새로고침에 살아남아야 하고, 이쪽은 누르는 그 순간에만 뜨는 물음이다.
   */
  const [noDataExtra, setNoDataExtra] = useState<string | null>(null)
  /** 보고서로 넘기기 직전 확인에서 자료가 없어 뺀 이름들 */
  const [unavailable, setUnavailable] = useState<string[]>([])
  /** 직접 찾기에서 확인했지만 없던 이름. 같은 이름으로는 다시 넣지 못하게 막는다. */
  const [extraMissing, setExtraMissing] = useState<string | null>(null)
  const [limitHit, setLimitHit] = useState(false)
  const [extraDraft, setExtraDraft] = useState('')
  const [creating, setCreating] = useState(false)
  /** 방금 추가한 패키지. 선택 패널 아래 "추가했어요 · 되돌리기" 알림에 쓴다. */
  const [lastAdded, setLastAdded] = useState<string | null>(null)

  /** 직접 추가 왕복 중 기준이 바뀌었는지 판별용 — state 클로저는 await 뒤에도 옛 값이라 ref 로 최신값을 쥔다. */
  const submittedRef = useRef(submitted)
  useEffect(() => {
    submittedRef.current = submitted
  }, [submitted])
  /** 같은 이유로 고른 목록도 최신값을 쥔다 — 왕복 사이에 다른 추가가 자리를 채웠을 수 있다. */
  const pickedRef = useRef(picked)
  useEffect(() => {
    pickedRef.current = picked
  }, [picked])

  const similar = useSimilarPackages(submitted ?? '')
  /*
    기준 패키지도 보고서가 쓰는 조회(`/packages`)로 함께 확인한다. 유사 패키지 조회는 이름 목록에만
    있으면 통과시켜서, 보고서 자료가 없는 이름이 기준으로 잡혀 보고서가 깨졌다.
  */
  const overview = usePackagesOverview(submitted ? [submitted] : [])
  const hasReportData =
    overview.data !== undefined &&
    !overview.data.not_found.includes(submitted ?? '') &&
    overview.data.items.some((it) => it.name === submitted)

  /** 이름 자체가 없거나, 있어도 보고서 자료가 없는 경우. 후보가 아직 없는 것(`NO_DATA`)과 다르다. */
  const missing =
    similar.data && similar.data.not_found.length > 0
      ? similar.data.not_found[0]
      : submitted && overview.data && !hasReportData
        ? submitted
        : null

  /**
   * 이름·자료는 있지만 유사 후보가 없다(`NO_DATA`). 막지는 않고, 비교가 빈약할 수 있다고 알린 뒤
   * 사용자가 "그래도 진행" 을 눌러야 2단계로 넘어간다.
   */
  const noDataBase =
    Boolean(submitted) &&
    hasReportData &&
    !missing &&
    similar.data?.data_status === 'NO_DATA' &&
    !acceptedNoSimilar

  const base =
    submitted && similar.data && hasReportData && !missing && !noDataBase ? submitted : null
  // isPending 만 보면 실패 후 재조회(isRefetching) 동안 스피너·비활성화가 안 걸린다 — isFetching 은 둘 다 포함
  const checking = Boolean(submitted) && (similar.isFetching || overview.isFetching)

  /** 이름을 못 찾은 경우는 `MissingPackage` 가 따로 그린다. 여기는 조회 자체가 실패한 경우다. */
  const error = !missing && (similar.error || overview.error) ? 'SIMILAR_FAILED' : null

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
    /*
      같은 이름 재확인은 주소가 안 바뀌어 react-query 가 다시 안 보낸다 — 직접 refetch
      (S15P21A506-332).

      **주소에 적힌 원문(`rawBase`)도 함께 본다.** 형식이 아닌 이름은 `submitted` 가 되지
      못하므로 그것만 보면 같은 이름을 다시 눌러도 매번 새 주소로 읽혀, 누를 때마다
      히스토리에 자국이 하나씩 쌓인다.
    */
    if (q === submitted || q === rawBase) {
      void similar.refetch()
      void overview.refetch()
      return
    }
    setLimitHit(false)
    // 기준이 바뀌면 고른 후보도 함께 지워진다(`setBase`).
    setBase(q)
  }

  function resetBase() {
    setLimitHit(false)
    setExtraError(null)
    // 유사 후보 확인도 함께 지워진다 — `setBase` 가 쿼리를 새로 만든다.
    setBase(null)
  }

  function toggle(name: string) {
    setLimitHit(false)
    if (picked.includes(name)) {
      setPicked(picked.filter((n) => n !== name))
      return
    }
    // 네 번째 요청은 기존 선택을 자동 해제하지 않는다(IA 6.3 · 구상안 4.4)
    if (1 + picked.length >= MAX_COMPARISON) {
      setLimitHit(true)
      return
    }
    setLastAdded(name)
    setPicked([...picked, name])
  }

  /**
   * 직접 추가 (IA 6.1).
   *
   * **후보 순위는 바뀌지 않는다.** 사용자가 넣은 이름은 모델이 고른 것이 아니므로
   * 목록에 끼워 넣지 않고 선택에만 더한다(구상안 §4.4 `manualSelection`).
   *
   * 존재 확인은 보고서와 같은 `/packages` 조회로 한다 — 여기서 통과한 이름은 보고서에서도 자료가 있다.
   *
   * **왕복 사이 레이스 방어.** `await` 도중 기준이 바뀌거나, 같은 이름이 동시에 또
   * 들어오거나, 다른 추가로 한도가 다 찼을 수 있다 — 응답이 오면 그 시점 최신 상태로
   * 다시 확인한 뒤에만 반영한다(S15P21A506-309).
   */
  async function addManual(name: string, force = false) {
    const q = name.trim()
    setExtraError(null)
    setExtraMissing(null)
    setNoDataExtra(null)
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

    /*
      보고서가 쓰는 것과 **같은 조회**(`/packages`)로 확인한다. 예전에는 이름 검색만 봤는데, 검색 목록에는
      있어도 보고서 자료가 없는 이름이 통과해 보고서가 깨졌다. 여기서 없다고 하면 보고서에서도 없다.
    */
    try {
      const found = await fetchPackagesOverview([q])
      if (found.not_found.includes(q) || !found.items.some((it) => it.name === q)) {
        setExtraMissing(q)
        return
      }
      // 유사 후보가 없는 패키지는 막지 않고 한 번 묻는다. "그래도 추가" 를 누르면 force 로 다시 들어온다.
      if (!force) {
        const similarOfExtra = await fetchSimilarPackages(q, 1)
        if (similarOfExtra.data_status === 'NO_DATA') {
          setNoDataExtra(q)
          return
        }
      }
    } catch {
      setExtraError('확인하지 못했어요. 잠시 뒤에 다시 해 주세요.')
      return
    }

    // 기준이 바뀐 뒤 늦게 도착한 응답이면 지금 선택 목록과 무관하니 버린다.
    if (submittedRef.current !== requestedFor) return

    // 왕복 사이에 같은 이름이 또 들어왔거나 다른 추가가 마지막 자리를 채웠을 수 있다.
    const latest = pickedRef.current
    if (latest.includes(q) || 1 + latest.length >= MAX_COMPARISON) return

    setPicked([...latest, q])
    setExtraDraft('')
    setLastAdded(q)
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
    setUnavailable([])

    /*
      보내기 전에 한 번 더 확인한다. **주소에서 온 이름은 확인을 거치지 않았다** — 기준은
      조회로 걸러지지만 고른 후보는 형식만 봤을 뿐이라, 자료가 없는 이름이 섞여 있을 수 있다.
      그런 이름은 넘기지 않고 빼 준 뒤 이 화면에 남는다.
    */
    try {
      const checked = await fetchPackagesOverview(selected)
      const missingNames = selected.filter(
        (n) => checked.not_found.includes(n) || !checked.items.some((it) => it.name === n),
      )
      if (missingNames.length > 0) {
        setPicked(pickedRef.current.filter((n) => !missingNames.includes(n)))
        setUnavailable(missingNames)
        setCreating(false)
        return
      }
    } catch {
      setExtraError('확인하지 못했어요. 잠시 뒤에 다시 해 주세요.')
      setCreating(false)
      return
    }

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
      {/* 1 을 누르면 기준 패키지 입력으로 돌아간다(지나온 단계만 누를 수 있다) */}
      <Stepper
        steps={FLOW_STEPS}
        currentId={base ? 'candidates' : 'input'}
        onStepClick={(id) => id === 'input' && resetBase()}
      />

      {/*
        1·2단계가 같은 틀(왼쪽 본문 + 오른쪽 패널 자리)을 쓴다. 1단계도 처음부터 왼쪽에 붙어 있어서,
        2단계로 넘어갈 때 본문이 옆으로 밀리지 않고 오른쪽 패널만 새로 나타난다.
      */}
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        {!base ? (
          /* ① 기준 패키지 — 하나만 받는다 */
          <section
            key="input"
            className="flex min-w-0 animate-in flex-col gap-7 duration-300 fade-in-0 slide-in-from-bottom-2"
          >
            <header className="flex flex-col gap-2">
              <h1 className="text-3xl font-bold tracking-tight">
                비교의 기준이 될 패키지를 넣어 주세요
              </h1>
              <p className="text-base text-muted-foreground">
                지금 쓰고 있거나 알아보는 중인 npm 패키지 하나면 돼요. 비슷한 후보는 저희가 찾아
                드려요.
              </p>
            </header>

            <div className="flex flex-col gap-3 rounded-2xl border bg-card p-5">
              <span className="text-base font-semibold">기준 패키지</span>
              <div className="flex items-start gap-2">
                <PackageSearch
                  value={draft}
                  onChange={(v) => {
                    setDraft(v)
                    /*
                    오류는 상태가 아니라 조회 결과에서 파생된다. 지우려면 "무엇을 확인했는지" 를
                    비워야 한다 — 그래야 조회가 꺼지고 문구도 함께 사라진다.

                    오타를 고치는 도중이라 히스토리에 남길 지점이 아니다 — `replace` 로 지운다.
                  */
                    if (missing) setBase(null, { replace: true })
                  }}
                  onSubmit={verify}
                  ariaLabel="기준 npm 패키지명"
                  disabled={checking}
                  autoFocus
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
                <MissingPackage name={missing} />
              ) : rejected.length > 0 ? (
                /*
                  주소에 적혀 있었지만 npm 이름 형식이 아니라 조회하지 않은 것. 조용히 빈
                  화면을 띄우면 링크를 받은 사람은 무엇이 잘못됐는지 알 방법이 없다.
                */
                <Notice tone="error" title="주소에 적힌 패키지 이름을 읽지 못했어요">
                  <span className="font-mono">{rejected.join(', ')}</span> 는 npm 패키지 이름
                  형식이 아니에요. 위에 이름을 직접 넣어 주세요.
                </Notice>
              ) : noDataBase && submitted ? (
                <NoSimilarWarning
                  name={submitted}
                  confirmLabel="그래도 기준으로 쓰기"
                  onConfirm={acceptNoSimilar}
                  onCancel={() => {
                    setBase(null)
                    setDraft('')
                  }}
                />
              ) : (
                error && (
                  <Notice tone="error" title="후보를 불러오지 못했어요">
                    잠시 뒤에 다시 확인해 주세요.
                  </Notice>
                )
              )}
            </div>
          </section>
        ) : (
          <>
            {/* ② 후보 고르기 — 1단계 자리에서 부드럽게 바뀌어 나타난다 */}
            <section
              key="candidates"
              className="flex min-w-0 animate-in flex-col gap-7 duration-300 fade-in-0 slide-in-from-bottom-2"
            >
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
              </header>

              {/*
                주소에 적혀 있었지만 쓰지 않은 이름. 조용히 자르면 주소에는 더 있는데 화면에는
                상한까지만 뜨고, 무엇이 빠졌는지 알 방법이 없다 — S15P21A506-187 이 보고서
                화면에서 없앤 실패라 여기에 새로 만들지 않는다.
              */}
              {(dropped.length > 0 || rejected.length > 0) && (
                <Notice tone="warn" title="주소에 적힌 일부를 비교에 넣지 못했어요">
                  {dropped.length > 0 && (
                    <p>
                      한 번에 {MAX_COMPARISON}개까지 비교해요. 자리가 모자라{' '}
                      <span className="font-mono">{dropped.join(', ')}</span> 는 뺐어요.
                    </p>
                  )}
                  {rejected.length > 0 && (
                    <p>
                      <span className="font-mono">{rejected.join(', ')}</span> 는 npm 패키지 이름
                      형식이 아니에요.
                    </p>
                  )}
                </Notice>
              )}

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
                      if (extraMissing) setExtraMissing(null)
                      if (noDataExtra) setNoDataExtra(null)
                      if (unavailable.length) setUnavailable([])
                    }}
                    onSubmit={(v) => void addManual(v)}
                    placeholder="정확한 패키지 이름"
                    ariaLabel="직접 추가할 패키지명"
                    disabled={full}
                  />
                  <Button
                    variant="outline"
                    size="lg"
                    className="h-11 shrink-0"
                    disabled={!extraDraft.trim() || full || extraDraft.trim() === extraMissing}
                    onClick={() => void addManual(extraDraft)}
                  >
                    추가
                  </Button>
                </div>
                {unavailable.length > 0 ? (
                  <MissingPackage name={unavailable.join(', ')} />
                ) : extraMissing ? (
                  <MissingPackage name={extraMissing} />
                ) : noDataExtra ? (
                  <NoSimilarWarning
                    name={noDataExtra}
                    confirmLabel="그래도 추가"
                    onConfirm={() => void addManual(noDataExtra, true)}
                    onCancel={() => setNoDataExtra(null)}
                  />
                ) : extraError ? (
                  <p role="alert" className="text-base text-destructive">
                    {extraError}
                  </p>
                ) : (
                  full && (
                    <p className="text-sm text-muted-foreground">
                      이미 {MAX_COMPARISON}개를 골랐어요. 오른쪽에서 하나를 빼면 새로 넣을 수
                      있어요.
                    </p>
                  )
                )}
              </div>

              <div className="flex flex-col gap-4">
                <h2 className="text-xl font-semibold tracking-tight">비슷한 패키지</h2>

                {/*
                빈 상태가 두 갈래다. **아직 계산되지 않은 것**(`NO_DATA`)과 **관련 후보가 없는 것**은
                사용자가 할 일이 다르다. 앞은 기다리면 되고 뒤는 직접 추가해야 한다.
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
                  <div className="flex flex-col gap-3">
                    <CandidateGrid candidates={candidates} picked={picked} onToggle={toggle} />
                    {/*
                    모델 이름은 기본 화면에서 의미가 없다(S15P21A506-443) — 라벨만 두고
                    실제 기준 설명과 모델 버전은 InfoDialog 로 옮긴다. 모델 버전을 완전히
                    지우지 않는 이유는 이 목록의 계보이기 때문이다(스냅샷 날짜를 쓰지
                    않기로 했다) — 다음 주에 목록이 바뀌었을 때 화면이 바뀐 것인지 모델이
                    바뀐 것인지 알 수 없게 된다.
                  */}
                    {similar.data?.model_ver && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-base text-muted-foreground">후보를 고른 기준</span>
                        <InfoDialog label="후보를 고른 기준 안내" title="후보를 고른 기준">
                          <p>
                            기능이 유사한 패키지 중 하위 모듈·보완재·보관된 저장소를 제외한 인기
                            패키지를 최대 {VISIBLE_CANDIDATES}개까지 보여줍니다.
                          </p>
                        </InfoDialog>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>

            {/* 선택 패널 — 무엇을 골랐는지 늘 보이게 오른쪽에 붙인다. 2단계에서 옆으로 스며 나온다 */}
            <SelectionPanel
              selected={selected}
              max={MAX_COMPARISON}
              limitHit={limitHit}
              creating={creating}
              lastAdded={lastAdded && picked.includes(lastAdded) ? lastAdded : null}
              onRemove={toggle}
              onCreate={() => void createReport()}
            />
          </>
        )}
      </div>

      <LoadingOverlay open={creating} title="보고서를 준비하고 있어요" steps={CREATE_STEPS} />
    </div>
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
