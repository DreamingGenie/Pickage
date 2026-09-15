import { ArrowLeftIcon, FileDownIcon } from 'lucide-react'
import { Suspense, lazy, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { MAX_NAMES, type PdfJob } from '@/api/types'
import { REPORT_NAMES_PARAM, paths } from '@/app/routes'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EvidenceDrawer } from '@/routes/report/_components/evidence-drawer'
import { PdfExportDialog } from '@/routes/report/_components/pdf-export-dialog'
import { PdfPreviewDialog } from '@/routes/report/_components/pdf-preview-dialog'
import { useAnalysisRun } from '@/routes/report/_components/use-analysis-run'

/**
 * 탭은 한 번에 하나만 마운트되므로(Radix 기본 동작) 탭 단위로 한 번 더 쪼갠다.
 * 03B 는 나중에 마크다운 렌더러(RAG 결과)를 물게 되므로 특히 분리 이득이 크다.
 */
const EcosystemReportTab = lazy(() =>
  import('@/routes/report/ecosystem/ecosystem-report-tab').then((m) => ({
    default: m.EcosystemReportTab,
  })),
)
const FeatureCompareTab = lazy(() =>
  import('@/routes/report/features/feature-compare-tab').then((m) => ({
    default: m.FeatureCompareTab,
  })),
)

const prefetch = {
  ecosystem: () => import('@/routes/report/ecosystem/ecosystem-report-tab'),
  features: () => import('@/routes/report/features/feature-compare-tab'),
} as const

export type ReportTab = 'ecosystem' | 'features'

/** 주소에서 읽어낸 비교 대상. */
interface ReportNames {
  /** 실제로 조회할 이름. 중복을 지우고 상한까지만 남긴다. */
  names: string[]
  /**
   * 상한을 넘겨 빠진 이름.
   *
   * **버리되 밝힌다.** 조용히 자르면 주소에 네 개가 적혀 있는데 화면에는 세 개만 뜨고,
   * 어느 것이 빠졌는지 알 방법이 없다. 이 화면이 없애려는 실패가 바로 그것이다.
   */
  dropped: string[]
}

/**
 * 주소에서 비교 대상을 읽는다 (`?names=a,b,c`).
 *
 * **없으면 기본 조합으로 대체하지 않는다.** 예전에는 라우터 state 가 없을 때 조용히
 * winston·pino·bunyan 으로 떨어졌다. 공유받은 링크에서 그 일이 일어나면 받는 사람은
 * 보낸 사람과 다른 보고서를 보면서도 화면에 아무 표시가 없다 — 비어 있는 것보다
 * 틀린 것을 맞다고 보여주는 쪽이 나쁘다.
 *
 * 서버가 어차피 같은 규칙으로 검증하므로(0.1) 여기서는 형식까지 보지 않는다.
 * 보내기 전에 줄이는 것만 한다 — 중복 제거와 상한이다. 상한을 넘겨 보내면 V002 로
 * 거절당해 네 요청이 전부 빈다.
 *
 * <h2>두 값을 한 {@code useMemo} 안에서 만든다</h2>
 *
 * 밖에서 잘라내면 렌더마다 새 배열이 나오고, 그 배열이 {@code EcosystemReportTab} 의
 * 질의 키에 그대로 들어가 **끝나지 않는 재조회**가 된다. 같은 memo 결과 안에 두면
 * 호출부에서 구조분해해도 두 배열의 참조가 그대로다.
 */
function useReportNames(raw: string | null): ReportNames {
  return useMemo(() => {
    if (!raw) return { names: [], dropped: [] }
    const cleaned = [
      ...new Set(
        raw
          .split(',')
          .map((name) => name.trim())
          .filter(Boolean),
      ),
    ]
    return { names: cleaned.slice(0, MAX_NAMES), dropped: cleaned.slice(MAX_NAMES) }
  }, [raw])
}

/**
 * 03A / 03B 를 담는 셸.
 *
 * 탭 상태는 로컬 state 로 둔다. 단 `?evidence=` 가 있으면 features 로 강제한다.
 *
 * 생태계 변화는 사전 집계라 즉시 뜨고, 기능 비교만 분석을 기다린다.
 * 그래서 보고서 전체를 막지 않고 03B 탭 안에서만 대기 화면을 보여준다.
 */
