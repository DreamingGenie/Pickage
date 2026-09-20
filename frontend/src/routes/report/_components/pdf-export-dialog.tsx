import { CheckIcon, CircleAlertIcon, DownloadIcon, Loader2Icon } from 'lucide-react'
import { useEffect, useState } from 'react'

import { errorNotice } from '@/api/client'
import { pdfDownloadUrl } from '@/api/endpoints'
import { useGeneratePdf } from '@/api/queries'
import type { PdfJob, ReportSection, TransitionPeriodParam } from '@/api/types'
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
import type { AnalysisRun } from '@/routes/report/_components/use-analysis-run'
import { TRANSITION_PERIODS } from '@/routes/report/ecosystem/transitions-model'

/**
 * PDF 내보내기 (기능-14 · Figma `485:1090`).
 *
 * <p>상태 다섯을 한 모달 안에서 넘긴다 — `READY → GENERATING → COMPLETE`, 적격성 실패는
 * `BLOCKED`, 생성 시작 후 실패는 `FAILED`(구상안 §13.2·13.3). 창을 따로 띄우면 진행 중에
 * 뒤 화면이 바뀌고, 돌아왔을 때 무엇을 만들던 중이었는지 다시 알려줘야 한다.
 *
 * <h2>`BLOCKED` 사유는 아직 둘뿐이다</h2>
 *
 * 구상안 §13.2 의 차단 사유 다섯 중 클라이언트에서 지금 실제로 판단 가능한 건
 * `FEATURE_ANALYSIS_REQUIRED`(기능 비교 미실행)·`VERSION_RESULT_MISMATCH`(재분석 중,
 * `ANALYSIS_RUNNING`과 겹쳐 판단)뿐이다. 나머지 셋(`COMPARISON_NOT_CONFIRMED`·
 * `ECOSYSTEM_RESULT_INCOMPLETE`·`SNAPSHOT_CREATION_ERROR`)은 타입에는 있지만 판단할
 * 신호가 아직 없어 항상 통과시킨다 — 신호가 생기면 `blockReasonsFor` 안의 조건만 채운다.
 *
 * <h2>진행 표시는 있는 신호만 쓴다</h2>
 *
 * 서버가 지금은 요청 안에서 문서를 만들어 돌려주므로 단계별 신호가 없다. 예전엔 가짜
 * 타이머로 단계를 흉내 냈으나(INSPECT 스캐폴딩, S15P21A506-220에서 제거) 실제로 없는
 * 정보를 지어내는 셈이라 뺐다 — `generate.isPending` 하나로 "진행 중"만 보여준다.
 */
