import { INTERVALS, type SnapshotWindow } from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

export interface EcosystemControls {
  /** 받아 둔 전체 구간 안에서 잘라 보기. */
  window: SnapshotWindow
  /** 표시 간격. */
  intervalKey: string
}

/**
 * 차트 위 공통 조작줄.
 *
 * <p><b>여기의 어떤 조작도 서버를 다시 부르지 않는다.</b> 추이는 보유한 전 구간을 한 번에
 * 받아 두었고(S15P21A506-374), 시작·끝을 고르는 일과 간격을 솎는 일은 그 위에서 끝난다.
 *
 * <p>처음에는 "26주 / 52주 / 104주" 버튼이 서버 조회 범위를 바꾸고, 그와 별개로 아래 드롭다운이
 * 받은 것을 자르는 구조였다. 명세 §1 의 "기간만 바꾸면 추이만 다시 받으면 된다" 를 그대로
 * 옮긴 것이었는데, <b>화면에서는 둘 다 똑같이 "구간 고르기" 로 보인다.</b> 26주 상태에서
 * "전체" 를 눌러도 26주가 끝이고, 넓히려면 버튼·좁히려면 드롭다운이라 어디를 만질지 헷갈렸다.
 * 지금은 조작이 하나뿐이라 그 구분 자체가 없다.
 *
 * <p>구간은 상대 기간("최근 1년")이 아니라 <b>실제 스냅샷 날짜</b>로 고른다. 목록에 없는
 * 날짜는 고를 수 없으므로, 화면에 뜬 시작·끝은 언제나 서버가 준 스냅샷을 가리킨다.
 */
export function EcosystemToolbar({
  controls,
  onChange,
  /** 응답에 들어 있는 스냅샷 날짜. 오름차순. */
  snapshots,
  className,
}: {
  controls: EcosystemControls
  onChange: (next: EcosystemControls) => void
  snapshots: string[]
  className?: string
}) {
  const { start, end } = controls.window
  const si = snapshots.indexOf(start)
  const ei = snapshots.indexOf(end)

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
        <span className="text-base whitespace-nowrap text-muted-foreground">조회 기간</span>
        <DateSelect value={start} options={snapshots} onChange={setStart} label="조회 시작일" />
        <span className="text-base text-muted-foreground">~</span>
        <DateSelect value={end} options={snapshots} onChange={setEnd} label="조회 종료일" />
      </div>

      <div className="ml-auto flex items-center gap-2">
        <span className="text-base whitespace-nowrap text-muted-foreground">표시 간격</span>
        <SegmentedControl
          label="표시 간격"
          options={INTERVALS.map((i) => ({ key: i.key, label: i.label }))}
          value={controls.intervalKey}
          onChange={(key) => onChange({ ...controls, intervalKey: key })}
        />
      </div>
    </div>
  )
}

function SegmentedControl({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { key: string; label: string }[]
  value: string
  onChange: (key: string) => void
}) {
  return (
    <div className="flex gap-0.5 rounded-md bg-muted p-0.5" role="group" aria-label={label}>
      {options.map((o) => {
        const active = value === o.key
        return (
          <button
            key={o.key}
            type="button"
            onClick={() => onChange(o.key)}
            aria-pressed={active}
            className={cn(
              'rounded-[5px] px-2 py-1 text-base transition-colors',
              active
                ? 'bg-background font-medium text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {o.label}
          </button>
        )
      })}
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
      disabled={options.length === 0}
      className="h-7 rounded-md border border-input bg-background px-2 font-mono text-base transition-colors hover:border-foreground/40 disabled:opacity-50"
    >
      {options.map((d) => (
        <option key={d} value={d}>
          {d}
        </option>
      ))}
    </select>
  )
}
