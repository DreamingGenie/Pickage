import { CheckIcon, CircleQuestionMarkIcon, type LucideIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import type {
  ComparisonPackage,
  EnvTone,
  EnvValue,
  EnvironmentRow,
} from '@/routes/report/features/model'

/**
 * 핵심 비교 요약 — 버전별 소비 조건 (기능-11-R01, IA §9.1-4).
 *
 * <h2>AI 비교를 기다리지 않는다</h2>
 *
 * 값이 전부 `GET /api/packages/env` 에서 온다. 배치가 미리 접어 둔 표를 키 조회하는 것이라
 * 즉시 뜬다 — 그래서 이 표는 AI 영역보다 **위**에 있고, 분석이 도는 중에도 흐려지지 않는다.
 * 기능-10-R06 의 "완료된 항목 먼저 표시" 가 이 모양이다.
 *
 * <h2>아래 기능 비교표와 같은 모양으로 그린다</h2>
 *
 * 칸마다 라벨을 붙여 한눈에 비교되게 한다. 다만 **색이 뜻하는 바가 다르다** — 아래는 판정
 * (지원·미지원)이라 좋고 나쁨이 있지만, 여기는 사실이라 종류만 구분한다. 그래서 빨강을 쓰지
 * 않고, 초록은 "타입 포함" 처럼 쓰는 사람에게 일이 줄어드는 경우에만 쓴다.
 *
 * <h2>빈 표를 그리지 않는다</h2>
 *
 * 한 건도 못 찾으면 섹션 자체를 그리지 않는다 — 빈 표를 두면 확인한 것이 없다는 사실이
 * 확인 결과처럼 읽힌다. 값이 없는 **칸만** `미확인` 으로 적는다.
 */
export function EnvironmentTable({
  packages,
  rows,
  note,
  loading,
}: {
  packages: readonly ComparisonPackage[]
  rows: readonly EnvironmentRow[]
  /** 못 찾은 대상이 있을 때의 안내. 없으면 null */
  note: string | null
  loading: boolean
}) {
  if (loading) {
    return (
      <section className="flex flex-col gap-5 rounded-2xl border p-6">
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
        <div className="flex flex-col gap-3">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-8 w-full animate-pulse rounded-md bg-muted/60" />
          ))}
        </div>
      </section>
    )
  }

  if (rows.length === 0) return null

  return (
    <section
      aria-labelledby="environment-title"
      className="flex flex-col gap-5 rounded-2xl border p-6"
    >
      <header className="flex flex-col gap-1.5">
        <h3 id="environment-title" className="text-sm font-semibold">
          설치하기 전에 알아 둘 것
        </h3>
        <p className="text-base text-muted-foreground">
          npm 에 올라온 파일에서 그대로 읽었어요. AI 가 판단한 내용이 아니에요.
        </p>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-base">
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col" className="pb-3 text-left font-normal">
                항목
              </th>
              {packages.map((pkg) => (
                <th key={pkg.name} scope="col" className="pb-3 text-left font-normal">
                  <span className="font-mono text-foreground">{pkg.name}</span>
                  <span className="ml-1.5 font-mono">{pkg.version}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-t align-top">
                <th scope="row" className="py-3 pr-3 text-left font-normal">
                  <span className="block text-foreground">{row.label}</span>
                  <span className="block text-sm leading-snug text-muted-foreground">
                    {row.hint}
                  </span>
                </th>
                {row.values.map((value, i) => (
                  <td key={packages[i].name} className="py-3 pr-3">
                    <EnvPill value={value} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {note && <p className="text-base leading-relaxed text-muted-foreground">{note}</p>}

      {/*
        실행 조건(engines)은 이 표에 없다. 기능-11-R01 의 항목이지만 수집에 포함되지 않았다 —
        빈 행을 두면 "조건이 없다" 로 읽히므로 아예 만들지 않는다.
      */}
    </section>
  )
}

const TONE: Record<EnvTone, { className: string; Icon?: LucideIcon }> = {
  neutral: { className: 'bg-muted text-foreground' },
  info: { className: 'bg-sky-50 text-sky-700' },
  positive: { className: 'bg-emerald-50 text-emerald-700', Icon: CheckIcon },
  unknown: { className: 'bg-muted text-muted-foreground', Icon: CircleQuestionMarkIcon },
}

/** 아래 기능 비교표의 `VerdictPill` 과 같은 모양. 값이 없으면 `미확인` 으로 적는다. */
function EnvPill({ value }: { value: EnvValue | null }) {
  const { text, tone } = value ?? { text: '알 수 없음', tone: 'unknown' as const }
  const { className, Icon } = TONE[tone]
  return (
    <span
      className={cn(
        'inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 text-base font-medium',
        className,
      )}
    >
      {Icon && <Icon className="size-3" strokeWidth={2.5} aria-hidden />}
      {text}
    </span>
  )
}
