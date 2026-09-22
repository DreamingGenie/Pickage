import { PlusIcon, SearchIcon } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { paths } from '@/app/routes'
import { parsePackageInput } from '@/lib/package'
import { PackageSearch } from '@/routes/analyze/package-search'
import { IntroGuide } from '@/routes/intro/guide'
import { IntroValues } from '@/routes/intro/values'

/**
 * v1-OSS-00-service-intro
 *
 * **검색이 먼저다.** 처음 온 사람이 가장 빨리 이해하는 길은 설명을 읽는 것이 아니라 한 번 눌러
 * 보는 것이라, 입력창과 예시 조합을 맨 위에 둔다. 그 아래 설명은 실제 화면과 같은 모양으로만
 * 그린다 — 인트로의 그림이 실제 화면과 다르면 들어가서 다시 헤매게 된다.
 *
 * 순서: 히어로(입력) → 핵심 메시지 3개(G2 식)
 *       → 자세히 보기(여섯 장 캐러셀, `guide.tsx`) → 자주 묻는 질문(관측 범위와 판단 한계, IA 4.1-5)
 *
 * 카피 원칙: 구상안이 산출한다고 명시한 것만 약속한다. 말투는 해요체, 어려운 말은 풀어 쓴다.
 * 기술 우열 판단, 자동 최종 추천은 산출물이 아니므로 문구에 넣지 않는다.
 * 화면 안의 도움말(첫 방문 안내)은 이 파일이 아니라 각 화면이 맡는다.
 */
/**
 * 자주 묻는 질문. "관측 범위와 판단 한계"(IA 4.1-5·4.2 범위 안내)를 질문 형태로 푼 것이다 —
 * 한계를 목록으로 늘어놓으면 읽지 않고 지나치지만, 궁금한 순간에 찾아 읽는 질문은 읽힌다.
 */
const FAQ: readonly { q: string; a: string }[] = [
  {
    q: '어느 패키지가 더 낫다고 알려 주나요?',
    a: '아니에요. 고르는 데 필요한 사실을 나란히 보여 드릴 뿐, 어느 쪽이 낫다고 판정하지 않아요. 후보 순서도 설명·키워드가 얼마나 비슷한지일 뿐, 품질이나 우열이 아니에요.',
  },
  {
    q: '찾는 패키지가 안 나와요',
    a: '미리 데이터를 모아 둔 패키지만 분석할 수 있어요. 입력창 목록에 없다면 아직 모으지 않은 패키지예요.',
  },
  {
    q: '숫자는 어디서 가져오나요?',
    a: '다운로드는 npm 공식 자료, 의존 수·버전 분포는 공개된 package.json 을 모아 센 값이에요. 버전 분포는 가장 최근에 모은 날 기준이라, 실제로 설치된 비율과는 다를 수 있어요.',
  },
  {
    q: '기능 비교 결과는 믿어도 되나요?',
    a: 'AI 가 고른 버전의 README 를 읽고 정리한 결과예요. README 에서 찾지 못한 것은 ‘미확인’, AI 가 원래 알던 지식으로 판단한 칸은 ‘일반 지식’ 으로 표시하니, 중요한 결정 전에는 원문도 확인해 보세요.',
  },
]

