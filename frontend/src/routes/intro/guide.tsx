import { CheckIcon } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

import { LineChart } from '@/components/charts/line-chart'
import { SAMPLE_ECOSYSTEM } from '@/components/charts/sample'
import type { CommunityTopic } from '@/api/types'
import { cn } from '@/lib/utils'
import { issueAccent } from '@/routes/report/community/accent'
import { CommunityIssueCard } from '@/routes/report/community/issue-card'
import { SAMPLE_COMMUNITY_RESULT } from '@/routes/report/community/sample'
import { CommunityThreadCard } from '@/routes/report/community/thread'
import { DEPENDENTS_TERM } from '@/routes/report/ecosystem/terms'

/**
 * 인트로의 "자세히 보기" — 옆으로 넘기는 여섯 장. 장마다 **무엇을 하는지(제목)·어떻게 하는지(한두 문장)**만
 * 적고, 실제 모습은 옆의 움직이는 예시 화면이 보여 준다. 1~6 번호를 누르면 그 장으로 바로 간다.
 * 따로 낱말 풀이를 두지 않는다 — 풀이가 필요 없도록 본문을 쓴다. 어려운 말은 본문 안에서 바로 푼다.
 *
 * 본문에 쓰는 말은 화면과 **같은 글자**로 쓴다 — 화면 문구가 바뀌면 여기도 함께 바꾼다.
 *
 * 뜻은 각 화면의 ⓘ 모달·주석과 구상안에서 옮겼다. 새로 지어내지 않는다.
 * 금지 표현(CLAUDE.md): 추천·순위·승자, 의존 수를 "사용처"·"N개 프로젝트가 사용" 으로 부르기.
 *
 * 그림은 실제 화면을 줄여 그린 것이고 숫자를 넣지 않는다 — 지어낸 숫자는 예시라도 오해를 만든다.
 * 그래프 한 개만 보고서 쪽 표본(`SAMPLE_ECOSYSTEM`)을 그대로 쓴다.
 */

interface Chapter {
  id: string
  title: string
  /** 이 장이 답하는 질문. 목차와 장 머리에 쓴다. */
  question: string
  /** 무엇을 하는지 — 한 줄 제목 */
  headline: string
  /** 어떻게 하는지 — 한두 문장 */
  body: string
  /** 이 장에서 할 수 있는 일. 짧게, 동사로 끝낸다 — 설명·주의는 넣지 않는다. */
  points: string[]
  /** 옆에 도는 예시 화면 */
  scene: () => ReactNode
  /**
   * 예시 화면의 마지막 애니메이션이 끝나는 시각(ms). 장면 안 지연값 + 길이로 잰 값이다 —
   * 장면을 고치면 함께 고친다. 끝난 뒤 `HOLD_MS` 만큼 머물렀다가 다음 장으로 넘어간다.
   */
  duration: number
}

const CHAPTERS: Chapter[] = [
  {
    id: 'guide-input',
    title: '패키지 넣기',
    question: '무엇부터 넣으면 되나요?',
    headline: '패키지 이름 하나로 시작해요',
    body: '알아보고 싶은 패키지를 검색하여 유사한 패키지를 확인해요.',
    points: ['패키지 이름으로 검색하기', '목록에서 골라 바로 확인하기'],
    scene: InputScene,
    duration: 3400,
  },
  {
    id: 'guide-candidates',
    title: '후보 고르기',
    question: '누구와 비교하나요?',
    headline: '비슷한 패키지를 골라 나란히 놓아요',
    body: 'Pickage가 제안하는 유사 패키지, 또는 원하는 패키지를 비교 후보군에 추가해요.',
    points: [
      '비슷한 패키지 둘러보기',
      '비교할 패키지 최대 2개 더하기',
      '목록에 없는 패키지 직접 넣기',
    ],
    scene: CandidateScene,
    duration: 3000,
  },
  {
    id: 'guide-ecosystem',
    title: '생태계 변화',
    question: '얼마나 쓰이고, 어떻게 변하고 있나요?',
    headline: '얼마나 쓰이고, 어떻게 변하는지 봐요',
    body: '자료들을 바탕으로 패키지들의 최신 동향을 파악할 수 있어요.',
    points: [
      'AI 요약으로 흐름 한눈에 보기',
      `내려받은 횟수·${DEPENDENTS_TERM} 추이 비교하기`,
      '버전 분포 보기',
    ],
    scene: EcosystemScene,
    duration: 2300,
  },
  {
    id: 'guide-features',
    title: '기능 비교',
    question: '무엇을 할 수 있고, 어떻게 설치되나요?',
    headline: '설치 정보와 기능을 맞춰 봐요',
    body: '설치 정보와 기능 간의 차이를 확인할 수 있어요.',
    points: ['설치 정보 나란히 보기', 'AI 로 공통점·차이점 요약 받기', '비교할 버전 바꿔 보기'],
    scene: FeaturesScene,
    duration: 4300,
  },
  {
    id: 'guide-community',
    title: 'GitHub 커뮤니티',
    question: '어떤 이야기가 오가고 있나요?',
    headline: '요즘 어떤 이야기가 오가는지 봐요',
    body: '패키지에 관해 어떤 이야기가 오고 가는지 엿볼 수 있어요.',
    points: ['많이 논의된 Issue 요약 보기', '실제 대화 흐름 따라가기', 'GitHub 원문 열어 보기'],
    scene: CommunityScene,
    duration: 2800,
  },
  {
    id: 'guide-pdf',
    title: 'PDF로 저장',
    question: '팀에 어떻게 공유하나요?',
    headline: 'PDF로 저장해 팀과 나눠요',
    body: '비교한 내용을 PDF로 저장해 팀과 함께 볼 수 있어요.',
    points: ['보고서를 PDF로 만들기', '미리보기로 확인하기', '바로 내려받기'],
    scene: PdfScene,
    duration: 4500,
  },
]

