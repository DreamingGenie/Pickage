import { CheckIcon, SearchIcon, TriangleAlertIcon, type LucideIcon } from 'lucide-react'
import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'

import { paths } from '@/app/routes'
import { LineChart } from '@/components/charts/line-chart'
import { SAMPLE_ECOSYSTEM } from '@/components/charts/sample'
import { parsePackageInput } from '@/lib/package'
import { PackageSearch } from '@/routes/analyze/package-search'
import { deltaOf, dependentsLineOf } from '@/routes/report/ecosystem/adapter'
import { EcosystemView } from '@/routes/report/ecosystem/ecosystem-view'
import {
  EXAMPLE_COMPARISON_PACKAGES,
  EXAMPLE_FEATURE_ROWS,
  PRESET_PACKAGES,
  VERDICT_LABEL,
  type Verdict,
} from '@/routes/intro/intro-content'

/**
 * v1-OSS-00-service-intro
 *
 * IA 4.1 순서: Hero → 사용 방법 3단계 → 분석 결과 예시 → 관측 범위와 판단 한계
 * 카피 원칙: 구상안이 산출한다고 명시한 것만 약속한다.
 * 기술 우열 판단, 자동 최종 추천, 외부 원문 링크는 산출물이 아니므로 문구에 넣지 않는다.
 */
const STEP_COUNT = 3
/** 2단계 예시의 비교 후보. 기준 패키지(winston)는 따로 그린다. */
const DEMO_CANDIDATES = ['pino', 'bunyan', 'log4js'] as const
/**
 * 3단계 예시에 넣는 Dependents 증감. 아래 "분석 결과 예시" 카드가 보여 주는 값과 같은 계산이다
 * (기준 패키지의 Total 선, 표시 구간의 처음과 끝). 손으로 적어 두면 두 곳이 어긋난다.
 */
const SAMPLE_BASE = SAMPLE_ECOSYSTEM.packages[0]
const SAMPLE_DEPENDENTS_DELTA =
  deltaOf(
    dependentsLineOf(
      SAMPLE_BASE.key,
      SAMPLE_ECOSYSTEM.dependentsByMajor[SAMPLE_BASE.key] ?? [],
      [],
    ),
  )?.value ?? null
/** 한 카드가 켜져 있는 시간. 가장 긴 시퀀스(3번, 약 1.5초)보다 넉넉히 잡는다. */
const STEP_CYCLE_MS = 2800

