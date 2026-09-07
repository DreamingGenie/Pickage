import { SettingsIcon } from 'lucide-react'

import {
  INTERVALS,
  type PackageCardModel,
  type SnapshotWindow,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

export interface EcosystemControls {
  window: SnapshotWindow
  intervalKey: string
}

/**
 * 차트 위 공통 조작줄.
 *
 * 구간은 상대 기간이 아니라 **실제 스냅샷 날짜**로 고른다.
 * 목록에 없는 날짜는 고를 수 없으므로, 화면에 뜬 시작·끝은 언제나 서버가 가진
 * 스냅샷과 같은 것을 가리킨다.
 */
export function EcosystemToolbar({
  controls,
  onChange,
  /** 고를 수 있는 스냅샷 날짜. 오름차순. */
  snapshots,
  packages,
  onVersionChange,
  className,
}: {
  controls: EcosystemControls
  onChange: (next: EcosystemControls) => void
  snapshots: string[]
  packages: PackageCardModel[]
  onVersionChange: (key: string, version: string) => void
  className?: string
}) {
  const { start, end } = controls.window
  const si = snapshots.indexOf(start)
  const ei = snapshots.indexOf(end)
  const count = si >= 0 && ei >= si ? ei - si + 1 : 0

  function setStart(v: string) {
    // 끝을 넘어서면 끝도 같이 민다. 뒤집힌 구간을 만들지 않는다.
    const next = snapshots.indexOf(v) > ei ? { start: v, end: v } : { start: v, end }
    onChange({ ...controls, window: next })
  }
  function setEnd(v: string) {
    const next = snapshots.indexOf(v) < si ? { start: v, end: v } : { start, end: v }
    onChange({ ...controls, window: next })
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-x-5 gap-y-3', className)}>
      <div className="flex items-center gap-2">
        <span className="text-[11px] whitespace-nowrap text-muted-foreground">스냅샷 구간</span>
        <DateSelect value={start} options={snapshots} onChange={setStart} label="시작 스냅샷" />
        <span className="text-[11px] text-muted-foreground">~</span>
        <DateSelect value={end} options={snapshots} onChange={setEnd} label="끝 스냅샷" />
        <span className="font-mono text-[10.5px] text-muted-foreground tabular-nums">
          {count}주
        </span>
        <button
          type="button"
          onClick={() =>
            onChange({
              ...controls,
              window: { start: snapshots[0], end: snapshots[snapshots.length - 1] },
            })
          }
          className="text-[11px] text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          전체
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-[11px] whitespace-nowrap text-muted-foreground">표시 간격</span>
        <div
          className="flex gap-0.5 rounded-md bg-muted p-0.5"
          role="group"
          aria-label="스냅샷 표시 간격"
        >
          {INTERVALS.map((it) => {
            const active = controls.intervalKey === it.key
            return (
              <button
                key={it.key}
                type="button"
                onClick={() => onChange({ ...controls, intervalKey: it.key })}
                aria-pressed={active}
                className={cn(
                  'rounded-[5px] px-2 py-1 text-[11px] transition-colors',
                  active
                    ? 'bg-background font-medium text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {it.label}
              </button>
            )
          })}
        </div>
      </div>

      <VersionSettings packages={packages} onChange={onVersionChange} className="ml-auto" />
    </div>
  )
}

function DateSelect({
  value,
  options,
  onChange,
  label,
}: {
  value: string
  options: string[]
  onChange: (v: string) => void
  label: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={label}
      className="h-7 rounded-md border border-input bg-background px-2 font-mono text-[11.5px] transition-colors hover:border-foreground/40"
    >
      {options.map((d) => (
        <option key={d} value={d}>
          {d}
        </option>
      ))}
    </select>
  )
}

/**
 * 패키지별 Dependents 표시 버전.
 *
 * 세 드롭다운은 서로 독립이고, 여기서 버전을 바꿔도 기능 비교(03B) 결과와
 * 분석 캐시는 무효화되지 않는다(구상안 1.2 · IA 8.2).
 */
function VersionSettings({
  packages,
  onChange,
  className,
}: {
  packages: PackageCardModel[]
  onChange: (key: string, version: string) => void
  className?: string
}) {
  return (
    <details className={cn('group relative', className)}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors hover:border-foreground/40 [&::-webkit-details-marker]:hidden">
        <SettingsIcon className="size-3.5" aria-hidden />
        표시 버전
      </summary>

      <div className="absolute top-full right-0 z-20 mt-1.5 flex w-[262px] flex-col gap-2.5 rounded-lg border bg-background p-3 shadow-lg">
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Dependents 그래프에만 적용됩니다. 기능 비교 버전과 분석 결과는 바뀌지 않습니다.
        </p>
        {packages.map((p) => (
          <label key={p.key} className="flex items-center justify-between gap-2">
            <span className="truncate font-mono text-[12px]">{p.key}</span>
            <select
              value={p.selectedDisplayVersion}
              onChange={(e) => onChange(p.key, e.target.value)}
              className="h-7 rounded-md border border-input bg-background px-2 font-mono text-[11.5px]"
            >
              {p.availableDisplayVersions.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
    </details>
  )
}