export function ReportPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  /**
   * 비교 대상은 주소가 들고 있다. 새로고침·뒤로가기·공유 링크가 전부 같은 보고서를 연다.
   */
  const { names: packages, dropped } = useReportNames(searchParams.get(REPORT_NAMES_PARAM))
  const evidenceId = searchParams.get('evidence')

  /**
   * 탭은 로컬 state 다. 단 `?evidence=` 가 있으면 기능 비교로 강제한다.
   * 동기화 effect 대신 렌더에서 파생시킨다 — 상태가 두 곳에 갈라지지 않는다.
   */
  const [picked, setTab] = useState<ReportTab>('ecosystem')
  const tab: ReportTab = evidenceId ? 'features' : picked
  const run = useAnalysisRun()

  /**
   * PDF 내보내기. 두 모달이 이어진다 — 내보내기(생성)가 닫히고 미리보기가 열린다.
   *
   * 만들어진 보고서를 여기서 들고 있는 이유는, 미리보기를 닫았다가 다시 열 때
   * **문서를 다시 만들지 않기 위해서**다(요구사항 §13.2 · 기능-16-R08).
   */
  const [exporting, setExporting] = useState(false)
  const [preview, setPreview] = useState<PdfJob | null>(null)

  function closeEvidence() {
    const next = new URLSearchParams(searchParams)
    next.delete('evidence')
    setSearchParams(next, { replace: true })
  }

  function openEvidence(id: string) {
    const next = new URLSearchParams(searchParams)
    next.set('evidence', id)
    setSearchParams(next)
    // 드로어를 닫아도 기능 비교 탭에 남아 있도록 선택도 함께 옮긴다.
    setTab('features')
  }

  /*
    주소에 비교 대상이 없다. 링크가 잘렸거나 `/report/draft` 를 손으로 친 경우다.
    무엇을 보여줄지 정할 근거가 없으므로 지어내지 않고 되돌려 보낸다.
  */
  if (packages.length === 0) {
    return (
      <div className="flex flex-col gap-7">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">분석 결과</h1>
        </header>
        <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed p-6">
          <p className="text-sm">주소에 비교 대상이 없습니다.</p>
          <p className="text-base text-muted-foreground">
            보고서 주소는 <span className="font-mono">?{REPORT_NAMES_PARAM}=</span> 에 비교 대상을
            담습니다. 링크가 잘렸거나 주소를 직접 입력했을 수 있습니다.
          </p>
          <Button size="sm" onClick={() => navigate(paths.analyze)}>
            분석 시작하기
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-wrap items-start justify-between gap-4">
        {/* 비교 패키지는 각 탭의 카드·범례에 이미 나오므로 제목 아래에 또 적지 않는다 */}
        <h1 className="text-2xl font-semibold tracking-tight">분석 결과</h1>

        {/* 되돌아가기. 확정한 선택을 그대로 들고 가서 2단계부터 다시 연다 */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(paths.analyze, { state: { restore: packages } })}
          >
            <ArrowLeftIcon className="size-3.5" aria-hidden />
            비교 대상 바꾸기
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate(paths.analyze)}>
            새 분석
          </Button>
          {/* 기능-05-R03 — 상단 우측. 보고서 어느 탭에 있든 같은 자리에 있어야 한다 */}
          <Button size="sm" onClick={() => setExporting(true)}>
            <FileDownIcon className="size-3.5" aria-hidden />
            PDF 내보내기
          </Button>
        </div>
      </header>

      {/*
        주소에 상한을 넘는 이름이 있었다. 탭과 무관한 "주소" 이야기라 페이지 위에 둔다 —
        생태계 탭 안의 "찾지 못한 패키지"(서버가 이름을 못 찾음)와는 다른 사실이고,
        둘이 함께 뜰 수도 있다.
      */}
      {dropped.length > 0 && (
        <p className="rounded-lg border border-dashed px-3 py-2 text-base text-muted-foreground">
          한 번에 {MAX_NAMES}개까지 비교합니다. 주소에 더 있어서{' '}
          <span className="font-mono text-foreground">{dropped.join(', ')}</span> 는 제외했습니다.
        </p>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as ReportTab)}>
        <TabsList>
          <TabsTrigger value="ecosystem" onMouseEnter={prefetch.ecosystem}>
            생태계 변화
          </TabsTrigger>
          <TabsTrigger value="features" onMouseEnter={prefetch.features}>
            기능 비교
            {run.status !== 'COMPLETED' && (
              <>
                <span
                  aria-hidden
                  className="ml-1 inline-block size-1.5 animate-pulse rounded-full bg-foreground/60"
                />
                <span className="sr-only">분석 중</span>
              </>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="ecosystem" className="pt-7">
          <Suspense fallback={<TabFallback />}>
            <EcosystemReportTab packages={packages} />
          </Suspense>
        </TabsContent>
        <TabsContent value="features" className="pt-7">
          <Suspense fallback={<TabFallback />}>
            <FeatureCompareTab packages={packages} run={run} onOpenEvidence={openEvidence} />
          </Suspense>
        </TabsContent>
      </Tabs>

      <EvidenceDrawer evidenceId={evidenceId} onClose={closeEvidence} />

      <PdfExportDialog
        open={exporting}
        onOpenChange={setExporting}
        packages={packages}
        run={run}
        onGoToFeatures={() => setTab('features')}
        onPreview={(job) => {
          // 생성 모달을 닫고 미리보기로 넘긴다. 둘이 겹쳐 뜨면 어느 쪽을 닫는 것인지
          // 알 수 없고, 뒤 모달의 포커스 덫에 갇힌다.
          setExporting(false)
          setPreview(job)
        }}
      />
      <PdfPreviewDialog job={preview} onOpenChange={(open) => !open && setPreview(null)} />
    </div>
  )
}

/** 탭 청크를 받는 동안. 화면 구조를 미리 잡아 레이아웃이 튀지 않게 한다. */
function TabFallback() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton className="h-11 w-full max-w-sm" />
      <Skeleton className="h-56 w-full" />
    </div>
  )
}
