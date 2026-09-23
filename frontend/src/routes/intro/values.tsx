import { ArrowDownToLineIcon, CheckIcon, EyeIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import type { PackageEnvResponse } from '@/api/types'
import { paths } from '@/app/routes'
import { LineChart } from '@/components/charts/line-chart'
import { SAMPLE_ECOSYSTEM } from '@/components/charts/sample'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { EcosystemView } from '@/routes/report/ecosystem/ecosystem-view'
import { DEPENDENTS_TERM } from '@/routes/report/ecosystem/terms'
import { toEnvironmentRows } from '@/routes/report/features/environment-adapter'
import { EnvironmentTable } from '@/routes/report/features/environment-table'

/**
 * 인트로의 핵심 기능 셋 — 동향 비교 · 기능 비교 · 보고서로 확인하기. G2 홈의 기능 소개 줄을 따른다.
 *
 * - **한 기능이 한 줄을 통째로 쓴다.** 글과 그림을 좌우로 두고 줄마다 방향을 바꾼다.
 * - 글은 두 줄 제목(옅은 질문 + 굵은 한 문장) · 한 문단 · 폭 넓은 알약 버튼.
 * - 버튼은 다른 화면으로 보내지 않고 **그 자리에서 미리보기 창을 연다.** 가능하면 보고서의 실제 컴포넌트를
 *   예시 자료로 그대로 그린다 — 인트로를 떠나지 않고도 결과가 어떻게 생겼는지 볼 수 있게.
 * - 그림은 아이콘이 아니라 **서비스 화면 조각을 겹쳐 쌓은 것**이다. 실제로 보게 될 카드·그래프·표 모양이라
 *   무엇을 하는 기능인지 화면으로 바로 읽힌다. 장식이므로 `aria-hidden` 이고, 같은 내용을 옆 글이 담는다.
 * - 숫자는 지어내지 않는다 — 값 자리는 회색 막대로 두고, 그래프만 보고서 쪽 표본을 쓴다.
 */
const EXAMPLE_NAMES = ['winston', 'pino', 'bunyan'] as const

const FEATURES: readonly {
  question: string
  statement: string
  body: string
  cta: string
  art: () => ReactNode
  preview: { title: string; description: string; body: () => ReactNode }
}[] = [
  {
    question: '얼마나 쓰이고 있을까?',
    statement: '동향을 비교해요.',
    body: `내려받은 횟수와 ${DEPENDENTS_TERM}가 주마다 어떻게 변했는지, 여러 패키지를 한 그래프에 나란히 놓고 봐요.`,
    cta: '동향 비교 미리보기',
    art: TrendArt,
    preview: {
      title: '동향 비교 미리보기',
      description: '보고서의 생태계 변화 화면이에요. 그래프와 카드는 예시 자료로 그렸어요.',
      body: TrendPreview,
    },
  },
  {
    question: '무엇이 다를까?',
    statement: '기능을 비교해요.',
    body: '설치 정보는 바로 표로 보여 드리고, 기능 차이는 AI 가 설명 문서를 읽고 공통점과 차이점으로 정리해 드려요.',
    cta: '기능 비교 미리보기',
    art: FeatureArt,
    preview: {
      title: '기능 비교 미리보기',
      description: '설치 정보 표는 보고서와 같은 화면이에요. AI 요약 글은 예시 문장이에요.',
      body: FeaturePreview,
    },
  },
  {
    question: '팀과 함께 봐야 한다면?',
    statement: '보고서로 확인해요.',
    body: '비교한 내용을 한 장의 보고서로 모아 PDF 로 저장하고, 팀원과 같은 화면을 보며 이야기해 보세요.',
    cta: '보고서 미리보기',
    art: ReportArt,
    preview: {
      title: '보고서 미리보기',
      description: 'PDF 로 저장하면 이런 문서가 만들어져요. 내용은 예시예요.',
      body: ReportPreview,
    },
  },
]

export function IntroValues() {
  /** 열린 미리보기. 한 번에 하나만 연다. */
  const [open, setOpen] = useState<number | null>(null)
  const current = open === null ? null : FEATURES[open]

  return (
    <section aria-label="Pickage 핵심 기능" className="flex flex-col">
      {FEATURES.map((f, i) => {
        const artFirst = i % 2 === 0
        return (
          <div
            key={f.statement}
            className="grid items-center gap-12 py-16 lg:min-h-[560px] lg:grid-cols-2 lg:gap-20"
          >
            {/* 그림 — 옅은 바탕 판 위에 화면 조각을 겹친다 */}
            <div
              aria-hidden
              className={cn(
                'relative flex min-h-[420px] items-center justify-center rounded-3xl bg-muted/60 px-6 py-12 sm:px-10',
                !artFirst && 'lg:order-2',
              )}
            >
              <f.art />
            </div>

            <div className="flex flex-col gap-6">
              <h3 className="flex flex-col text-4xl leading-tight font-bold tracking-tight">
                <span className="text-muted-foreground">{f.question}</span>
                <span>{f.statement}</span>
              </h3>
              <p className="max-w-lg text-lg leading-relaxed text-foreground/80">{f.body}</p>
              <button
                type="button"
                onClick={() => setOpen(i)}
                className="flex h-14 w-full max-w-lg items-center justify-center gap-2 rounded-full border bg-card text-lg font-semibold transition-colors outline-none hover:border-foreground/50 focus-visible:ring-[3px] focus-visible:ring-ring/40"
              >
                <EyeIcon aria-hidden className="size-5" />
                {f.cta}
              </button>
            </div>
          </div>
        )
      })}

      <Dialog open={open !== null} onOpenChange={(v) => !v && setOpen(null)}>
        <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-6xl">
          {current && (
            <>
              <DialogHeader>
                <DialogTitle className="text-2xl">{current.preview.title}</DialogTitle>
                <DialogDescription className="text-base">
                  {current.preview.description}
                </DialogDescription>
              </DialogHeader>
              <div className="rounded-2xl bg-canvas p-6">
                <current.preview.body />
              </div>
              <div className="flex justify-end">
                <Link
                  to={paths.analyze()}
                  className="flex h-12 items-center rounded-full bg-primary px-6 text-base font-semibold text-primary-foreground transition-opacity hover:opacity-90"
                >
                  내 패키지로 비교해 보기
                </Link>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}

/* ── 미리보기 창 내용 ─────────────────────────────────────────────────── */

/** 동향 — 보고서의 생태계 화면을 예시 자료로 그대로 그린다. */
function TrendPreview() {
  return <EcosystemView model={SAMPLE_ECOSYSTEM} compactChart />
}

/**
 * 기능 — 설치 정보 표는 실제 컴포넌트다. 값은 세 패키지의 공개된 설치 정보 중 확실한 두 줄
 * (불러오는 방식·타입)만 쓴다 — 개수 줄은 지어내지 않으려고 뺐다.
 * AI 요약은 아직 화면이 없어(RAG 개편 예정) 예시 문장으로 모양만 보여 준다.
 */
const PREVIEW_PACKAGES = [
  { name: 'winston', version: '3.19.0' },
  { name: 'pino', version: '10.3.1' },
  { name: 'bunyan', version: '1.8.15' },
]
const PREVIEW_ENV: PackageEnvResponse = {
  items: [
    {
      name: 'winston',
      version: '3.19.0',
      module_format: 'CJS',
      types_bundled: true,
      direct_dependencies: null,
      peer_dependencies: null,
    },
    {
      name: 'pino',
      version: '10.3.1',
      module_format: 'CJS',
      types_bundled: true,
      direct_dependencies: null,
      peer_dependencies: null,
    },
    {
      name: 'bunyan',
      version: '1.8.15',
      module_format: 'CJS',
      types_bundled: false,
      direct_dependencies: null,
      peer_dependencies: null,
    },
  ],
  not_found: [],
}

function FeaturePreview() {
  const rows = toEnvironmentRows(PREVIEW_PACKAGES, PREVIEW_ENV).filter(
    (r) => r.key === 'module_format' || r.key === 'types_bundled',
  )
  return (
    <div className="flex flex-col gap-6">
      <EnvironmentTable packages={PREVIEW_PACKAGES} rows={rows} note={null} loading={false} />
      <section className="flex flex-col gap-4 rounded-2xl border bg-card p-6">
        <span className="flex items-center justify-between gap-2">
          <span className="text-lg font-semibold">AI 기능 비교</span>
          <span className="rounded-full bg-tone-neutral px-2.5 py-0.5 text-sm">예시 문장</span>
        </span>
        <div className="flex flex-col gap-1">
          <b>공통점</b>
          <p className="leading-relaxed text-muted-foreground">
            세 패키지 모두 로그 수준을 나누고, JSON 으로 남길 수 있어요.
          </p>
        </div>
        <div className="flex flex-col gap-1">
          <b>차이점</b>
          <p className="leading-relaxed text-muted-foreground">
            pino 는 빠르게 남기는 데 집중하고, 보기 좋게 바꾸는 일은 다른 도구에 맡겨요. winston 은
            여러 곳으로 나눠 보내는 설정을 설명 문서에 자세히 적어 두었어요.
          </p>
        </div>
      </section>
    </div>
  )
}

/** 보고서 — PDF 한 장의 모양. 서버가 만드는 문서라 여기서는 구성만 줄여 그린다. */
function ReportPreview() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 rounded-md border bg-white p-10 shadow-[0_24px_48px_-24px_rgba(15,23,42,0.4)]">
      <div className="flex flex-col gap-1 border-b pb-4">
        <span className="text-2xl font-bold">Pickage 생태계 보고서</span>
        <span className="font-mono text-base text-muted-foreground">winston · pino · bunyan</span>
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-lg font-semibold">{DEPENDENTS_TERM}</span>
        <LineChart series={LINES} height={140} bare ariaLabel="보고서 그래프 예시" />
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-lg font-semibold">Downloads</span>
        <LineChart series={LINES} height={110} bare ariaLabel="보고서 그래프 예시" />
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-lg font-semibold">수치 표</span>
        {[0, 1, 2].map((r) => (
          <span
            key={r}
            className="grid grid-cols-[6rem_1fr_1fr_1fr] items-center gap-3 border-t py-2"
          >
            <span className="font-mono text-sm">{EXAMPLE_NAMES[r]}</span>
            <Bar className="w-3/4" />
            <Bar className="w-1/2" />
            <Bar className="w-2/3" />
          </span>
        ))}
      </div>
      <span className="text-sm text-muted-foreground">
        + 커뮤니티 분석 · 버전 분포 · 유지·유입·이탈
      </span>
    </div>
  )
}

/* ── 그림 조각 ───────────────────────────────────────────────────────── */

function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-xl border bg-card shadow-[0_24px_48px_-28px_rgba(15,23,42,0.45)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

function Bar({ className }: { className?: string }) {
  return <span className={cn('block h-2.5 rounded-full bg-muted-foreground/20', className)} />
}

function Avatar({ name, dark = false }: { name: string; dark?: boolean }) {
  return (
    <span
      className={cn(
        'grid size-11 shrink-0 place-items-center rounded-full font-mono text-base font-bold',
        dark ? 'bg-foreground text-background' : 'bg-muted text-foreground',
      )}
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  )
}

const LINES = SAMPLE_ECOSYSTEM.series.downloads.map((s) => ({ ...s, points: s.points.slice(-44) }))

/** 1 — 동향: 뒤에 패키지 카드 둘, 앞에 세 선이 겹친 그래프 카드. */
function TrendArt() {
  return (
    <div className="relative h-[340px] w-full max-w-[560px]">
      {[
        { name: 'pino', top: 'top-0 left-0', tag: '1년 사이 늘었어요' },
        { name: 'bunyan', top: 'top-14 left-10', tag: '한동안 새 버전 없음' },
      ].map((p) => (
        <Card key={p.name} className={cn('absolute w-[62%] p-5', p.top)}>
          <span className="flex items-center gap-3">
            <Avatar name={p.name} />
            <span className="flex flex-col gap-1">
              <span className="font-mono text-base font-bold">{p.name}</span>
              <span className="text-sm text-muted-foreground">{p.tag}</span>
            </span>
          </span>
          <span className="mt-4 grid grid-cols-3 gap-2">
            {['주간 다운로드', '저장소 별', '열린 이슈'].map((l) => (
              <span key={l} className="flex flex-col gap-1.5 rounded-lg bg-canvas p-2">
                <span className="truncate text-sm text-muted-foreground">{l}</span>
                <Bar className="w-3/4" />
              </span>
            ))}
          </span>
        </Card>
      ))}
      <Card className="absolute right-0 bottom-0 w-[70%] p-5">
        <span className="flex items-center justify-between">
          <span className="text-base font-bold">{DEPENDENTS_TERM}</span>
          <span className="flex rounded-md border text-sm">
            <span className="rounded-l-md bg-foreground px-2 py-0.5 text-background">실제값</span>
            <span className="px-2 py-0.5 text-muted-foreground">변화율</span>
          </span>
        </span>
        <span className="mt-2 flex gap-2">
          {EXAMPLE_NAMES.map((n) => (
            <span key={n} className="rounded-full border px-2 py-0.5 font-mono text-sm">
              {n}
            </span>
          ))}
        </span>
        <LineChart series={LINES} height={130} bare ariaLabel="그래프 예시" />
      </Card>
    </div>
  )
}

/** 2 — 기능: 뒤에 설치 정보 표, 앞에 AI 가 쓴 공통점·차이점 카드. */
function FeatureArt() {
  const rows: [string, string[]][] = [
    ['불러오는 방식', ['require', 'require', 'require']],
    ['TypeScript 타입', ['들어 있어요', '들어 있어요', '@types 따로']],
    ['함께 설치되는 패키지', ['', '', '']],
  ]
  return (
    <div className="relative h-[360px] w-full max-w-[560px]">
      <Card className="absolute top-0 left-0 w-[80%] p-5">
        <span className="text-base font-bold">설치하기 전에 알아 둘 것</span>
        <span className="mt-3 grid grid-cols-[7.5rem_repeat(3,minmax(0,1fr))] gap-2 pb-2 font-mono text-sm text-muted-foreground">
          <span />
          {EXAMPLE_NAMES.map((n) => (
            <span key={n}>{n}</span>
          ))}
        </span>
        {rows.map(([label, values]) => (
          <span
            key={label}
            className="grid grid-cols-[7.5rem_repeat(3,minmax(0,1fr))] items-center gap-2 border-t py-2.5 text-sm"
          >
            <span className="text-muted-foreground">{label}</span>
            {values.map((v, j) =>
              v ? (
                <span key={j} className="w-fit rounded-md bg-tone-neutral px-1.5 py-0.5">
                  {v}
                </span>
              ) : (
                <Bar key={j} className="w-10" />
              ),
            )}
          </span>
        ))}
      </Card>
      <Card className="absolute right-0 bottom-0 w-[66%] p-5">
        <span className="flex items-center justify-between gap-2">
          <span className="text-base font-bold">AI 기능 비교</span>
          <span className="flex items-center gap-1 rounded-full bg-foreground px-2.5 py-0.5 text-sm text-background">
            <CheckIcon className="size-3.5" strokeWidth={3} />
            요약 완료
          </span>
        </span>
        <span className="mt-4 flex flex-col gap-3 text-sm leading-relaxed">
          <span className="flex flex-col gap-1.5">
            <b>공통점</b>
            <Bar className="w-full" />
            <Bar className="w-4/5" />
          </span>
          <span className="flex flex-col gap-1.5">
            <b>차이점</b>
            <Bar className="w-full" />
            <Bar className="w-11/12" />
            <Bar className="w-3/5" />
          </span>
        </span>
      </Card>
    </div>
  )
}

/** 3 — 보고서: 뒤에 PDF 한 장, 앞에 보고서 머리(탭·버튼), 모서리에 내려받기 알약. */
function ReportArt() {
  return (
    <div className="relative h-[360px] w-full max-w-[560px]">
      <Card className="absolute top-10 left-0 flex h-[300px] w-[42%] flex-col gap-3 p-5">
        <span className="text-sm font-bold">Pickage 생태계 보고서</span>
        <span className="font-mono text-sm text-muted-foreground">PDF</span>
        <LineChart series={LINES} height={70} bare ariaLabel="보고서 그래프 예시" />
        <span className="flex flex-col gap-2">
          <Bar className="w-full" />
          <Bar className="w-5/6" />
          <Bar className="w-2/3" />
        </span>
      </Card>
      <Card className="absolute top-0 right-0 w-[74%] overflow-hidden">
        <div className="h-16 bg-foreground/85" />
        <div className="flex flex-col gap-4 p-5">
          <span className="flex items-start justify-between gap-3">
            <span className="flex flex-col gap-1">
              <span className="text-sm text-muted-foreground">비교 보고서</span>
              <span className="font-mono text-lg font-bold">winston · pino · bunyan</span>
            </span>
            <span className="rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background">
              PDF로 저장
            </span>
          </span>
          <span className="flex gap-4 border-b text-sm">
            <span className="-mb-px border-b-2 border-foreground pb-2 font-semibold">
              생태계 변화
            </span>
            <span className="pb-2 text-muted-foreground">기능 비교</span>
            <span className="pb-2 text-muted-foreground">GitHub 커뮤니티</span>
          </span>
          <span className="grid grid-cols-2 gap-3">
            <span className="flex flex-col gap-2 rounded-lg bg-canvas p-3">
              <Bar className="w-1/2 bg-foreground/50" />
              <Bar className="w-full" />
              <Bar className="w-4/5" />
            </span>
            <span className="flex flex-col gap-2 rounded-lg bg-canvas p-3">
              <Bar className="w-1/2 bg-foreground/50" />
              <Bar className="w-full" />
              <Bar className="w-3/5" />
            </span>
          </span>
        </div>
      </Card>
      <span className="absolute bottom-4 left-[30%] flex items-center gap-2 rounded-full border bg-card px-4 py-2.5 text-base font-semibold shadow-[0_18px_40px_-20px_rgba(15,23,42,0.5)]">
        <ArrowDownToLineIcon className="size-5" />
        PDF가 준비되었어요
      </span>
    </div>
  )
}
