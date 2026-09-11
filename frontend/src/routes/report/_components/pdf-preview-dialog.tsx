import { DownloadIcon, Loader2Icon } from 'lucide-react'

import { errorNotice } from '@/api/client'
import { pdfDownloadUrl } from '@/api/endpoints'
import { usePdfPreview } from '@/api/queries'
import type { PdfJob } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/**
 * 문서 미리보기 (기능-14).
 *
 * <h2>PDF 를 띄우지 않는다</h2>
 *
 * PDF 를 {@code iframe} 에 넣으면 브라우저의 "PDF 다운로드" 설정에 걸려 저장창이 뜬다.
 * 서버가 {@code inline} 으로 보내도 그 설정이 이긴다. 그래서 서버가 <b>문서 내용을 그린
 * HTML</b> 을 주고, 여기서 그것을 띄운다.
 *
 * <p>보고 있는 것과 받을 것이 다르지 않다 — 다운로드할 PDF 는 <b>이 HTML 을 변환한
 * 결과</b>다(공통-R08).
 *
 * <h2>{@code srcDoc} 인 이유</h2>
 *
 * 문서에는 자기 {@code <style>} 이 들어 있다 — {@code table}, {@code body} 같은 태그
 * 선택자를 쓴다. 본문에 그대로 심으면(`dangerouslySetInnerHTML`) <b>그 CSS 가 앱 전체로
 * 새어나가</b> 다른 화면의 표까지 바뀐다. {@code iframe} 은 문서 경계가 있어 그 일이 없다.
 *
 * <p>안전 쪽으로도 낫다. 문서에는 npm 에서 온 남의 설명 문자열이 들어간다. 서버가
 * 이스케이프하지만, 그 방어가 뚫렸을 때 본문에 심는 방식은 곧바로 앱 안에서 스크립트가
 * 도는 구조가 된다. {@code sandbox} 를 걸어 한 겹 더 막는다.
 *
 * <p>{@code src} 로 주소를 주지 않고 받아 온 문자열을 쓰는 이유는 요청을 한 번만 하기
 * 위해서다 — 주소를 주면 브라우저가 같은 문서를 다시 받는다.
 */
export function PdfPreviewDialog({
  job,
  onOpenChange,
}: {
  /** 열려 있지 않으면 `null`. 보고서가 없으면 미리보기도 없다. */
  job: PdfJob | null
  onOpenChange: (open: boolean) => void
}) {
  const preview = usePdfPreview(job?.report_id ?? null)
  const notice = preview.error ? errorNotice(preview.error) : null

  return (
    <Dialog open={Boolean(job)} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[85vh] flex-col sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>미리보기</DialogTitle>
          <DialogDescription className="font-mono">{job?.file_name}</DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-hidden rounded-lg border bg-white">
          {preview.isPending ? (
            <div className="flex h-full items-center justify-center gap-2 text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" aria-hidden />
              문서를 불러오는 중
            </div>
          ) : notice ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
              <p>{notice.message}</p>
              <p className="text-muted-foreground">
                보고서는 잠깐만 보관됩니다. 창을 닫고 다시 만들어 주세요.
              </p>
            </div>
          ) : (
            <iframe
              /*
                문서 CSS 가 앱으로 새지 않게, 스크립트가 앱 안에서 돌지 않게 가둔다.

                `allow-same-origin` 은 **웹폰트 때문**이다. 이것이 없으면 iframe 이 고유한
                오리진을 갖게 되어 `/fonts/...` 요청이 교차 출처가 되고, 폰트는 CORS 없이는
                받아지지 않아 미리보기만 다른 글꼴로 떨어진다.

                `allow-scripts` 는 주지 않는다. 스크립트가 못 도는 한 같은 오리진이어도
                부모 문서를 건드릴 수 없다 — 둘을 함께 주는 것이 위험한 조합이고,
                여기서는 그럴 이유가 없다.
              */
              sandbox="allow-same-origin"
              srcDoc={preview.data}
              title={`${job?.file_name ?? '보고서'} 미리보기`}
              className="h-full w-full border-0 bg-white"
            />
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            닫기
          </Button>
          {/*
            버튼이 아니라 링크다. 서버가 attachment 로 보내므로 여는 것만으로 저장된다.
            blob 을 만들면 같은 파일을 메모리에 한 번 더 들고 해제까지 챙겨야 한다.

            미리보기를 못 불러왔어도 다운로드는 막지 않는다 — 둘은 다른 요청이고,
            파일은 멀쩡한데 미리보기만 실패했을 수 있다.
          */}
          {job && (
            <Button asChild>
              <a href={pdfDownloadUrl(job.report_id)} download={job.file_name}>
                <DownloadIcon className="size-4" aria-hidden />
                다운로드
              </a>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
