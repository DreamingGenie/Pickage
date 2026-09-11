import { CheckIcon, Loader2Icon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { errorNotice } from '@/api/client'
import { useGeneratePdf } from '@/api/queries'
import type { PdfJob, ReportSection } from '@/api/types'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/**
 * PDF 내보내기 (기능-14 · Figma `485:1090`).
 *
 * <p>상태 셋을 한 모달 안에서 넘긴다 — `READY → GENERATING → COMPLETE`.
 * 창을 따로 띄우면 진행 중에 뒤 화면이 바뀌고, 돌아왔을 때 무엇을 만들던 중이었는지
 * 다시 알려줘야 한다.
 *
 * <h2>`BLOCKED` 는 아직 없다</h2>
 *
 * 구상안 §13.2 의 차단 사유 다섯 중 셋이 기능 비교에 달려 있고 그 기능이 없다. 지금
 * 넣으면 <b>언제나 차단인 화면</b>이 되어 아무것도 확인할 수 없다. 기능 비교가 붙을 때
 * 적격성 검사와 함께 더한다.
 *
 * <h2>진행 단계는 흉내다</h2>
 *
 * 서버가 지금은 요청 안에서 문서를 만들어 돌려주므로 단계별 신호가 없다. 그래도 단계를
 * 보여주는 이유는, 생성이 #1 워커로 옮겨가면 실제로 그 신호가 오기 때문이다 —
 * 그때 이 자리에 값만 꽂으면 된다. 대신 <b>가짜 진행률로 사용자를 속이지 않는다</b>:
 * 완료 전까지는 마지막 단계에서 멈춰 있고, 남은 시간을 예측해 보여주지 않는다.
 */
export function PdfExportDialog({
  open,
  onOpenChange,
  packages,
  from,
  to,
  snapshotAt,
  onPreview,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  packages: string[]
  from?: string
  to?: string
  snapshotAt?: string
  /** 미리보기 모달을 여는 일은 부모가 한다 — 이 모달은 닫히고 그쪽이 열려야 한다. */
  onPreview: (job: PdfJob) => void
}) {
  const [sections, setSections] = useState<ReportSection[]>([])
  const generate = useGeneratePdf()

  /* ⚠ 임시 (UI 확인용) — 아래 INSPECT 표시가 붙은 곳을 함께 지운다 ─────────── */
  const [held, setHeld] = useState(false)
  /* ───────────────────────────────────────────────────────────────────── */

  const job = generate.data

  function toggle(section: ReportSection) {
    setSections((prev) =>
      prev.includes(section) ? prev.filter((s) => s !== section) : [...prev, section],
    )
  }

  function close(next: boolean) {
    onOpenChange(next)
    // 닫으면 결과를 버린다. 다시 열었을 때 지난번 문서가 떠 있으면, 그 사이 비교 대상이
    // 바뀌었는지 사용자가 알 수 없다.
    if (!next) {
      generate.reset()
      setHeld(false) // INSPECT
    }
  }

  function submit() {
    /* ⚠ INSPECT — 생성이 너무 빨라 진행 화면을 볼 수 없어서 붙잡아 둔다.
       서버가 단계 신호를 주기 시작하면 이 자리는 그 신호로 대체된다. */
    setHeld(true)
    window.setTimeout(() => setHeld(false), STEPS.length * INSPECT_STEP_MS)

    generate.mutate({ names: packages, from, to, snapshot_at: snapshotAt, sections })
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-2xl">
        {generate.isPending || held ? (
          <Generating names={packages} />
        ) : job ? (
          <Complete job={job} onPreview={() => onPreview(job)} onClose={() => close(false)} />
        ) : (
          <Ready
            packages={packages}
            from={from}
            to={to}
            snapshotAt={snapshotAt}
            sections={sections}
            onToggle={toggle}
            error={generate.error}
            onCancel={() => close(false)}
            onSubmit={submit}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ *
 * READY — 내보내기 확인
 * ------------------------------------------------------------------ */

/**
 * IA §12.2 — <b>사용자는 여기서 문서 구성을 편집하지 않는다.</b> 정보 여섯 줄은 읽기
 * 전용이고, 고를 수 있는 것은 "더할 구역" 뿐이다.
 */
function Ready({
  packages,
  from,
  to,
  snapshotAt,
  sections,
  onToggle,
  error,
  onCancel,
  onSubmit,
}: {
  packages: string[]
  from?: string
  to?: string
  snapshotAt?: string
  sections: ReportSection[]
  onToggle: (section: ReportSection) => void
  error: unknown
  onCancel: () => void
  onSubmit: () => void
}) {
  const notice = error ? errorNotice(error) : null

  return (
    <>
      <DialogHeader>
        <DialogTitle>PDF 내보내기</DialogTitle>
        <DialogDescription>
          문서 구성을 편집하지 않고, 내보낼 보고서 상태만 확인합니다.
        </DialogDescription>
      </DialogHeader>

      <dl className="flex flex-col divide-y rounded-lg border">
        <Row label="비교 대상" value={packages.join(' · ')} />
        <Row
          label="생태계 조회 기간"
          value={from && to ? `${from} ~ ${to}` : '서버 기본 구간 (최신 스냅샷 기준 26주)'}
        />
        <Row label="Version Share 기준일" value={snapshotAt ?? '최신 스냅샷'} />
        <Row
          label="포함 내용"
          value="Downloads · 직접 Dependency · Snapshot 증감 · Version Share · 자료 상태"
        />
      </dl>

      <fieldset className="flex flex-col gap-3 rounded-lg border p-4">
        <legend className="px-1 font-medium">더할 구역</legend>

        {/*
          생태계는 끌 수 없다. 체크박스를 켠 채 잠가 두는 이유는, 아예 안 보이면
          "생태계가 들어가긴 하나" 를 사용자가 알 수 없기 때문이다.
        */}
        <label className="flex items-start gap-3 opacity-60">
          <Checkbox checked disabled aria-label="생태계 (항상 포함)" className="mt-0.5" />
          <span className="flex flex-col">
            <span>생태계 보고서</span>
            <span className="text-muted-foreground">항상 포함됩니다.</span>
          </span>
        </label>

        <SectionToggle
          section="COMMUNITY"
          label="커뮤니티 분석"
          note="아직 제공되지 않습니다. 구역 자리와 사유만 문서에 실립니다."
          checked={sections.includes('COMMUNITY')}
          onToggle={onToggle}
        />
        <SectionToggle
          section="FEATURES"
          label="기능 심화 분석"
          note="아직 제공되지 않습니다. 구역 자리와 사유만 문서에 실립니다."
          checked={sections.includes('FEATURES')}
          onToggle={onToggle}
        />
      </fieldset>

      {/* 부분 자료는 차단 사유가 아니다(구상안 §13.2). 경고와 함께 포함한다 */}
      <p className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 leading-relaxed text-amber-900">
        일부 기간 자료 없음·직접 Dependency 부족·Version Share 해석 불가는 경고와 함께 포함될 수
        있습니다.
      </p>

      {notice && <p className="text-destructive">{notice.message}</p>}

      <DialogFooter>
        <Button variant="outline" onClick={onCancel}>
          취소
        </Button>
        <Button onClick={onSubmit}>PDF 생성</Button>
      </DialogFooter>
    </>
  )
}

function SectionToggle({
  section,
  label,
  note,
  checked,
  onToggle,
}: {
  section: ReportSection
  label: string
  note: string
  checked: boolean
  onToggle: (section: ReportSection) => void
}) {
  return (
    <label className="flex items-start gap-3">
      <Checkbox
        checked={checked}
        onCheckedChange={() => onToggle(section)}
        aria-label={label}
        className="mt-0.5"
      />
      <span className="flex flex-col">
        <span>{label}</span>
        <span className="text-muted-foreground">{note}</span>
      </span>
    </label>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 px-4 py-3">
      <dt className="w-40 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1 font-mono">{value}</dd>
    </div>
  )
}

/* ------------------------------------------------------------------ *
 * GENERATING — 생성 중
 * ------------------------------------------------------------------ */

const STEPS = [
  '생태계 ReportSnapshot 확인',
  '그래프와 Snapshot 문서 배치',
  '자료 상태·해석 한계 정리',
  '파일 준비',
] as const

/**
 * ⚠ 임시 (UI 확인용) — 단계 하나를 보여줄 시간.
 *
 * 서버가 요청 안에서 문서를 만들어 돌려주므로 실제로는 순식간에 지나가 진행 화면을
 * 눈으로 볼 수 없다. 확인이 끝나면 이 상수와 `INSPECT` 표시가 붙은 자리를 지운다.
 */
const INSPECT_STEP_MS = 1000

function Generating({ names }: { names: string[] }) {
  /*
    ⚠ INSPECT — 서버가 단계 신호를 주지 않으므로 시간으로 넘긴다.
    이 컴포넌트는 생성 중에만 붙으므로 다시 열 때마다 0 에서 시작한다.
  */
  const [step, setStep] = useState(0)
  useEffect(() => {
    const id = window.setInterval(
      () => setStep((s) => Math.min(s + 1, STEPS.length - 1)),
      INSPECT_STEP_MS,
    )
    return () => window.clearInterval(id)
  }, [])

  return (
    <>
      <DialogHeader>
        <DialogTitle>PDF를 만들고 있습니다</DialogTitle>
        <DialogDescription className="font-mono">{names.join(' · ')}</DialogDescription>
      </DialogHeader>

      {/* 진행 막대. 남은 시간을 예측하지 않고 지나온 단계만 비율로 보인다 */}
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-foreground transition-[width] duration-500"
          style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
        />
      </div>

      <ul className="flex flex-col gap-1">
        {STEPS.map((label, i) => {
          const done = i < step
          const current = i === step
          return (
            <li key={label} className="flex items-center gap-3 rounded-md px-3 py-2.5">
              {done ? (
                <CheckIcon className="size-4 shrink-0 text-emerald-600" aria-hidden />
              ) : current ? (
                <Loader2Icon className="size-4 shrink-0 animate-spin" aria-hidden />
              ) : (
                <span aria-hidden className="size-4 shrink-0 rounded-full border" />
              )}
              <span className={cn(done || current ? 'text-foreground' : 'text-muted-foreground')}>
                {label}
              </span>
            </li>
          )
        })}
      </ul>

      <p className="text-muted-foreground">이 창을 닫아도 생성은 계속됩니다.</p>
    </>
  )
}

/* ------------------------------------------------------------------ *
 * COMPLETE — 준비됨
 * ------------------------------------------------------------------ */

function Complete({
  job,
  onPreview,
  onClose,
}: {
  job: PdfJob
  onPreview: () => void
  onClose: () => void
}) {
  return (
    <>
      <DialogHeader>
        <span aria-hidden className="text-2xl text-emerald-600">
          <CheckIcon className="size-7" />
        </span>
        <DialogTitle>PDF가 준비되었습니다</DialogTitle>
        <DialogDescription className="font-mono">{job.file_name}</DialogDescription>
      </DialogHeader>

      <p className="text-muted-foreground">
        {new Date(job.created_at).toLocaleString('ko-KR')} · {formatBytes(job.bytes)}
      </p>

      {/*
        요청했지만 못 채운 구역. 조용히 넘어가면 사용자는 체크한 것이 사라진 이유를
        알 수 없다 — 문서 안에도 같은 말이 적혀 있다.
      */}
      {job.omitted.length > 0 && (
        <p className="rounded-lg border border-dashed px-4 py-3 leading-relaxed text-muted-foreground">
          {job.omitted.map(sectionLabel).join(' · ')} 구역은 해당 분석 기능이 아직 없어 자리와
          사유만 실렸습니다.
        </p>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          닫기
        </Button>
        <Button onClick={onPreview}>미리보기</Button>
      </DialogFooter>
    </>
  )
}

function sectionLabel(section: ReportSection): string {
  return section === 'COMMUNITY' ? '커뮤니티 분석' : '기능 심화 분석';
}

/** 크기는 사람이 읽는 값이라 반올림한다. 정확한 바이트 수가 필요한 화면이 아니다. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  return kb < 1024 ? `${kb.toFixed(0)} KB` : `${(kb / 1024).toFixed(1)} MB`
}
