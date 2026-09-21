import { SegmentedControl } from '@/components/common/segmented-control'
import {
  INTERVALS,
  PERIOD_PRESETS,
  resolvePreset,
  type PeriodPresetKey,
  type SnapshotWindow,
} from '@/routes/report/ecosystem/model'
import { cn } from '@/lib/utils'

export interface EcosystemControls {
  /** 받아 둔 전체 구간 안에서 잘라 보기. */
  window: SnapshotWindow
  /**
   * 눌려 있는 기간 프리셋. `null` 이면 아래 날짜를 직접 골라 프리셋에 해당하지 않는 구간이다.
   * 날짜에서 거꾸로 추론하지 않고 **고른 사실 그대로** 들고 있다 — 자료가 프리셋보다 짧으면 서로 다른
   * 프리셋이 같은 구간이 되어, 추론하면 누른 것과 다른 버튼이 켜진다.
   */
  presetKey: PeriodPresetKey | null
  /** 표시 간격. */
  intervalKey: string
}

/**
 * 차트 위 공통 조작줄.
 *
 * <p><b>여기의 어떤 조작도 서버를 다시 부르지 않는다.</b> 추이는 쌓아 둔 전 구간을 한 번에
 * 받아 두었고, 시작·끝을 고르는 일과 간격을 솎는 일은 그 위에서 끝난다.
 *
 * <p>처음에는 "26주 / 52주 / 104주" 버튼이 서버 조회 범위를 바꾸고, 그와 별개로 아래 드롭다운이
 * 받은 것을 자르는 구조였다. 명세 §1 의 "기간만 바꾸면 추이만 다시 받으면 된다" 를 그대로
 * 옮긴 것이었는데, <b>화면에서는 둘 다 똑같이 "구간 고르기" 로 보인다.</b> 26주 상태에서
 * "전체" 를 눌러도 26주가 끝이고, 넓히려면 버튼·좁히려면 드롭다운이라 어디를 만질지 헷갈렸다.
 * 지금은 조작이 하나뿐이라 그 구분 자체가 없다.
 *
 * <p>구간은 <b>실제 집계 날짜</b>로 고른다. 목록에 없는 날짜는 고를 수 없으므로, 화면에 뜬
 * 시작·끝은 언제나 서버가 준 집계를 가리킨다. 위쪽 프리셋("전체 기간·반년·1년…")도 이 원칙을
 * 깨지 않는다 — 누르면 `resolvePreset` 이 상대 기간을 실제 집계 날짜로 풀어 아래 날짜 선택에
 * 채운다(S15P21A506-405). 날짜를 직접 고르면 프리셋 선택이 풀린다.
 *
 * <p>"스냅샷" 이라는 말은 화면에 쓰지 않는다. 우리 쪽 수집 단위의 이름이지 읽는 사람이
 * 아는 말이 아니다.
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
    onChange({ ...controls, window: next, presetKey: null })
  }
  function setEnd(v: string) {
    const next = snapshots.indexOf(v) < si ? { start: v, end: v } : { start, end: v }
    onChange({ ...controls, window: next, presetKey: null })
  }
  function pickPreset(key: PeriodPresetKey) {
    if (snapshots.length === 0) return
    onChange({ ...controls, window: resolvePreset(key, snapshots), presetKey: key })
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-x-5 gap-y-3', className)}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="text-base whitespace-nowrap text-muted-foreground">조회 기간</span>
        {/* 프리셋이 먼저이고, 그 오른쪽에 세부 기간이 온다. 눌린 것이 없으면(`''`) 직접 고른 구간이다. */}
        <SegmentedControl
          label="조회 기간 프리셋"
          options={PERIOD_PRESETS.map((p) => ({ key: p.key, label: p.label }))}
          value={controls.presetKey ?? ''}
          onChange={(key) => pickPreset(key as PeriodPresetKey)}
        />
        <span aria-hidden className="h-4 w-px bg-border" />
        <div className="flex items-center gap-2">
          <DateSelect value={start} options={snapshots} onChange={setStart} label="시작일" />
          <span className="text-base text-muted-foreground">~</span>
          <DateSelect value={end} options={snapshots} onChange={setEnd} label="종료일" />
        </div>
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