export function ServiceIntroPage() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  function start(raw: string) {
    const parsed = parsePackageInput(raw)
    if (!parsed.ok) {
      setError(parsed.reason)
      return
    }
    navigate(paths.analyze, { state: { prefill: raw.trim() } })
  }

  return (
    <div className="flex flex-col gap-8 pb-16">
      {/* ── Hero ───────────────────────────────────────────────── */}
      {/*
        간결한 첫 화면 — 둥근 판 위에 큰 한 줄 제목, 두 줄 설명, 폭 넓은 검색창.
        판 뒤에는 각진 면이 겹친 옅은 배경을 깐다(`HeroBackdrop`, 흑백 톤). 장식이다.

        **`overflow-hidden` 은 배경 도형에만 둔다.** 판 전체에 걸면 자동완성 목록이 판 밖으로 내려올 때 잘린다.
        `z-10`: 아래 구역보다 위에 쌓여야 자동완성 목록이 가려지지 않는다.
      */}
      <section className="relative z-10 mt-2 flex flex-col items-center gap-6 rounded-[28px] border px-6 pt-20 pb-16 text-center sm:px-10">
        <HeroBackdrop />

        <h1 className="relative text-4xl font-extrabold tracking-[-0.035em] text-balance lg:text-display">
          비교하고 고르는 npm 패키지
        </h1>
        <p className="relative max-w-2xl text-lg leading-relaxed text-foreground/70">
          비슷한 패키지를 찾아 쓰임새·기능·커뮤니티를 한눈에 비교하고,
          <br className="hidden sm:inline" /> 내 프로젝트에 맞는 선택을 직접 내려 보세요.
        </p>

        <div className="relative mt-4 w-full max-w-3xl">
          <PackageSearch
            value={draft}
            onChange={(v) => {
              setDraft(v)
              if (error) setError(null)
            }}
            onSubmit={start}
            placeholder="알아보고 싶은 npm 패키지 이름을 적어 주세요"
            ariaLabel="분석할 npm 패키지명"
            icon={false}
            invalid={Boolean(error)}
            describedBy={error ? 'intro-input-error' : undefined}
            className="w-full"
            inputClassName="h-16 w-full rounded-full border-foreground/15 bg-card pr-36 pl-8 font-sans text-lg shadow-[0_12px_32px_-16px_rgba(15,23,42,0.35)] placeholder:text-muted-foreground/70 aria-invalid:border-destructive"
          />
          <button
            type="button"
            disabled={!draft.trim()}
            aria-label="분석 시작"
            onClick={() => start(draft)}
            className="absolute top-2 right-2 flex h-12 items-center gap-2 rounded-full bg-primary px-6 text-lg font-semibold text-primary-foreground transition-opacity outline-none hover:opacity-90 focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-40"
          >
            검색
            <SearchIcon aria-hidden className="size-5" />
          </button>
        </div>
        {error && (
          <p
            id="intro-input-error"
            role="alert"
            className="relative -mt-2 text-sm text-destructive"
          >
            {error}
          </p>
        )}
      </section>

      {/* ── 핵심 메시지 3개 — 메시지 하나가 한 줄을 다 쓴다(`values.tsx`) ── */}
      <IntroValues />

      {/* ── Pickage 따라하기 — 옆으로 넘기는 여섯 장, 1~6 으로 바로 이동 ── */}
      <IntroGuide />

      {/* ── 자주 묻는 질문 (IA 4.1-5 관측 범위와 판단 한계) ─────── */}
      {/*
        자주 묻는 질문 — 흔한 고객센터식 FAQ 배치(토스·Stripe·노션 등): 왼쪽에 제목, 오른쪽에 접이식 목록.
        질문 앞에는 Q, 답 앞에는 A 표시를 둔다. 표시는 장식이 아니라 질문/답을 가르는 글자라 스크린리더에도 읽힌다.
        열고 닫는 표시는 +(열기) / ×(닫기)로 돌린다.
      */}
      <section
        id="faq"
        className="grid scroll-mt-6 gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]"
      >
        <div className="flex flex-col gap-3">
          <h2 className="text-3xl font-bold tracking-tight">자주 묻는 질문</h2>
          <p className="text-lg text-muted-foreground">
            처음 쓰실 때 많이 궁금해하시는 것들을 모았어요.
          </p>
        </div>
        <ul className="flex flex-col border-t">
          {FAQ.map((item) => (
            <li key={item.q} className="border-b">
              <details className="group/faq">
                <summary className="flex cursor-pointer list-none items-center gap-4 py-6 outline-none focus-visible:bg-card [&::-webkit-details-marker]:hidden">
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-foreground font-mono text-base font-bold text-background">
                    Q
                  </span>
                  <span className="flex-1 text-lg font-semibold">{item.q}</span>
                  <PlusIcon
                    aria-hidden
                    className="size-6 shrink-0 text-muted-foreground transition-transform duration-200 group-open/faq:rotate-45"
                  />
                </summary>
                <div className="flex gap-4 pb-6">
                  <span className="grid size-9 shrink-0 place-items-center rounded-full border bg-card font-mono text-base font-bold text-muted-foreground">
                    A
                  </span>
                  <p className="flex-1 rounded-2xl bg-card px-5 py-4 text-lg leading-relaxed text-foreground/80">
                    {item.a}
                  </p>
                </div>
              </details>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}

/**
 * 첫 화면 판 뒤의 옅은 배경 — 각진 면 몇 장이 겹친 모양. 흑백 톤으로만 칠한다. 장식이며 뜻을 전하지 않는다.
 * 판의 둥근 모서리를 따라 자르려고 여기(배경)에만 `overflow-hidden` 을 건다.
 */
function HeroBackdrop() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 overflow-hidden rounded-[28px]"
    >
      <div
        className="absolute inset-0"
        style={{ background: 'linear-gradient(135deg, #e4e7ec 0%, #f1f3f6 45%, #fbfbfc 100%)' }}
      />
      <div
        className="absolute inset-y-0 -left-10 w-[42%]"
        style={{
          clipPath: 'polygon(0 18%, 100% 0, 70% 100%, 0 100%)',
          background: 'linear-gradient(160deg, #ffffff 0%, rgba(255,255,255,0.35) 100%)',
          opacity: 0.8,
        }}
      />
      <div
        className="absolute inset-y-0 right-0 w-[48%]"
        style={{
          clipPath: 'polygon(0 0, 100% 0, 100% 100%, 38% 100%, 22% 32%)',
          background:
            'linear-gradient(200deg, #ffffff 0%, rgba(255,255,255,0.55) 60%, rgba(255,255,255,0) 100%)',
        }}
      />
      <div
        className="absolute bottom-0 left-[28%] h-[45%] w-[30%]"
        style={{
          clipPath: 'polygon(20% 0, 100% 100%, 0 100%)',
          background: 'linear-gradient(0deg, rgba(209,213,219,0.55) 0%, rgba(209,213,219,0) 100%)',
        }}
      />
    </div>
  )
}