export function PdfExportDialog({
  open,
  onOpenChange,
  packages,
  from,
  to,
  snapshotAt,
  transitionPeriod,
  run,
  onPreview,
  onGoToFeatures,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  packages: string[]
  from?: string
  to?: string
  snapshotAt?: string
  /**
   * 화면이 지금 보고 있는 유지·유입·이탈 구간. 선택 사항으로 두면 안 넘기는 실수가 조용히
   * 통과되고, 그러면 화면에서 1y·5y를 보다가 PDF를 내보내도 서버 기본값(3y)으로 문서가
   * 조용히 달라진다 — 공통-R08(화면과 PDF 결과가 일치해야 한다)을 어기는 상황이라 필수로
   * 둔다(S15P21A506-394).
   */
  transitionPeriod: TransitionPeriodParam
  /** 기능 비교 진행 상태 — BLOCKED 판단과 재분석 시 stale COMPLETE 방지에 쓴다. */
  run: AnalysisRun
  /** 미리보기 모달을 여는 일은 부모가 한다 — 이 모달은 닫히고 그쪽이 열려야 한다. */
  onPreview: (job: PdfJob) => void
  /** BLOCKED 화면에서 "기능 비교로 이동"을 눌렀을 때. 탭 전환은 부모(report-page)가 한다. */
  onGoToFeatures: () => void
}) {
  const [sections, setSections] = useState<ReportSection[]>([])
  const generate = useGeneratePdf()
  const job = generate.data
  const blockReasons = blockReasonsFor(run)
  const blocked = blockReasons.length > 0

  // 재분석이 새로 시작되면 이전 COMPLETE 파일을 더는 "지금 선택 버전 결과"로 보여주지
  // 않는다 — 실제로 있던 버그(다이얼로그가 report-page에 항상 마운트돼 있어 미리보기로
  // 넘어간 뒤엔 생성 결과가 리셋되지 않고 남아 있었다).
  useEffect(() => {
    generate.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.runId])

  function toggle(section: ReportSection) {
    setSections((prev) =>
      prev.includes(section) ? prev.filter((s) => s !== section) : [...prev, section],
    )
  }

  function close(next: boolean) {
    onOpenChange(next)
    // 닫으면 결과를 버린다. 다시 열었을 때 지난번 문서가 떠 있으면, 그 사이 비교 대상이
    // 바뀌었는지 사용자가 알 수 없다.
    if (!next) generate.reset()
  }

  function submit() {
    generate.mutate({
      names: packages,
      from,
      to,
      snapshot_at: snapshotAt,
      period: transitionPeriod,
      sections,
    })
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-2xl">
        {generate.isPending ? (
          <Generating names={packages} />
        ) : generate.isError ? (
          <Failed error={generate.error} onRetry={submit} onClose={() => close(false)} />
        ) : job ? (
          <Complete job={job} onPreview={() => onPreview(job)} onClose={() => close(false)} />
        ) : blocked ? (
          <Blocked
            reasons={blockReasons}
            onGoToFeatures={() => {
              close(false)
              onGoToFeatures()
            }}
            onClose={() => close(false)}
          />
        ) : (
          <Ready
            packages={packages}
            from={from}
            to={to}
            snapshotAt={snapshotAt}
            transitionPeriod={transitionPeriod}
            sections={sections}
            onToggle={toggle}
            onCancel={() => close(false)}
            onSubmit={submit}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------------------------------------------ *
 * BLOCKED — 적격성 실패 (구상안 §13.2)
 * ------------------------------------------------------------------ */

type BlockReason =
  | 'COMPARISON_NOT_CONFIRMED'
  | 'ECOSYSTEM_RESULT_INCOMPLETE'
  | 'SNAPSHOT_CREATION_ERROR'
  | 'FEATURE_ANALYSIS_REQUIRED'
  | 'VERSION_RESULT_MISMATCH'

const BLOCK_REASON_LABEL: Record<BlockReason, string> = {
  COMPARISON_NOT_CONFIRMED: '비교 대상이 아직 확정되지 않았습니다.',
  ECOSYSTEM_RESULT_INCOMPLETE: '생태계 분석 결과가 아직 준비되지 않았습니다.',
  SNAPSHOT_CREATION_ERROR: '보고서 사본을 만드는 중 오류가 발생했습니다.',
  FEATURE_ANALYSIS_REQUIRED: '기능 비교 분석이 아직 실행되지 않았습니다.',
  VERSION_RESULT_MISMATCH: '기능 비교가 다시 실행되는 중입니다. 완료 후 다시 시도해 주세요.',
}

/**
 * 지금 실제로 판단 가능한 두 사유만 채운다. 나머지 셋은 신호가 없어 늘 통과한다 —
 * 자세한 사유는 이 파일 상단 주석 참고.
 */
function blockReasonsFor(run: AnalysisRun): BlockReason[] {
  if (!run.hasCompletedOnce) return ['FEATURE_ANALYSIS_REQUIRED']
  if (run.status === 'RUNNING') return ['VERSION_RESULT_MISMATCH']
  return []
}

function Blocked({
  reasons,
  onGoToFeatures,
  onClose,
}: {
  reasons: BlockReason[]
  onGoToFeatures: () => void
  onClose: () => void
}) {
  return (
    <>
      <DialogHeader>
        <span aria-hidden className="text-2xl text-muted-foreground">
          <CircleAlertIcon className="size-7" />
        </span>
        <DialogTitle>지금은 PDF를 만들 수 없습니다</DialogTitle>
      </DialogHeader>

      <ul className="flex flex-col gap-2 rounded-lg border px-4 py-3">
        {reasons.map((r) => (
          <li key={r} className="flex items-start gap-2">
            <CircleAlertIcon className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
            <span>{BLOCK_REASON_LABEL[r]}</span>
          </li>
        ))}
      </ul>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          닫기
        </Button>
        <Button onClick={onGoToFeatures}>기능 비교로 이동</Button>
      </DialogFooter>
    </>
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
  transitionPeriod,
  sections,
  onToggle,
  onCancel,
  onSubmit,
}: {
  packages: string[]
  from?: string
  to?: string
  snapshotAt?: string
  transitionPeriod: TransitionPeriodParam
  sections: ReportSection[]
  onToggle: (section: ReportSection) => void
  onCancel: () => void
  onSubmit: () => void
}) {
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
        {/* 조건을 주지 않으면 화면의 기본값이다 — 전체 기간, 주 단위. 의존 수 그래프는 실제값으로 그린다. */}
        <Row
          label="생태계 조회 기간"
          value={from && to ? `${from} ~ ${to}` : '보유한 전 기간 · 매주'}
        />
        <Row label="Version Share 기준일" value={snapshotAt ?? '가장 최근 집계'} />
        <Row label="유지·유입·이탈 조회 기간" value={transitionPeriodLabel(transitionPeriod)} />
        <Row
          label="포함 내용"
          value="그래프와 수치 표 — Downloads · 의존 수(실제값) · Version Share · 유지·유입·이탈 · 자료 상태"
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
          note="기준 패키지의 GitHub 저장소 수치·핵심 논의·실제 논의 흐름이 실립니다. 자료가 아직 수집되지 않았다면 그 안내만 실립니다."
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

function transitionPeriodLabel(period: TransitionPeriodParam): string {
  return TRANSITION_PERIODS.find((p) => p.key === period)?.label ?? period
}

/* ------------------------------------------------------------------ *
 * GENERATING — 생성 중
 * ------------------------------------------------------------------ */

/**
 * 서버가 요청 안에서 문서를 만들어 돌려주므로 단계별 신호가 없다. 예전엔 타이머로 단계를
 * 흉내 냈지만(S15P21A506-220에서 제거) 없는 정보를 지어내는 셈이었다 — `isPending` 하나로
 * "진행 중"만 정직하게 보여준다. 생성이 #1 워커로 옮겨가 실제 단계 신호가 오면 그때
 * 다시 단계별 표시를 붙인다.
 */
function Generating({ names }: { names: string[] }) {
  return (
    <>
      <DialogHeader>
        <DialogTitle>PDF를 만들고 있습니다</DialogTitle>
        <DialogDescription className="font-mono">{names.join(' · ')}</DialogDescription>
      </DialogHeader>

      <div className="flex items-center gap-3 rounded-lg border px-4 py-3">
        <Loader2Icon className="size-4 shrink-0 animate-spin" aria-hidden />
        <span>생태계 결과와 자료 상태를 정리해 문서를 만드는 중입니다.</span>
      </div>

      <p className="text-muted-foreground">이 창을 닫아도 생성은 계속됩니다.</p>
    </>
  )
}

/* ------------------------------------------------------------------ *
 * FAILED — 생성 실패 (구상안 §13.3: 다운로드 실패와 분리)
 * ------------------------------------------------------------------ */

function Failed({
  error,
  onRetry,
  onClose,
}: {
  error: unknown
  onRetry: () => void
  onClose: () => void
}) {
  const notice = errorNotice(error)
  return (
    <>
      <DialogHeader>
        <span aria-hidden className="text-2xl text-destructive">
          <CircleAlertIcon className="size-7" />
        </span>
        <DialogTitle>PDF 생성에 실패했습니다</DialogTitle>
        <DialogDescription>{notice.message}</DialogDescription>
      </DialogHeader>

      <p className="text-muted-foreground">
        완료된 파일이 있다고 가정하지 않습니다. 다시 시도하면 새로 만듭니다.
      </p>

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          닫기
        </Button>
        <Button onClick={onRetry}>다시 시도</Button>
      </DialogFooter>
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
        알 수 없다 — 문서 안에도 같은 말이 적혀 있다. 이유는 구역마다 다르다.
      */}
      {job.omitted.length > 0 && (
        <ul className="flex flex-col gap-1 rounded-lg border border-dashed px-4 py-3 leading-relaxed text-muted-foreground">
          {job.omitted.map((section) => (
            <li key={section}>{omittedNote(section)}</li>
          ))}
        </ul>
      )}

      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          닫기
        </Button>
        <Button variant="outline" onClick={onPreview}>
          미리보기
        </Button>
        {/*
          미리보기를 거치지 않고 바로 받는다. 버튼이 아니라 링크다 — 서버가 attachment 로 보내므로 여는 것만으로
          저장된다(미리보기 모달의 다운로드와 같은 방식). blob 을 만들면 같은 파일을 메모리에 한 번 더 들고 있어야 한다.
        */}
        <Button asChild>
          <a href={pdfDownloadUrl(job.report_id)} download={job.file_name}>
            <DownloadIcon className="size-4" aria-hidden />
            다운로드
          </a>
        </Button>
      </DialogFooter>
    </>
  )
}

/**
 * 채우지 못한 구역의 이유. 둘은 이유가 다르다 — 기능 심화 분석은 기능이 아직 없어서, 커뮤니티 분석은 이 패키지의
 * 자료가 아직 수집되지 않아서다(기능은 있다). 같은 말로 안내하면 커뮤니티가 "미완성 기능"으로 읽힌다.
 */
function omittedNote(section: ReportSection): string {
  return section === 'COMMUNITY'
    ? '커뮤니티 분석: 이 패키지의 GitHub 자료가 아직 수집되지 않아 안내만 실렸습니다. GitHub 커뮤니티 탭을 한 번 연 뒤 다시 만들면 채워집니다.'
    : '기능 심화 분석: 해당 분석 기능이 아직 없어 자리와 사유만 실렸습니다.'
}

/** 크기는 사람이 읽는 값이라 반올림한다. 정확한 바이트 수가 필요한 화면이 아니다. */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  return kb < 1024 ? `${kb.toFixed(0)} KB` : `${(kb / 1024).toFixed(1)} MB`
}
