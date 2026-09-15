import { Loader2Icon, XIcon } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'

import { fetchPackageSearch } from '@/api/endpoints'
import { useSimilarPackages } from '@/api/queries'
import { MAX_NAMES } from '@/api/types'
import { paths } from '@/app/routes'
import { LoadingOverlay } from '@/components/common/loading-overlay'
import { Button } from '@/components/ui/button'
import { CandidateGrid } from '@/routes/analyze/candidate-grid'
import { PackageSearch } from '@/routes/analyze/package-search'
import { StepCard, StepConnector, type StepState } from '@/routes/analyze/step-card'
import { cn } from '@/lib/utils'

/** 기준 패키지를 포함한 비교 대상 수(IA 1.4). 서버의 `names` 상한과 같은 값이다. */
const MAX_COMPARISON = MAX_NAMES

/**
 * 화면에 깔 후보 수.
 *
 * 서버는 `limit` 만큼(기본 20) 주지만 다 펼치지 않는다. 고를 수 있는 자리가
 * `MAX_COMPARISON - 1` 개뿐이라, 후보를 스무 개 늘어놓으면 고르는 일이 아니라
 * 훑는 일이 된다. 늘리려면 이 숫자만 바꾸면 된다.
 */
const VISIBLE_CANDIDATES = 2

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
  const nav = useLocation().state as { prefill?: string; restore?: string[] } | null
  const restore = nav?.restore

  const [draft, setDraft] = useState(nav?.prefill ?? restore?.[0] ?? '')
  const [extraError, setExtraError] = useState<string | null>(null)
  const [picked, setPicked] = useState<string[]>(restore?.slice(1) ?? [])
  const [limitHit, setLimitHit] = useState(false)
  const [extraDraft, setExtraDraft] = useState('')
  const [creating, setCreating] = useState(false)

  /**
   * 확인을 요청한 이름. **확정된 기준이 아니다.**
   *
   * 존재 확인과 후보 조회를 <b>한 번에</b> 한다 — 유사 패키지 응답이 이름이 없으면
   * `not_found` 로 알려주기 때문이다. 존재만 보려고 따로 한 번 더 부르면 왕복이 두 번이 되고,
   * 두 응답 사이에 이름이 사라지는 경우까지 다뤄야 한다.
   */
  const [submitted, setSubmitted] = useState<string | null>(nav?.prefill ?? restore?.[0] ?? null)

  const similar = useSimilarPackages(submitted ?? '')

  /** 이름 자체가 없는 경우. 후보가 아직 없는 것(`NO_DATA`)과 다르다. */
  const missing =
    similar.data && similar.data.not_found.length > 0 ? similar.data.not_found[0] : null

  const base = submitted && similar.data && !missing ? submitted : null
  // isPending 만 보면 실패 후 재조회(isRefetching) 동안 스피너·비활성화가 안 걸린다 — isFetching 은 둘 다 포함
  const checking = Boolean(submitted) && similar.isFetching

  const error = missing
    ? `npm 레지스트리에서 ${missing} 을(를) 찾지 못했습니다. 철자를 확인해 주세요.`
    : similar.error
      ? '후보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'
      : null

  /**
   * 서버는 `limit` 만큼 주지만 화면에는 일부만 깐다.
   *
   * **기본 선택을 하지 않는다.** 고를 자리가 두 개인데 두 개를 미리 켜 두면 고르는 단계가
   * 사라진다 — 사용자는 자기가 고르지 않은 조합으로 보고서를 받는다.
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
   */
  async function addManual(name: string) {
    const q = name.trim()
    setExtraError(null)
    if (!q) return
    if (selected.includes(q)) {
      setExtraError('이미 비교 대상에 있습니다.')
      return
    }
    if (full) {
      setExtraError(`${MAX_COMPARISON}개를 이미 골랐습니다. 하나를 먼저 해제해 주세요.`)
      return
    }

    try {
      const found = await fetchPackageSearch(q, 5)
      if (!found.items.includes(q)) {
        setExtraError(`npm 레지스트리에서 ${q} 을(를) 찾지 못했습니다.`)
        return
      }
    } catch {
      setExtraError('확인에 실패했습니다. 잠시 후 다시 시도해 주세요.')
      return
    }

    setPicked((prev) => [...prev, q])
    setExtraDraft('')
  }

  /**
   * 보고서 생성. 비교 대상을 확정하고 리포트 id 를 받아 이동한다.
   *
   * **비교 대상은 주소에 싣는다**(`?names=`). 라우터 state 로만 넘기면 그 링크를 받은
   * 사람에게는 state 가 없어 보고서가 조용히 다른 조합으로 떨어진다(S15P21A506-187).
   *
   * 미해결: id 발급 주체. 지금은 서버 왕복을 흉내 내고 draft 로 들어간다.
   * 실패하면 오버레이를 걷고 이 화면에 남아 선택을 잃지 않게 해야 한다.
   */
  async function createReport() {
    if (!base) return
    setCreating(true)
    await new Promise((r) => setTimeout(r, CREATE_MS))
    navigate(paths.report('draft', selected))
  }

  /*
    인트로에서 이름을 치고 넘어온 경우와 보고서에서 되돌아온 경우는 `submitted` 의 초기값이
    처리한다 — 조회가 곧 존재 확인이라 도착하자마자 2단계가 열린다.

    예전에는 effect 안에서 확인을 한 번 돌렸는데, 그러면 첫 렌더 뒤에 상태가 또 바뀌어
    화면이 두 번 그려지고 "왜 잠깐 1단계가 보이지" 가 생긴다.
  */

  const step1: StepState = base ? 'done' : 'active'

  return (
    <div className="flex flex-col gap-8 py-4">
      <header className="mx-auto flex w-full max-w-5xl flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">패키지 분석</h1>
        <p className="text-sm text-muted-foreground">
          기준이 될 npm 패키지 하나를 입력하면, 관련 후보를 찾아 최대 {MAX_COMPARISON}개까지 나란히
          놓습니다.
        </p>
      </header>

      {/*
        하단 고정 바가 마지막 콘텐츠 위를 덮지 않도록 바 높이만큼 자리를 비워 둔다.
        비워 두지 않으면 직접 추가 입력이 바 밑에 깔려 클릭이 바에 먹힌다.
      */}
      <ol className={cn('mx-auto flex w-full max-w-5xl flex-col', base && 'pb-28')}>
        {/* ① 기준 패키지 — 하나만 받는다 */}
        <StepCard
          index={1}
          title="기준 패키지"
          state={step1}
          summary={
            base && (
              <span className="flex items-center gap-2">
                <span className="font-mono font-medium">{base}</span>
                <span className="text-base text-muted-foreground">npm에서 확인됨</span>
              </span>
            )
          }
          onEdit={resetBase}
        >
          <div className="flex flex-col gap-3">
            <div className="flex gap-2">
              <PackageSearch
                value={draft}
                onChange={(v) => {
                  setDraft(v)
                  /*
                    오류는 이제 상태가 아니라 조회 결과에서 파생된다. 지우려면 "무엇을
                    확인했는지" 를 비워야 한다 — 그래야 조회가 꺼지고 문구도 함께 사라진다.

                    이미 확인된 기준이 있으면 건드리지 않는다. 그때 입력창은 2단계를
                    연 뒤에도 남아 있는 것이라, 글자를 고쳤다고 확정한 기준을 날리면 안 된다.
                  */
                  if (missing) setSubmitted(null)
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
                    확인 중
                  </>
                ) : (
                  '패키지 확인'
                )}
              </Button>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <p className="text-base text-muted-foreground">
              버전은 여기서 고르지 않습니다. 보고서 안에서 선택합니다.
            </p>
          </div>
        </StepCard>

        {/* ②③ 은 기준 패키지가 확인된 뒤에야 아래로 붙는다 */}
        {base && (
          <>
            <StepConnector active />
            <StepCard index={2} title="후보 선택" state="active" className="animate-oss-stack">
              <div className="flex flex-col gap-6">
                <div className="flex flex-col gap-1">
                  <h3 className="text-xl font-semibold tracking-tight">
                    비교할 패키지를 선택하세요
                  </h3>
                  <p className="text-base text-muted-foreground">
                    설명이 가까운 후보입니다. 기준 패키지를 포함해 총 {MAX_COMPARISON}개까지
                    비교합니다. 완전한 대체 관계나 품질 순위를 의미하지 않습니다.
                  </p>
                </div>

                {/*
                  빈 상태가 두 갈래다.

                  **아직 계산되지 않은 것**(`NO_DATA`)과 **관련 후보가 없는 것**은 사용자가 할
                  일이 다르다. 앞은 기다리면 되고 뒤는 직접 추가해야 한다. 같은 문구로 그리면
                  적재 직후 "이 패키지는 대체재가 없다" 로 읽힌다.
                */}
                {candidates.length === 0 ? (
                  <div className="rounded-2xl border border-dashed px-6 py-10 text-center">
                    <p>
                      {similar.data?.data_status === 'NO_DATA'
                        ? '아직 후보를 계산하지 않았습니다.'
                        : '관련 후보를 찾지 못했습니다.'}
                    </p>
                    <p className="mt-1 text-base text-muted-foreground">
                      {similar.data?.data_status === 'NO_DATA'
                        ? '주간 배치가 돌면 채워집니다. 그동안은 아래에서 직접 추가할 수 있습니다.'
                        : '비교할 패키지를 아래에서 직접 추가하거나 다른 기준 패키지로 시작해 보세요.'}
                    </p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    <CandidateGrid candidates={candidates} picked={picked} onToggle={toggle} />
                    {/*
                      모델 버전이 이 목록의 계보다(스냅샷 날짜를 쓰지 않기로 했다).
                      어느 모델이 고른 것인지 적어 두지 않으면, 다음 주에 목록이 바뀌었을 때
                      화면이 바뀐 것인지 모델이 바뀐 것인지 알 수 없다.
                    */}
                    {similar.data?.model_ver && (
                      <p className="font-mono text-base text-muted-foreground">
                        판정 모델 {similar.data.model_ver}
                      </p>
                    )}
                  </div>
                )}

                {limitHit && (
                  <p className="text-base text-amber-700">
                    {MAX_COMPARISON}개를 이미 골랐습니다. 하나를 해제한 뒤 다시 선택해 주세요.
                  </p>
                )}

                {/* 직접 추가 (IA 6.1) */}
                <div className="flex flex-col gap-4 rounded-2xl border bg-muted/25 p-6">
                  <div className="flex flex-col gap-1">
                    <h4 className="text-base font-semibold">찾는 패키지가 없나요?</h4>
                    <p className="text-base text-muted-foreground">
                      {full
                        ? `최대 ${MAX_COMPARISON}개가 선택되었습니다. 다른 패키지를 추가하려면 선택한 후보 1개를 먼저 해제하세요.`
                        : '이름을 알고 있다면 직접 추가할 수 있습니다. 후보 순위는 바뀌지 않습니다.'}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <PackageSearch
                      value={extraDraft}
                      onChange={(v) => {
                        setExtraDraft(v)
                        if (extraError) setExtraError(null)
                      }}
                      onSubmit={(v) => void addManual(v)}
                      placeholder="npm 패키지명"
                      ariaLabel="직접 추가할 패키지명"
                    />
                    <Button
                      variant="outline"
                      size="lg"
                      className="h-11 shrink-0"
                      disabled={!extraDraft.trim()}
                      onClick={() => void addManual(extraDraft)}
                    >
                      패키지 추가
                    </Button>
                  </div>
                  {extraError && <p className="text-base text-destructive">{extraError}</p>}
                </div>
              </div>
            </StepCard>
          </>
        )}
      </ol>

      {/* 하단 고정 선택 바 (IA 6.4) */}
      {base && (
        <div className="sticky bottom-0 z-20 -mx-10 -mt-8 border-t bg-background/95 px-10 py-4 backdrop-blur">
          <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-5 gap-y-3">
            <span className="text-base font-medium">선택한 비교 대상</span>
            <span className="font-mono text-base tabular-nums">
              {selected.length} / {MAX_COMPARISON} 선택됨
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {selected.map((n, i) => (
                <Chip
                  key={n}
                  name={n}
                  fixed={i === 0}
                  onRemove={i === 0 ? undefined : () => toggle(n)}
                />
              ))}
            </div>
            <Button
              size="lg"
              className="ml-auto"
              disabled={creating}
              onClick={() => void createReport()}
            >
              분석 시작
            </Button>
          </div>
        </div>
      )}

      <LoadingOverlay open={creating} title="보고서를 만들고 있습니다" steps={CREATE_STEPS} />
    </div>
  )
}

/** 기준 패키지는 해제 버튼을 주지 않는다(IA 6.3). */
function Chip({ name, fixed, onRemove }: { name: string; fixed: boolean; onRemove?: () => void }) {
  return (
    <span
      className={cn(
        'flex items-center gap-2 rounded-lg border px-3 py-1.5 font-mono text-base',
        fixed && 'bg-muted/60',
      )}
    >
      {name}
      {fixed ? (
        <span className="font-sans text-base text-muted-foreground">기준</span>
      ) : (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`${name} 비교 대상에서 빼기`}
          className="-mr-1 rounded p-0.5 text-muted-foreground hover:text-foreground"
        >
          <XIcon className="size-3.5" aria-hidden />
        </button>
      )}
    </span>
  )
}

/** 보고서 생성 왕복 흉내. 실제로는 id 발급 + 사전 집계 조회다. */
const CREATE_MS = 2700

const CREATE_STEPS = ['비교 대상 확정', '사전 집계 조회', '보고서 준비'] as const