export function ServiceIntroPage() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const steps = useStepCycle()

  function start(raw: string) {
    const parsed = parsePackageInput(raw)
    if (!parsed.ok) {
      setError(parsed.reason)
      return
    }
    navigate(paths.analyze, { state: { prefill: raw.trim() } })
  }

  return (
    <div className="flex flex-col gap-28 pb-16">
      {/* ── Hero ───────────────────────────────────────────────── */}
      {/*
        뷰포트 전폭으로 편다. 예전에는 `-mx-10` 으로 컨테이너 패딩만 벗어나서, 화면이
        컨테이너 최대 폭(1440px)보다 넓어지면 히어로 좌우가 비어 보였다.
        `left-1/2 w-screen -translate-x-1/2` 는 컨테이너가 화면 가운데에 있다는 전제로
        어떤 폭에서도 양끝까지 닿는다. 세로 스크롤바 때문에 생기는 넘침은 AppLayout 이 자른다.

        **`overflow-hidden` 을 여기 두지 않는다.** 배경 도형을 자르려고 예전에 걸어 둔 것인데, 자동완성
        목록이 히어로 아래로 내려오면 그것까지 잘려 목록 끝이 사라졌다. 도형만 `HeroBackdrop` 안에서
        자른다. `z-10` 은 `transform` 이 만든 쌓임 맥락 때문에 필요하다 — 없으면 이 아래의 카드
        (`opacity` 로 쌓임 맥락이 생긴다)가 목록 위로 올라온다.
      */}
      <section className="relative left-1/2 z-10 -mt-8 w-screen -translate-x-1/2 border-b px-10 pt-24 pb-20">
        <HeroBackdrop />

        <div className="relative mx-auto flex max-w-3xl flex-col items-center gap-6 text-center">
          <h1 className="text-3xl leading-[1.12] font-bold tracking-[-0.02em] text-balance sm:text-4xl sm:whitespace-nowrap">
            패키지 선택에, 확인할 근거를
          </h1>
          {/*
            제품 책임자가 정한 문구다(S15P21A506-404). "추천" 이 아니라 "제안" 이다 — 서비스는 유사 후보를
            내놓을 뿐 우열이나 최종 선택을 권하지 않는다(IA 1-12). 그 한계는 페이지 아래 "관측 범위와 판단
            한계" 가 밝힌다. 줄은 쉼표·마침표 뒤에서만 바뀐다(`Clauses`).
          */}
          <div className="flex flex-col gap-2 text-base leading-relaxed text-muted-foreground">
            <p>
              <Clauses>
                {[
                  '유사한 기능을 가진 패키지를 제안하고,',
                  '믿을 수 있는 근거와 함께 분석을 제공합니다.',
                ]}
              </Clauses>
            </p>
            <p>
              <Clauses>{['PDF로 다운로드 받아 팀원들과 공유하세요.']}</Clauses>
            </p>
          </div>

          <div className="relative mt-2 w-full max-w-xl">
            <PackageSearch
              value={draft}
              onChange={(v) => {
                setDraft(v)
                if (error) setError(null)
              }}
              onSubmit={start}
              placeholder="npm 패키지명을 입력하세요"
              ariaLabel="분석할 npm 패키지명"
              icon={false}
              invalid={Boolean(error)}
              describedBy={error ? 'intro-input-error' : undefined}
              className="w-full"
              inputClassName="h-14 w-full rounded-full pr-16 pl-7 text-base shadow-[0_2px_14px_-4px_rgba(15,23,42,0.14)] placeholder:text-muted-foreground/70 aria-invalid:border-destructive"
            />
            <button
              type="button"
              disabled={!draft.trim()}
              aria-label="분석 시작"
              onClick={() => start(draft)}
              className="absolute top-2 right-2 grid size-10 place-items-center rounded-full bg-primary text-primary-foreground transition-opacity outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-35"
            >
              <SearchIcon className="size-[18px]" />
            </button>
          </div>
          {error && (
            <p id="intro-input-error" className="-mt-3 text-sm text-destructive">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center justify-center gap-2">
            <span className="text-xs text-muted-foreground">예시로 둘러보기</span>
            {PRESET_PACKAGES.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => start(name)}
                className="rounded-full border bg-background/70 px-3 py-1 font-mono text-xs backdrop-blur-sm transition-colors hover:border-foreground/40 hover:bg-background"
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* ── 사용 방법 3단계 ────────────────────────────────────── */}
      <section className="flex flex-col gap-9">
        <div className="flex flex-col gap-2">
          <h2 className="text-2xl font-semibold tracking-tight">사용 방법</h2>
          <p className="text-sm text-muted-foreground">세 단계면 보고서까지 갑니다.</p>
        </div>

        <ol className="grid gap-6 lg:grid-cols-3">
          {/* 1 — 타이핑 후 확인 배지가 뜬다 */}
          <Step
            {...steps.props(0)}
            keyword="패키지 입력"
            desc={['고민하고 계신 패키지를 입력해 주세요']}
            note={
              <StepNote tone="warn" icon={TriangleAlertIcon}>
                <Clauses>{['수집된 데이터가 있어야,', '결과를 확인할 수 있습니다.']}</Clauses>
              </StepNote>
            }
          >
            <div className="flex flex-col gap-2">
              <div className="flex h-9 items-center rounded-md border bg-background px-3">
                <span
                  className="inline-block w-0 overflow-hidden align-middle font-mono text-base whitespace-nowrap group-data-[on=true]:animate-oss-type"
                  style={{ '--oss-type-w': '7ch' } as React.CSSProperties}
                >
                  winston
                </span>
                <span className="ml-[2px] inline-block h-4 w-px shrink-0 bg-foreground opacity-0 group-data-[on=true]:animate-oss-caret" />
              </div>
              <div
                className="flex items-center gap-1.5 text-base text-muted-foreground opacity-0 group-data-[on=true]:animate-oss-rise"
                style={{ animationDelay: '840ms' }}
              >
                <span className="grid size-3.5 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                  <CheckIcon className="size-2.5" strokeWidth={3} />
                </span>
                npm에서 확인됨
              </div>
            </div>
          </Step>

          {/* 2 — 기준 패키지가 위, 후보는 한 줄. 체크가 찍히고 카운트가 올라온다 */}
          <Step
            {...steps.props(1)}
            keyword="후보 선택"
            desc={['비교하실 패키지를 선택하세요.', '총 2개 선택하실 수 있습니다.']}
            note={
              <StepNote icon={SearchIcon}>
                <Clauses>{['찾는 패키지가 후보에 없다면,', '검색해서 추가하세요.']}</Clauses>
              </StepNote>
            }
          >
            <div className="flex flex-col gap-1.5">
              {/* 기준 패키지 — 해제할 수 없다 */}
              <div className="flex items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 transition-colors duration-300 group-data-[on=true]:border-foreground/45">
                <DemoCheck picked />
                <span className="font-mono text-base">winston</span>
                <span className="ml-auto text-base text-muted-foreground">해제 불가</span>
              </div>
              {/*
                후보 — 모두 미선택으로 시작한다. **칸을 균등하게 나눈다.** 내용 폭대로 늘어놓으면 칩이
                왼쪽에 몰리고 오른쪽이 비는데, 그 빈 폭은 화면 폭마다 달라 고정값으로 메울 수 없다.
                그래서 카드 폭(container query)에 따라 3등분하고, 3등분이 안 들어갈 만큼 좁으면 2등분하되
                홀로 남는 마지막 칩이 줄 전체를 채우게 한다 — 어느 폭에서도 오른쪽이 비지 않는다.
              */}
              <div className="@container">
                <div className="grid grid-cols-2 gap-1 @min-[18rem]:grid-cols-3 @max-[18rem]:[&>:last-child:nth-child(odd)]:col-span-2">
                  {DEMO_CANDIDATES.map((name) => (
                    <div
                      key={name}
                      className="flex items-center justify-center gap-1.5 rounded-md border bg-background px-1.5 py-1.5"
                    >
                      <DemoCheck />
                      <span className="font-mono text-base">{name}</span>
                    </div>
                  ))}
                </div>
              </div>
              <span
                className="mt-0.5 text-base text-muted-foreground tabular-nums opacity-0 group-data-[on=true]:animate-oss-rise"
                style={{ animationDelay: '700ms' }}
              >
                1 / 3 선택됨
              </span>
            </div>
          </Step>

          {/* 3 — 그래프가 좌에서 우로 그려지고 판정이 하나씩 올라온다 */}
          <Step
            {...steps.props(2)}
            keyword="보고서 확인"
            desc={['생태계 변화와 기능 비교를 보고,', '셀마다 확인된 근거를 펼쳐 봅니다.']}
          >
            <div className="flex flex-col gap-2.5">
              <div className="rounded-md border bg-background px-2.5 pt-2 pb-1">
                <div className="[clip-path:inset(0_100%_0_0)] group-data-[on=true]:animate-oss-wipe">
                  <LineChart
                    series={[
                      {
                        ...SAMPLE_ECOSYSTEM.series.downloads[0],
                        points: SAMPLE_ECOSYSTEM.series.downloads[0].points.slice(-26),
                      },
                    ]}
                    height={34}
                    bare
                    ariaLabel="다운로드 추이 예시"
                  />
                </div>
              </div>
              {SAMPLE_DEPENDENTS_DELTA !== null && (
                <div
                  className="flex items-baseline justify-between gap-3 opacity-0 group-data-[on=true]:animate-oss-rise"
                  style={{ animationDelay: '500ms' }}
                >
                  <span className="text-base text-muted-foreground">Dependents 증감</span>
                  <span className="font-mono text-lg leading-none font-semibold text-rose-600 tabular-nums">
                    {SAMPLE_DEPENDENTS_DELTA > 0 ? '+' : SAMPLE_DEPENDENTS_DELTA < 0 ? '−' : '±'}
                    {Math.abs(SAMPLE_DEPENDENTS_DELTA).toLocaleString()}
                  </span>
                </div>
              )}
              <div className="flex flex-wrap gap-1">
                {(['SUPPORTED', 'CONDITIONALLY_SUPPORTED', 'UNCONFIRMED'] as const).map((v, i) => (
                  <span
                    key={v}
                    className="opacity-0 group-data-[on=true]:animate-oss-rise"
                    style={{ animationDelay: `${700 + i * 130}ms` }}
                  >
                    <VerdictPill verdict={v} />
                  </span>
                ))}
              </div>
              <span
                className="text-base text-muted-foreground opacity-0 group-data-[on=true]:animate-oss-rise"
                style={{ animationDelay: '1120ms' }}
              >
                셀을 누르면 근거 발췌가 열립니다
              </span>
            </div>
          </Step>
        </ol>
      </section>

      {/* ── 분석 결과 예시 ─────────────────────────────────────── */}
      <section className="flex flex-col gap-7">
        <div className="flex flex-col gap-2">
          <h2 className="text-2xl font-semibold tracking-tight">분석 결과 예시</h2>
          <p className="text-sm text-muted-foreground">
            보고서는 두 장입니다. 둘 다 winston · pino · bunyan 조합의 예시이며, 기능 비교표는 이
            서비스가 지금 만든 결과가 아니라 그 세 패키지를 실제로 검증한 결과를 옮긴 것입니다.
          </p>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.35fr_1fr]">
          {/* 1페이지 */}
          <article className="flex flex-col gap-6 rounded-2xl border bg-muted/30 p-7">
            <header className="flex items-baseline justify-between gap-3">
              <h3 className="text-base font-semibold">1. 생태계 변화</h3>
              <span className="font-mono text-xs text-muted-foreground">카드를 눌러보세요</span>
            </header>
            <EcosystemView model={SAMPLE_ECOSYSTEM} compactChart />
          </article>

          {/* 2페이지 */}
          <article className="flex flex-col gap-6 rounded-2xl border bg-muted/30 p-7">
            <header className="flex items-baseline justify-between gap-3">
              <h3 className="text-base font-semibold">2. 기능 비교</h3>
              <span className="font-mono text-xs text-muted-foreground">정확한 버전 기준</span>
            </header>

            <div className="flex flex-wrap gap-1.5">
              {EXAMPLE_COMPARISON_PACKAGES.map((p) => (
                <span key={p} className="rounded border px-1.5 py-0.5 font-mono text-base">
                  {p}
                </span>
              ))}
            </div>

            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="pb-3 text-left font-normal">확인 항목</th>
                  {EXAMPLE_COMPARISON_PACKAGES.map((p) => (
                    <th key={p} className="pb-3 text-left font-mono font-normal">
                      {p.split('@')[0]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {EXAMPLE_FEATURE_ROWS.map((row) => (
                  <tr key={row.label} className="border-t align-top">
                    <td className="py-3 pr-3 text-muted-foreground">{row.label}</td>
                    {row.cells.map((cell, i) => (
                      <td key={i} className="py-3">
                        <div className="flex flex-col gap-0.5">
                          <VerdictPill verdict={cell.verdict} />
                          {cell.note && (
                            <span className="font-mono text-base leading-tight text-muted-foreground">
                              {cell.note}
                            </span>
                          )}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>

            <p className="border-t pt-3 text-base leading-relaxed text-muted-foreground">
              <strong className="font-medium text-foreground">미확인</strong>은 미지원이 아닙니다.
              해당 버전 자료에서 확인되지 않았다는 뜻이고, 무엇을 어디까지 찾아봤는지 함께
              보여줍니다. <strong className="font-medium text-foreground">미지원</strong>은 공식
              부정 근거가 있을 때만 씁니다.
            </p>
          </article>
        </div>
      </section>

      {/* ── 관측 범위와 판단 한계 (IA 4.1-5·4.2 "범위 안내") ────── */}
      <section className="flex flex-col gap-3 rounded-2xl border border-dashed p-7">
        <h2 className="text-xl font-semibold tracking-tight">관측 범위와 판단 한계</h2>
        <ul className="flex flex-col gap-2 text-base leading-relaxed text-muted-foreground">
          <li>
            후보의 유사도 순위는 설명·키워드가 가까운 정도이며, 기술 품질이나 우열 판정이 아닙니다.
            어느 쪽이 낫다는 판정은 하지 않습니다.
          </li>
          <li>다운로드 추이는 npm 공식 자료를 쌓아 둔 전 구간의 관측 범위입니다.</li>
          <li>
            버전 분포는 최신 DB Snapshot 기준일의 관측이며, 실제 설치 비중이나 요구조건 해석 결과가
            아닙니다.
          </li>
          <li>이 페이지의 수치와 그래프는 모두 예시이며, 실제 분석 결과가 아닙니다.</li>
        </ul>
      </section>
    </div>
  )
}

/** Capterra 계열의 각진 그라데이션 워시. 장식이며 의미를 전달하지 않는다. */
function HeroBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute inset-0"
        style={{
          background: 'linear-gradient(160deg, #eef4fc 0%, #f7fafd 42%, #ffffff 100%)',
        }}
      />
      <div
        className="absolute -top-32 left-1/2 h-[560px] w-[1100px] -translate-x-1/2 opacity-70"
        style={{
          clipPath: 'polygon(22% 0, 100% 18%, 74% 100%, 0 64%)',
          background: 'linear-gradient(120deg, #dce9fa 0%, #eff5fd 60%, #ffffff 100%)',
        }}
      />
      <div
        className="absolute -right-24 -bottom-20 h-[320px] w-[520px] opacity-60"
        style={{
          clipPath: 'polygon(0 34%, 100% 0, 100% 100%, 26% 100%)',
          background: 'linear-gradient(200deg, #e6eefb 0%, #ffffff 100%)',
        }}
      />
    </div>
  )
}

interface StepProps {
  index: number
  on: boolean
  runKey: number
  onPin: () => void
  onUnpin: () => void
}

/**
 * 세 카드를 1 → 2 → 3 으로 자동 순환시킨다.
 * 호버하면 그 카드에 멈춘 채 같은 시퀀스를 반복하고, 벗어나면 그 자리에서 순환을 잇는다.
 * 모션을 끈 사용자에게는 순환 없이 세 카드를 모두 켜둔다.
 */
function useStepCycle() {
  const [reduced, setReduced] = useState(false)
  const [active, setActive] = useState(0)
  const [pinned, setPinned] = useState<number | null>(null)
  const [run, setRun] = useState(0)

  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const sync = () => setReduced(mq.matches)
    sync()
    mq.addEventListener('change', sync)
    return () => mq.removeEventListener('change', sync)
  }, [])

  useEffect(() => {
    if (reduced) return
    // pinned 가 바뀌면 타이머를 다시 깔아 시퀀스를 처음부터 재생한다.
    setRun((r) => r + 1)
    const id = setInterval(() => {
      setRun((r) => r + 1)
      if (pinned === null) setActive((a) => (a + 1) % STEP_COUNT)
    }, STEP_CYCLE_MS)
    return () => clearInterval(id)
  }, [pinned, reduced])

  const current = pinned ?? active

  return {
    props(index: number): StepProps {
      const on = reduced || index === current
      return {
        index: index + 1,
        on,
        // 켜질 때마다 key 가 바뀌어 리마운트되고, 그래서 애니메이션이 처음부터 다시 돈다.
        runKey: on ? run : -1,
        onPin: () => setPinned(index),
        onUnpin: () => {
          setActive(index)
          setPinned(null)
        },
      }
    },
  }
}

/**
 * 키워드를 가장 크게 두고, 그 아래에 해당 단계의 화면 조각을 보여준다.
 * 켜진 카드만 선명해지고, 나머지는 흑백으로 가라앉는다.
 * 애니메이션은 장식이며, 설명 문단이 같은 내용을 글로 담고 있다.
 */
function Step({
  index,
  on,
  runKey,
  onPin,
  onUnpin,
  keyword,
  desc,
  note,
  children,
}: StepProps & {
  keyword: string
  desc: readonly string[]
  note?: ReactNode
  children: ReactNode
}) {
  return (
    <li
      data-on={on}
      onMouseEnter={onPin}
      onMouseLeave={onUnpin}
      onFocus={onPin}
      onBlur={onUnpin}
      className="group flex flex-col gap-5 rounded-2xl border bg-background p-7 opacity-45 grayscale transition-[opacity,filter,border-color,box-shadow] duration-500 data-[on=true]:border-foreground/30 data-[on=true]:opacity-100 data-[on=true]:shadow-[0_2px_16px_-8px_rgba(15,23,42,0.25)] data-[on=true]:grayscale-0"
    >
      <div className="flex items-center gap-3">
        <span className="grid size-6 place-items-center rounded-full bg-foreground font-mono text-base text-background tabular-nums">
          {index}
        </span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-2xl leading-tight font-bold tracking-tight">{keyword}</h3>
        <p className="text-base leading-relaxed text-muted-foreground">
          <Clauses>{desc}</Clauses>
        </p>
      </div>

      {/* 예시 이미지와 그 아래 안내. 카드가 늘어나도 둘이 함께 바닥에 붙는다. */}
      <div className="mt-auto flex flex-col gap-3">
        <div key={runKey} className="rounded-lg border bg-muted/50 p-3">
          {children}
        </div>
        {note}
      </div>
    </li>
  )
}

/**
 * 문구를 **절 단위**로 끊어 준다. 각 절은 하나의 덩어리(`inline-block`)라 줄은 절과 절 사이, 곧
 * 마침표·쉼표 뒤에서만 바뀐다. 기본 줄나눔은 글자 수대로 아무 띄어쓰기에서나 끊어 "총 2개 선택하실 /
 * 수 있습니다." 처럼 뜻이 잘린다. 한 절이 칸보다 길 때만 띄어쓰기에서 나뉜다(`break-keep`).
 *
 * 절을 배열로 받는 이유: 어디서 끊길지가 문구의 일부라서, 문자열 하나에 두면 고치는 사람이 그
 * 사실을 놓친다.
 */
function Clauses({ children }: { children: readonly string[] }) {
  return (
    <>
      {children.map((clause, i) => (
        <Fragment key={clause}>
          {i > 0 && ' '}
          <span data-clause className="inline-block max-w-full break-keep">
            {clause}
          </span>
        </Fragment>
      ))}
    </>
  )
}

/** 예시 이미지 아래 한 줄 안내. 색만으로 뜻을 전하지 않도록 아이콘을 함께 둔다(IA 1-13). */
function StepNote({
  tone = 'muted',
  icon: Icon,
  children,
}: {
  tone?: 'muted' | 'warn'
  icon: LucideIcon
  children: ReactNode
}) {
  return (
    <p
      className={`flex items-start gap-1.5 text-sm leading-snug ${
        tone === 'warn' ? 'text-amber-700' : 'text-muted-foreground'
      }`}
    >
      <Icon aria-hidden className="mt-[5px] size-3.5 shrink-0" />
      <span>{children}</span>
    </p>
  )
}

/** 2단계 예시의 체크박스. picked 면 빈 칸 → 검게 채워짐 → 체크 순서로 재생한다. */
function DemoCheck({ picked = false }: { picked?: boolean }) {
  return (
    <span className="relative grid size-3.5 shrink-0 place-items-center rounded-[3px] border">
      {picked && (
        <>
          <span className="absolute -inset-px rounded-[3px] bg-foreground opacity-0 group-data-[on=true]:animate-oss-pop" />
          <CheckIcon
            className="relative size-2.5 text-background opacity-0 group-data-[on=true]:animate-oss-pop"
            style={{ animationDelay: '130ms' }}
            strokeWidth={3}
          />
        </>
      )}
    </span>
  )
}

/** 구상안 7.2 verdict 5종. 미확인은 실패색을 쓰지 않는다. */
function VerdictPill({ verdict }: { verdict: Verdict }) {
  const style: Record<Verdict, string> = {
    SUPPORTED: 'bg-emerald-50 text-emerald-700',
    CONDITIONALLY_SUPPORTED: 'bg-amber-50 text-amber-700',
    LIMITED_SUPPORT: 'bg-amber-50 text-amber-700',
    UNCONFIRMED: 'bg-muted text-muted-foreground',
    UNSUPPORTED: 'bg-red-50 text-red-700',
  }
  return (
    <span
      className={`w-fit rounded px-1.5 py-0.5 text-base font-medium ${style[verdict]}`}
      title={verdict}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  )
}