/** 애니메이션이 끝난 뒤 다음 장으로 넘어가기 전 머무는 시간. */
const HOLD_MS = 2000

export function IntroGuide() {
  const [index, setIndex] = useState(0)
  /** 번호를 누를 때마다 올라간다. 지금 장을 다시 눌러도 그 장이 처음부터 다시 재생된다. */
  const [restart, setRestart] = useState(0)
  const count = CHAPTERS.length
  const go = (i: number) => {
    setIndex((i + count) % count)
    setRestart((r) => r + 1)
  }
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

  /*
    자동 넘김. 지금 장의 애니메이션이 끝나고 2초 뒤 다음 장으로 간다. 번호를 눌러 장을 바꾸면 그 장부터
    다시 센다(`index` 가 바뀌면 타이머를 새로 건다).

    마우스를 올려 두어도 멈추지 않는다(제품 결정). 이 구역이 화면 밖이거나 모션을 끈 사용자일 때만 넘기지 않는다.
  */
  const sectionRef = useRef<HTMLElement>(null)

  /*
    높이는 지금 장을 따라간다. 트랙은 가로로 늘어선 flex 라 그대로 두면 가장 긴 장(커뮤니티) 높이에
    맞춰져, 짧은 장에서는 아래가 크게 빈다. 지금 장의 높이를 재서 바깥 틀에 주고, 바뀔 때는 부드럽게 늘고 준다.
  */
  const slideRefs = useRef<(HTMLElement | null)[]>([])
  const [trackHeight, setTrackHeight] = useState<number | undefined>(undefined)
  useLayoutEffect(() => {
    const el = slideRefs.current[index]
    if (!el) return
    const update = () => {
      // 크기를 잴 수 없는 환경(시험)에서는 0 이 나온다 — 그때는 높이를 주지 않는다.
      if (el.offsetHeight > 0) setTrackHeight(el.offsetHeight)
    }
    update()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [index])
  const [inView, setInView] = useState(() => typeof IntersectionObserver === 'undefined')

  useEffect(() => {
    const el = sectionRef.current
    if (!el || typeof IntersectionObserver === 'undefined') return
    const io = new IntersectionObserver(([e]) => setInView(e.isIntersecting), { threshold: 0.3 })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    if (!inView) return
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const id = setTimeout(
      () => setIndex((i) => (i + 1) % count),
      CHAPTERS[index].duration + HOLD_MS,
    )
    return () => clearTimeout(id)
  }, [index, restart, inView, count])

  /** 탭 목록 안의 좌우 화살표로 장을 옮긴다(WAI-ARIA tabs). */
  function onTabKey(e: React.KeyboardEvent) {
    const next = e.key === 'ArrowRight' ? index + 1 : e.key === 'ArrowLeft' ? index - 1 : null
    if (next === null) return
    e.preventDefault()
    const i = (next + count) % count
    go(i)
    tabRefs.current[i]?.focus()
  }

  return (
    <section
      ref={sectionRef}
      id="guide"
      aria-labelledby="guide-title"
      className="flex scroll-mt-6 flex-col gap-8"
    >
      <div className="flex flex-col gap-2">
        <h2 id="guide-title" className="text-3xl font-bold tracking-tight">
          Pickage 따라하기
        </h2>
        <p className="text-lg text-muted-foreground">번호를 누르면 그 단계로 바로 가요.</p>
      </div>

      {/* 1~6 바로가기 — 번호를 선으로 잇는 진행 표시. 지금 장은 굵은 글자로도 알린다(색만으로 알리지 않는다). */}
      <div
        role="tablist"
        aria-label="사용 설명서 목차"
        onKeyDown={onTabKey}
        className="relative grid grid-cols-3 gap-y-6 sm:grid-cols-6"
      >
        {/*
          번호 동그라미를 잇는 선. 지나온 구간은 진하게, 남은 구간은 옅게 칠한다.
          넓은 화면에서만 한 줄로 이어진다(좁으면 두 줄로 접혀 선이 어색해진다).
        */}
        <span
          aria-hidden
          className="absolute top-[18px] right-[calc(100%/12)] left-[calc(100%/12)] hidden h-0.5 bg-border sm:block"
        >
          <span
            className="block h-full bg-foreground transition-[width] duration-500 ease-out"
            style={{ width: `${(index / (count - 1)) * 100}%` }}
          />
        </span>
        {CHAPTERS.map((c, i) => {
          const on = i === index
          const passed = i <= index
          return (
            <button
              key={c.id}
              ref={(el) => {
                tabRefs.current[i] = el
              }}
              type="button"
              role="tab"
              id={`${c.id}-tab`}
              aria-selected={on}
              aria-controls={c.id}
              tabIndex={on ? 0 : -1}
              onClick={() => go(i)}
              className="group/step relative flex flex-col items-center gap-3 text-center outline-none"
            >
              <span
                className={cn(
                  'grid size-9 place-items-center rounded-full font-mono text-base font-semibold tabular-nums shadow-sm ring-4 ring-canvas transition-colors group-focus-visible/step:outline-2 group-focus-visible/step:outline-offset-2 group-focus-visible/step:outline-foreground',
                  passed ? 'bg-foreground text-background' : 'border bg-card text-muted-foreground',
                )}
              >
                {i + 1}
              </span>
              <span
                className={cn(
                  'text-lg transition-colors',
                  on
                    ? 'font-bold text-foreground'
                    : 'text-muted-foreground group-hover/step:text-foreground',
                )}
              >
                {c.title}
              </span>
            </button>
          )
        })}
      </div>

      {/*
        옆으로 넘어가는 트랙. 한 번에 한 장만 보이고, 안 보이는 장은 `inert` 로 포커스가 들어가지 않는다.
        테두리·배경을 두지 않는다 — 따로 떨어진 상자처럼 보이지 않고 페이지 바탕에 녹아들게 한다.
      */}
      <div
        className="overflow-hidden transition-[height] duration-500 ease-out motion-reduce:transition-none"
        style={{ height: trackHeight }}
      >
        <div
          className="flex items-start transition-transform duration-500 ease-out motion-reduce:transition-none"
          style={{ transform: `translateX(-${index * 100}%)` }}
        >
          {CHAPTERS.map((c, i) => {
            const active = i === index
            return (
              <article
                key={c.id}
                ref={(el) => {
                  slideRefs.current[i] = el
                }}
                id={c.id}
                role="tabpanel"
                aria-labelledby={`${c.id}-tab`}
                aria-hidden={!active}
                inert={!active}
                className="grid w-full shrink-0 items-center gap-8 py-6 lg:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] lg:gap-14"
              >
                <div className="flex flex-col gap-5">
                  <h3 className="text-4xl leading-tight font-bold tracking-tight">{c.headline}</h3>
                  <p className="text-lg leading-relaxed text-muted-foreground">{c.body}</p>
                  <ul className="flex flex-col gap-2">
                    {c.points.map((p) => (
                      <li key={p} className="flex items-start gap-2.5 text-lg">
                        <CheckIcon aria-hidden className="mt-1.5 size-5 shrink-0" strokeWidth={3} />
                        {p}
                      </li>
                    ))}
                  </ul>
                </div>
                <SceneFrame scene={c.scene} on={active && inView} run={active ? restart : 0} />
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}

/* ── 움직이는 예시 화면 ─────────────────────────────────────────────── */

/**
 * 예시 화면. 장이 켜질 때(그리고 이 구역이 화면 안일 때) 한 번 재생한다. 반복하지 않는다 — 끝나면
 * 잠깐 머문 뒤 장 자체가 다음으로 넘어간다. 모션을 끈 사용자에게는 전역 CSS 가 애니메이션을 즉시
 * 끝내 최종 모습만 보인다.
 */
function SceneFrame({
  scene: Scene,
  on,
  run,
}: {
  scene: () => ReactNode
  on: boolean
  /** 번호를 다시 누르면 바뀐다 — 같은 장이어도 처음부터 다시 재생한다. */
  run: number
}) {
  return (
    // 틀을 두지 않는다. 예시 조각(흰 카드)이 페이지 바탕 위에 그대로 떠 있게 한다.
    <div aria-hidden className="relative">
      {/* key 가 바뀌면 다시 마운트되어 애니메이션이 처음부터 돈다 — 켜질 때마다 처음부터 재생한다 */}
      <div
        key={`${on}-${run}`}
        data-on={on}
        className="group flex min-h-[360px] flex-col justify-center"
      >
        <Scene />
      </div>
    </div>
  )
}

/** 뒤늦게 나타나는 조각. `delay` 는 ms. */
function Rise({
  delay,
  className,
  children,
}: {
  delay: number
  className?: string
  children: ReactNode
}) {
  return (
    <div
      className={cn('opacity-0 group-data-[on=true]:animate-oss-rise', className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

/** 처음엔 보이다가 `delay` 에 사라지는 조각. 바뀌기 전 모습을 보여 줄 때 쓴다. */
function Fade({
  delay,
  className,
  children,
}: {
  delay: number
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn('group-data-[on=true]:animate-oss-fade-out', className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </span>
  )
}

/** 눌리는 순간 살짝 들어갔다 나온다. */
function Press({
  delay,
  className,
  children,
}: {
  delay: number
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn('inline-block group-data-[on=true]:animate-oss-press', className)}
      style={{ animationDelay: `${delay}ms` }}
    >
      {children}
    </span>
  )
}

/**
 * 마우스 커서. `delay` 에 오른쪽 아래에서 다가와 자리를 잡고, 도착하면 누르는 물결이 퍼진다.
 * 위치는 부모(relative) 안에서 `className` 으로 정한다 — 화살표 끝이 누를 자리에 오게 둔다.
 */
function Cursor({ delay, className }: { delay: number; className?: string }) {
  return (
    <span className={cn('pointer-events-none absolute z-20', className)}>
      <span
        className="absolute -top-2.5 -left-2.5 size-5 rounded-full border-2 border-foreground/60 opacity-0 group-data-[on=true]:animate-oss-click"
        style={{ animationDelay: `${delay + 600}ms` }}
      />
      <span
        className="block opacity-0 group-data-[on=true]:animate-oss-cursor"
        style={{ animationDelay: `${delay}ms` }}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" className="drop-shadow-md">
          <path
            d="M3 2l17 10.5-7.2 1.4-3.6 7.1z"
            fill="#111827"
            stroke="#ffffff"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    </span>
  )
}

function Box({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-xl border bg-card shadow-[0_8px_24px_-16px_rgba(15,23,42,0.3)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

function Btn({
  outline,
  className,
  children,
}: {
  outline?: boolean
  className?: string
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-grid h-10 shrink-0 place-items-center rounded-lg px-4 text-base font-medium whitespace-nowrap',
        outline ? 'border bg-card' : 'bg-primary text-primary-foreground',
        className,
      )}
    >
      {children}
    </span>
  )
}

/** 값 자리. 숫자를 지어내지 않으려고 회색 막대로 둔다. */
function Bar({ w = 'w-12', className }: { w?: string; className?: string }) {
  return (
    <span className={cn('inline-block h-2.5 rounded-full bg-muted-foreground/20', w, className)} />
  )
}

/** 한 칸에 두 모습을 겹쳐 두고 `at` 에 앞의 것을 지우고 뒤의 것을 띄운다. */
function Swap({
  at,
  before,
  after,
  className,
}: {
  at: number
  before: ReactNode
  after: ReactNode
  className?: string
}) {
  return (
    <span className={cn('relative inline-grid', className)}>
      <Fade delay={at} className="col-start-1 row-start-1">
        {before}
      </Fade>
      <span
        className="col-start-1 row-start-1 opacity-0 group-data-[on=true]:animate-oss-rise"
        style={{ animationDelay: `${at}ms` }}
      >
        {after}
      </span>
    </span>
  )
}

/* 1 — 입력: 타이핑 → 목록에서 winston 을 눌러 고름 → 패키지 확인을 누름 */
function InputScene() {
  return (
    <Box className="flex flex-col gap-4 p-7">
      <span className="text-lg font-semibold">기준 패키지</span>
      <div className="relative flex gap-2">
        <div className="relative flex h-12 flex-1 items-center rounded-lg border bg-card px-4 font-mono text-lg">
          <Fade delay={1900} className="flex items-center">
            <span
              className="inline-block w-0 overflow-hidden whitespace-nowrap group-data-[on=true]:animate-oss-type"
              style={{ '--oss-type-w': '3ch' } as React.CSSProperties}
            >
              win
            </span>
            <span className="ml-[2px] inline-block h-5 w-px bg-foreground opacity-0 group-data-[on=true]:animate-oss-caret" />
          </Fade>
          <span
            className="absolute left-4 opacity-0 group-data-[on=true]:animate-oss-rise"
            style={{ animationDelay: '1900ms' }}
          >
            winston
          </span>
        </div>
        <Press delay={2750}>
          <Btn className="h-12">
            <Swap at={2950} before="패키지 확인" after="찾는 중…" />
          </Btn>
        </Press>
        <Cursor delay={2150} className="right-10 bottom-2" />

        {/* 자동완성 목록 — 고르면 닫힌다 */}
        <Fade delay={1900} className="absolute top-full right-28 left-0 z-10 mt-2">
          <Rise delay={700}>
            <div className="relative flex flex-col rounded-xl border bg-card py-1.5 font-mono text-lg shadow-lg">
              <span className="bg-muted px-4 py-2">
                <b>win</b>ston
              </span>
              <span className="px-4 py-2 text-muted-foreground">
                <b>win</b>ston-transport
              </span>
              <span className="px-4 py-2 text-muted-foreground">
                <b>win</b>dow-size
              </span>
              <Cursor delay={1000} className="top-7 left-40" />
            </div>
          </Rise>
        </Fade>
      </div>
      <span className="text-right text-sm text-muted-foreground tabular-nums">
        앞 글자만 적어도 찾아 드려요
      </span>
      <div className="h-32" />
    </Box>
  )
}

/* 2 — 후보: 실제 화면처럼 3열 카드 + 오른쪽 선택 패널. pino 를 추가하고 보고서 보기를 누름 */
function CandidateScene() {
  const cards = [
    { name: 'pino', rank: 1, pick: true },
    { name: 'bunyan', rank: 2, pick: false },
    { name: 'log4js', rank: 3, pick: false },
  ]
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <span className="text-xl font-bold">함께 비교할 패키지를 골라 주세요</span>
        <span className="text-base text-muted-foreground">
          <b className="font-mono font-medium text-foreground">winston</b> 과 비슷한 패키지를
          찾았어요. 최대 2개를 더 고를 수 있어요.
        </span>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_13rem]">
        <div className="flex flex-col gap-3">
          <Box className="flex items-center gap-2 px-4 py-3 text-base text-muted-foreground">
            목록에 없는 패키지 직접 찾기
            <Bar w="w-24" className="ml-auto" />
          </Box>
          <span className="text-base font-semibold">비슷한 패키지</span>
          <div className="grid grid-cols-3 gap-3">
            {cards.map((c) => (
              <Box key={c.name} className="relative flex flex-col gap-3 p-4">
                {c.pick && (
                  <span
                    className="absolute -inset-px rounded-xl border-2 border-foreground opacity-0 group-data-[on=true]:animate-oss-rise"
                    style={{ animationDelay: '1050ms' }}
                  />
                )}
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-lg font-bold">{c.name}</span>
                  {c.pick ? (
                    <span className="relative">
                      <Swap
                        at={1050}
                        before={
                          <span className="rounded-full border px-2 py-0.5 text-sm text-muted-foreground">
                            추가
                          </span>
                        }
                        after={
                          <span className="rounded-full bg-primary px-2 py-0.5 text-sm text-primary-foreground">
                            ✓ 추가됨
                          </span>
                        }
                      />
                      <Cursor delay={400} className="top-3 left-6" />
                    </span>
                  ) : (
                    <span className="rounded-full border px-2 py-0.5 text-sm text-muted-foreground">
                      추가
                    </span>
                  )}
                </span>
                <span className="flex flex-col gap-1.5">
                  <Bar w="w-full" />
                  <Bar w="w-4/5" />
                  <Bar w="w-3/5" />
                </span>
                <span className="border-t pt-2 text-sm text-muted-foreground">
                  비슷한 순서 {c.rank}위
                </span>
              </Box>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <Box className="flex flex-col gap-3 p-4">
            <span className="flex items-baseline justify-between text-base font-semibold">
              비교할 패키지
              <Swap
                at={1150}
                before={<span className="font-mono text-muted-foreground">1 / 3</span>}
                after={<span className="font-mono text-muted-foreground">2 / 3</span>}
              />
            </span>
            <span className="flex items-center gap-1.5 rounded-lg border bg-muted/50 px-2.5 py-1.5 font-mono text-base">
              <span className="rounded-full bg-brand-soft px-1.5 font-sans text-sm">기준</span>
              winston
            </span>
            <Rise delay={1150}>
              <span className="flex justify-between rounded-lg border px-2.5 py-1.5 font-mono text-base">
                pino <span className="text-muted-foreground">×</span>
              </span>
            </Rise>
            <span className="relative">
              <Press delay={2700} className="w-full">
                <Btn className="w-full">
                  <Swap at={1150} before="기준만 보고서 보기" after="2개로 보고서 보기" />
                </Btn>
              </Press>
              <Cursor delay={2100} className="right-8 bottom-1" />
            </span>
          </Box>
          <Rise delay={1350}>
            <div className="rounded-lg bg-tone-positive px-3 py-2 text-sm text-tone-positive-foreground">
              <b className="font-mono">pino</b> 를 추가했어요 · <u>되돌리기</u>
            </div>
          </Rise>
        </div>
      </div>
    </div>
  )
}

/* 3 — 생태계: 보고서 머리 → AI 가 쓴 한눈에 보기 요약 → 그래프 → 패키지별 한 줄 */
function EcosystemScene() {
  const lines = SAMPLE_ECOSYSTEM.series.downloads.map((s) => ({
    ...s,
    points: s.points.slice(-40),
  }))
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span className="text-sm text-muted-foreground">비교 보고서</span>
        <span className="font-mono text-2xl font-bold">winston · pino · bunyan</span>
        <span className="flex gap-5 border-b text-base">
          <span className="-mb-px border-b-2 border-foreground pb-2 font-semibold">
            생태계 변화
          </span>
          <span className="pb-2 text-muted-foreground">기능 비교</span>
          <span className="pb-2 text-muted-foreground">GitHub 커뮤니티</span>
        </span>
      </div>

      <Box className="flex flex-col gap-2 p-5">
        <span className="flex items-center justify-between text-base font-semibold">
          한눈에 보기{' '}
          <span className="text-sm font-normal text-muted-foreground">AI 요약 · 예시</span>
        </span>
        {[
          ['pino', '는 지난 1년 사이 의존 등록 수가 늘었어요'],
          ['winston', '은 내려받은 횟수가 꾸준해요'],
          ['bunyan', '은 한동안 새 버전이 나오지 않았어요'],
        ].map(([name, rest], i) => (
          <Rise key={name} delay={300 + i * 350}>
            <span className="text-base">
              · <b className="font-mono">{name}</b>
              {rest}
            </span>
          </Rise>
        ))}
      </Box>

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Box className="flex flex-col gap-2 p-4">
          <span className="text-base font-semibold">Downloads</span>
          <div
            className="[clip-path:inset(0_100%_0_0)] group-data-[on=true]:animate-oss-wipe"
            style={{ animationDelay: '1300ms' }}
          >
            <LineChart series={lines} height={120} bare ariaLabel="그래프 예시" />
          </div>
        </Box>
        <div className="flex flex-col gap-2">
          {[
            ['pino', '늘었어요'],
            ['winston', '비슷해요'],
            ['bunyan', '줄었어요'],
          ].map(([name, tag], i) => (
            <Rise key={name} delay={1700 + i * 150}>
              <Box className="flex items-center justify-between gap-2 px-4 py-3">
                <span className="font-mono text-base font-semibold">{name}</span>
                <span className="rounded-full bg-tone-neutral px-2 py-0.5 text-sm text-tone-neutral-foreground">
                  {tag}
                </span>
              </Box>
            </Rise>
          ))}
        </div>
      </div>
    </div>
  )
}

/* 4 — 기능 비교: 설치 정보 표 → 기능 비교 시작 → 세 단계 → 공통점·차이점 요약 */
function FeaturesScene() {
  const rows: [string, string[]][] = [
    ['불러오는 방식', ['require', 'require', 'require']],
    ['TypeScript 타입', ['들어 있어요', '들어 있어요', '@types 따로']],
  ]
  return (
    <div className="flex flex-col gap-4">
      <Box className="flex flex-col p-5 text-base">
        <span className="pb-3 font-semibold">설치하기 전에 알아 둘 것</span>
        <span className="grid grid-cols-[8.5rem_repeat(3,minmax(0,1fr))] gap-2 pb-2 font-mono text-sm text-muted-foreground">
          <span />
          <span>winston</span>
          <span>pino</span>
          <span>bunyan</span>
        </span>
        {rows.map(([label, values], i) => (
          <Rise key={label} delay={150 + i * 200}>
            <span className="grid grid-cols-[8.5rem_repeat(3,minmax(0,1fr))] items-center gap-2 border-t py-2.5">
              <span className="text-muted-foreground">{label}</span>
              {values.map((v, j) => (
                <span key={j} className="w-fit rounded-md bg-tone-neutral px-2 py-0.5 text-sm">
                  {v}
                </span>
              ))}
            </span>
          </Rise>
        ))}
      </Box>

      <Box className="flex flex-col gap-4 p-5">
        <span className="flex items-center justify-between gap-2">
          <span className="text-base font-semibold">AI 기능 비교</span>
          <span className="relative">
            <Press delay={1300}>
              <Btn>기능 비교 시작</Btn>
            </Press>
            <Cursor delay={700} className="right-6 bottom-1" />
          </span>
        </span>
        <div className="grid grid-cols-3 gap-3 text-sm text-muted-foreground">
          {['README 모으기', '기능 맞춰 보기', '요약 쓰기'].map((step, i) => (
            <span key={step} className="flex flex-col gap-1.5">
              <span className="h-1.5 overflow-hidden rounded-full bg-muted">
                <span
                  className="block h-full bg-primary [clip-path:inset(0_100%_0_0)] group-data-[on=true]:animate-oss-wipe"
                  style={{ animationDelay: `${1500 + i * 650}ms` }}
                />
              </span>
              {step}
            </span>
          ))}
        </div>
        <div className="flex flex-col gap-3 border-t pt-4 text-base leading-relaxed">
          <Rise delay={3500}>
            <b>공통점</b>
            <p className="text-muted-foreground">
              세 패키지 모두 로그 수준을 나누고, JSON 으로 남길 수 있어요.
            </p>
          </Rise>
          <Rise delay={3850}>
            <b>차이점</b>
            <p className="text-muted-foreground">
              pino 는 빠르게 남기는 데 집중하고 보기 좋게 바꾸는 일은 다른 도구에 맡겨요. winston 은
              여러 곳으로 나눠 보내는 설정을 README 에 자세히 적어 두었어요.
            </p>
          </Rise>
        </div>
      </Box>
    </div>
  )
}

/*
 * 5 — 커뮤니티: 보고서의 "핵심 논의"·"실제 논의 흐름" 두 구역을 **실제 컴포넌트 그대로** 그린다
 * (`CommunityIssueCard`·`CommunityThreadCard`).
 * 예시 화면이 실제 화면과 달라지면 인트로가 틀린 모습을 약속하게 된다 — 그래서 흉내 내지 않고 가져다 쓴다.
 * 말풍선(li)만 차례로 떠오르게 바깥에서 애니메이션을 건다. 발화 내용은 지어낸 예시라 이름도 example-* 로 둔다.
 */
const DEMO_SUMMARY =
  '새 버전으로 올린 뒤 로그가 두 번씩 찍힌다는 제보가 있었고, 출력 대상을 한 번만 등록하면 해결된다는 안내가 나왔다.'
/** 요약 강조 구간은 글자 위치(UTF-16)로 준다 — 손으로 세면 어긋나니 문장에서 찾아 만든다. */
function markOf(text: string, kind: 'KEY_TERM' | 'KEY_SENTENCE') {
  const start = DEMO_SUMMARY.indexOf(text)
  return { start, end: start + text.length, kind }
}

const DEMO_TOPIC: CommunityTopic = {
  ...SAMPLE_COMMUNITY_RESULT.topics[0],
  issue_number: 1234,
  state: 'CLOSED',
  title_original: 'Logs are printed twice after upgrading',
  title_ko: '새 버전에서 로그가 두 번씩 찍히는 문제',
  comments_count: 3,
  reactions_count: 5,
  summary_ko: DEMO_SUMMARY,
  summary_marks: [
    markOf('로그가 두 번씩 찍힌다', 'KEY_TERM'),
    markOf('출력 대상을 한 번만 등록하면 해결된다', 'KEY_SENTENCE'),
  ],
  messages: [
    {
      author_login: 'example-user',
      role: 'ISSUE_AUTHOR',
      kind: 'DISCUSSION',
      created_at: '2026-09-01T00:00:00Z',
      text: '새 버전으로 올린 뒤 같은 로그가 두 번씩 찍힌다고 알렸다.',
    },
    {
      author_login: 'example-owner',
      role: 'REPOSITORY_OWNER',
      kind: 'USER_SOLUTION',
      created_at: '2026-09-02T00:00:00Z',
      text: '출력 대상을 두 번 등록하면 생기는 일이라며, 한 번만 등록하도록 안내했다.',
    },
    {
      author_login: 'example-dev',
      role: 'CONTRIBUTOR',
      kind: 'DISCUSSION',
      created_at: '2026-09-03T00:00:00Z',
      text: '같은 문제를 겪었는데 안내대로 바꾸니 해결됐다고 확인했다.',
    },
  ],
}

function CommunityScene() {
  return (
    <div className="grid items-start gap-6 xl:grid-cols-2">
      {/*
        보고서와 같이 두 구역으로 나눈다 — 핵심 논의(요약 카드) / 실제 논의 흐름(대화).
        넓은 화면에서는 나란히 둔다. 위아래로 쌓으면 이 장만 유난히 길어진다.
      */}
      <Rise delay={200} className="flex flex-col gap-3">
        <SceneHeading title="핵심 논의" hint="GitHub 공개 Issue · 핵심 논지 요약" />
        <CommunityIssueCard topic={DEMO_TOPIC} limitations={[]} accent={issueAccent(0)} />
      </Rise>
      <div className="flex flex-col gap-3">
        <Rise delay={900}>
          <SceneHeading
            title="실제 논의 흐름"
            hint="원문 댓글의 핵심 논지를 한국어로 요약했습니다."
          />
        </Rise>
        <div className="[&_li]:opacity-0 group-data-[on=true]:[&_li:nth-child(1)]:animate-[oss-rise_380ms_cubic-bezier(0.2,0.8,0.3,1)_1200ms_both] group-data-[on=true]:[&_li:nth-child(2)]:animate-[oss-rise_380ms_cubic-bezier(0.2,0.8,0.3,1)_1800ms_both] group-data-[on=true]:[&_li:nth-child(3)]:animate-[oss-rise_380ms_cubic-bezier(0.2,0.8,0.3,1)_2400ms_both]">
          <CommunityThreadCard topic={DEMO_TOPIC} accent={issueAccent(0)} />
        </div>
      </div>
    </div>
  )
}

/** 보고서 커뮤니티 탭의 구역 제목과 같은 모양(`result.tsx` SectionHeading). */
function SceneHeading({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
      <span className="text-2xl font-bold tracking-tight">{title}</span>
      <span className="text-base text-muted-foreground">{hint}</span>
    </div>
  )
}

/* 6 — PDF: 구역을 고르고 생성 → 준비됨 → 미리보기를 누르면 문서가 올라온다 */
function PdfScene() {
  const lines = SAMPLE_ECOSYSTEM.series.downloads.map((s) => ({
    ...s,
    points: s.points.slice(-40),
  }))
  return (
    <div className="relative min-h-[420px]">
      <Box className="flex max-w-md flex-col gap-3 p-6">
        <span className="text-lg font-semibold">PDF 내보내기</span>
        <span className="text-sm text-muted-foreground">더할 구역</span>
        <span className="flex items-center gap-2 text-base">
          <span className="grid size-5 place-items-center rounded-[5px] bg-primary text-primary-foreground opacity-60">
            <CheckIcon className="size-3.5" strokeWidth={3} />
          </span>
          생태계 보고서 <span className="text-muted-foreground">· 항상 포함</span>
        </span>
        <span className="relative flex items-center gap-2 text-base">
          <span className="relative grid size-5 place-items-center rounded-[5px] border">
            <span
              className="absolute -inset-px grid place-items-center rounded-[5px] bg-primary text-primary-foreground opacity-0 group-data-[on=true]:animate-oss-pop"
              style={{ animationDelay: '900ms' }}
            >
              <CheckIcon className="size-3.5" strokeWidth={3} />
            </span>
          </span>
          커뮤니티 분석
          <Cursor delay={300} className="top-3 left-2.5" />
        </span>
        <div className="flex flex-col gap-3 border-t pt-4">
          <span className="relative flex justify-end">
            <Press delay={1700}>
              <Btn>
                <Swap at={1850} before="PDF 생성" after="만드는 중…" />
              </Btn>
            </Press>
            <Cursor delay={1100} className="right-8 bottom-1" />
          </span>
          <span className="h-1.5 overflow-hidden rounded-full bg-muted">
            <span
              className="block h-full bg-primary [clip-path:inset(0_100%_0_0)] group-data-[on=true]:animate-oss-wipe"
              style={{ animationDelay: '1850ms' }}
            />
          </span>
          <Rise delay={2800} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-base font-medium">
              <CheckIcon className="size-4" strokeWidth={3} />
              PDF가 준비되었어요
            </span>
            <span className="relative flex gap-2">
              <Press delay={3700}>
                <Btn outline className="h-9">
                  미리보기
                </Btn>
              </Press>
              <Btn className="h-9">다운로드</Btn>
              <Cursor delay={3100} className="bottom-1 left-14" />
            </span>
          </Rise>
        </div>
      </Box>

      {/* 미리보기 문서 — 종이 한 장이 올라온다 */}
      <div
        className="absolute top-6 right-0 w-[min(100%,26rem)] opacity-0 group-data-[on=true]:animate-oss-slide-up"
        style={{ animationDelay: '3950ms' }}
      >
        <div className="flex flex-col gap-3 rounded-md border bg-white p-6 shadow-[0_24px_48px_-20px_rgba(15,23,42,0.45)]">
          <span className="text-sm text-muted-foreground">미리보기</span>
          <span className="text-xl font-bold">Pickage 생태계 보고서</span>
          <span className="font-mono text-sm text-muted-foreground">winston · pino · bunyan</span>
          <span className="border-t pt-3 text-sm font-semibold">Downloads</span>
          <LineChart series={lines} height={90} bare ariaLabel="보고서 그래프 예시" />
          <span className="flex flex-col gap-2 border-t pt-3">
            {[0, 1, 2].map((r) => (
              <span key={r} className="flex items-center gap-3">
                <Bar w="w-16" />
                <Bar w="w-full" />
              </span>
            ))}
          </span>
        </div>
      </div>
    </div>
  )
}
