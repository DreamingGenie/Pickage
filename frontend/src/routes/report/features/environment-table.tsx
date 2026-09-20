import { cn } from '@/lib/utils'
import type { ComparisonView } from '@/routes/report/features/model'

/**
 * 핵심 비교 요약 — 공통 환경·설치 조건 (IA §9.1-4).
 *
 * 이 표는 구조화 데이터 계층이 있어야 채워진다(구상안 §1.4). 그 계층이 없으면 응답의
 * `environment` 가 비어 있고, 그때는 **섹션 자체를 그리지 않는다** — 빈 표를 두면 확인한 것이
 * 없다는 사실이 확인 결과처럼 읽힌다. 값이 없는 칸만 `미확인` 으로 적는다.
 */
export function EnvironmentTable({ view, dimmed }: { view: ComparisonView; dimmed: boolean }) {
  if (view.environment.length === 0) return null

  return (
    <section
      aria-labelledby="environment-title"
      className={cn(
        'flex flex-col gap-5 rounded-2xl border p-6 transition-opacity',
        dimmed && 'opacity-60',
      )}
    >
      <header className="flex flex-col gap-1.5">
        <h3 id="environment-title" className="text-sm font-semibold">
          핵심 비교 요약
        </h3>
        <p className="text-base text-muted-foreground">
          정확한 버전의 배포 산출물에서 확인한 핵심 조건입니다.
        </p>
      </header>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-base">
          <thead>
            <tr className="text-muted-foreground">
              <th scope="col" className="pb-3 text-left font-normal">
                항목
              </th>
              {view.packages.map((pkg) => (
                <th key={pkg.name} scope="col" className="pb-3 text-left font-mono font-normal">
                  {pkg.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {view.environment.map((row) => (
              <tr key={row.key} className="border-t align-top">
                <th scope="row" className="py-3 pr-3 text-left font-normal text-muted-foreground">
                  {row.label}
                </th>
                {row.values.map((value, i) => (
                  <td
                    key={view.packages[i].name}
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

      {view.environmentNote && (
        <p className="text-base leading-relaxed text-muted-foreground">{view.environmentNote}</p>
      )}
    </section>
  )
}
