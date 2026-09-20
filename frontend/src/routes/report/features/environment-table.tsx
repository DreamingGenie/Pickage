import type { ComparisonPackage, EnvironmentRow } from '@/routes/report/features/model'
import { cn } from '@/lib/utils'

/**
 * 핵심 비교 요약 — 버전별 소비 조건 (기능-11-R01, IA §9.1-4).
 *
 * <h2>AI 비교를 기다리지 않는다</h2>
 *
 * 값이 전부 `GET /api/packages/env` 에서 온다. 배치가 미리 접어 둔 표를 키 조회하는 것이라
 * 즉시 뜬다 — 그래서 이 표는 AI 영역보다 **위**에 있고, 분석이 도는 중에도 흐려지지 않는다.
 * 기능-10-R06 의 "완료된 항목 먼저 표시" 가 이 모양이다.
 *
 * 217 에서는 이 표가 기능 비교 응답 안에 있었다. 백엔드가 둘을 다른 엔드포인트로 나누면서
 * 데이터 출처만 바뀌었고, 표 자체는 그대로다.
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
        <div className="h-24 w-full animate-pulse rounded bg-muted/60" />
      </section>
    )
  }

  if (rows.length === 0) return null

  return (
    <section aria-labelledby="environment-title" className="flex flex-col gap-5 rounded-2xl border p-6">
      <header className="flex flex-col gap-1.5">
        <h3 id="environment-title" className="text-sm font-semibold">
          핵심 비교 요약
        </h3>
        <p className="text-base text-muted-foreground">
          정확한 버전의 배포 산출물에서 확인한 소비 조건입니다.
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
                <th key={pkg.name} scope="col" className="pb-3 text-left font-mono font-normal">
                  {pkg.name}
                  <span className="text-muted-foreground/70">@{pkg.version}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-t align-top">
                <th scope="row" className="py-3 pr-3 text-left font-normal text-muted-foreground">
                  {row.label}
                </th>
                {row.values.map((value, i) => (
                  <td
                    key={packages[i].name}
                    className={cn('py-3 pr-3', value === null && 'text-muted-foreground')}
                  >
                    {value ?? '미확인'}
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
        빈 행을 두면 "조건이 없다" 로 읽히므로 아예 만들지 않는다. 그 사실을 화면에 적지도
        않는다. 없는 항목을 설명하면 사용자가 무엇을 못 봤는지 알 수 없는 채로 신경만 쓴다.
      */}
    </section>
  )
}
