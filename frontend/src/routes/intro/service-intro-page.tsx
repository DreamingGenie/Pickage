import { CheckIcon, SearchIcon } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'

import { paths } from '@/app/routes'
import { LineChart } from '@/components/charts/line-chart'
import { SAMPLE_ECOSYSTEM } from '@/components/charts/sample'
import { parsePackageInput } from '@/lib/package'
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
      <section className="relative -mx-10 -mt-8 overflow-hidden border-b px-10 pt-24 pb-20">
        <HeroBackdrop />

        <div className="relative mx-auto flex max-w-2xl flex-col items-center gap-6 text-center">
          <h1 className="text-4xl leading-[1.12] font-bold tracking-[-0.02em] text-balance">
            판단은 직접,
            <br />
            근거는 여기서
          </h1>
          <p className="max-w-lg text-base leading-relaxed text-muted-foreground">
            공개 npm 생태계에서 관측된 변화와 정확한 버전의 공식 자료를 모아 최대 3개 패키지를
            나란히 놓습니다. 어느 쪽이 낫다는 판정은 하지 않습니다.
          </p>

          <form
            className="relative mt-2 w-full max-w-xl"
            onSubmit={(e) => {
              e.preventDefault()
              start(draft)
            }}
          >
            <input
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value)
                if (error) setError(null)
              }}
              placeholder="npm 패키지명을 입력하세요"
              aria-label="분석할 npm 패키지명"
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'intro-input-error' : undefined}
              className="h-14 w-full rounded-full border bg-background pr-16 pl-7 text-base shadow-[0_2px_14px_-4px_rgba(15,23,42,0.14)] transition-shadow outline-none placeholder:text-muted-foreground/70 focus-visible:ring-[3px] focus-visible:ring-ring/40 aria-invalid:border-destructive"
            />
            <button
              type="submit"
              disabled={!draft.trim()}
              aria-label="분석 시작"
              className="absolute top-2 right-2 grid size-10 place-items-center rounded-full bg-primary text-primary-foreground transition-opacity outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-35"
            >
              <SearchIcon className="size-[18px]" />
            </button>
          </form>

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
            desc="패키지명을 입력하면 npm 레지스트리에 실제로 있는지 확인합니다. 버전은 여기서 고르지 않습니다."
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

          {/* 2 — 체크가 순서대로 찍히고 카운트가 올라온다 */}
          <Step
            {...steps.props(1)}
            keyword="후보 선택"
            desc="설명이 가까운 후보를 최대 3개까지 보여줍니다. 기준 패키지를 포함해 최종 비교는 총 3개까지라, 후보 중 최대 2개를 고를 수 있습니다. 모두 미선택 상태로 시작하니 직접 고르거나 이름으로 추가하세요."
          >
            <div className="flex flex-col gap-1.5">
              {[
                { name: 'winston', tag: '해제 불가', picked: true, delay: 0 },
                { name: 'pino', tag: '1위', picked: false, delay: 0 },
                { name: 'bunyan', tag: '2위', picked: false, delay: 0 },
                { name: 'log4js', tag: '3위', picked: false, delay: 0 },
              ].map((c) => (
                <div
                  key={c.name}
                  className={`flex items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 transition-colors duration-300 ${
                    c.picked ? 'group-data-[on=true]:border-foreground/45' : ''
                  }`}
                >
                  {/* 빈 칸 → 검게 채워짐 → 체크 순서로 보이도록 칠과 체크를 따로 재생한다 */}
                  <span className="relative grid size-3.5 shrink-0 place-items-center rounded-[3px] border">
                    {c.picked && (
                      <>
                        <span
                          className="absolute -inset-px rounded-[3px] bg-foreground opacity-0 group-data-[on=true]:animate-oss-pop"
                          style={{ animationDelay: `${c.delay}ms` }}
                        />
                        <CheckIcon
                          className="relative size-2.5 text-background opacity-0 group-data-[on=true]:animate-oss-pop"
                          style={{ animationDelay: `${c.delay + 130}ms` }}
                          strokeWidth={3}
                        />
                      </>
                    )}
                  </span>
                  <span className="font-mono text-base">{c.name}</span>
                  <span className="ml-auto text-base text-muted-foreground">{c.tag}</span>
                </div>
              ))}
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
            desc="생태계 변화와 기능 비교를 보고, 셀마다 확인된 근거를 펼쳐 봅니다."
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
    <div aria-hidden className="pointer-events-none absolute inset-0">
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
  children,
}: StepProps & { keyword: string; desc: string; children: ReactNode }) {
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
        <p className="text-base leading-relaxed text-muted-foreground">{desc}</p>
      </div>

      <div key={runKey} className="mt-auto rounded-lg border bg-muted/50 p-3">
        {children}
      </div>
    </li>
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
