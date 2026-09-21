/**
 * ⚠ 임시 — BE Jackson 직렬화 버그가 고쳐지면 이 파일과 `endpoints.ts` 의 호출 한 줄을 지운다.
 *
 * 서버가 RAG 결과를 `{"node_type":"OBJECT",...}` 로 망가뜨려 보내는 동안(Jackson 2 트리를
 * Jackson 3 이 일반 객체로 직렬화), **정상 응답이 왔다면 화면이 어떻게 보일지** 확인하려고
 * 둔 자리다. 소비 조건 표·run 상태·폴링은 전부 실서버 값이고, `result` 하나만 여기서 채운다.
 *
 * **개발 서버에서만 켜진다**(`import.meta.env.DEV`). 빌드된 배포본에는 들어가도 동작하지 않는다.
 *
 * 값은 화면 상태를 골고루 보려고 만든 것이지 분석 결과가 아니다 — 지원·조건부·제한적·
 * 미확인·미지원 판정, 근거 없는 일반 지식 셀, 문헌이 짧은 패키지를 한 번씩 넣었다.
 */
import type { FeatureRunResponse, FeatureVerdict, RagComparisonResult } from '@/api/types'

/** 망가진 응답인지. 정상이면 `packages` 가 있다. */
function isBroken(result: unknown): boolean {
  return typeof result === 'object' && result !== null && !('packages' in result)
}

const ROWS: { label: string; verdicts: FeatureVerdict[]; generalAt?: number }[] = [
  { label: '경로 매개변수 라우팅', verdicts: ['SUPPORTED', 'SUPPORTED'] },
  { label: '미들웨어 체인', verdicts: ['SUPPORTED', 'CONDITIONALLY_SUPPORTED'] },
  { label: '비동기 핸들러 오류 처리', verdicts: ['LIMITED_SUPPORT', 'SUPPORTED'] },
  { label: '스트리밍 응답', verdicts: ['SUPPORTED', 'UNCONFIRMED'], generalAt: 1 },
  { label: '템플릿 렌더링', verdicts: ['SUPPORTED', 'UNSUPPORTED'] },
]

function previewResult(refs: readonly string[]): RagComparisonResult {
  const packages = refs.map((ref) => {
    const at = ref.lastIndexOf('@')
    return { package: ref.slice(0, at), version: ref.slice(at + 1) }
  })

  return {
    dataStatus: 'COMPLETE',
    packages,
    features: ROWS.map((row, r) => ({
      featureLabel: row.label,
      results: packages.map((p, i) => {
        const verdict = row.verdicts[i % row.verdicts.length]
        const general = row.generalAt === i
        return {
          package: p.package,
          version: p.version,
          verdict,
          evidenceIds: general || verdict === 'UNCONFIRMED' ? [] : [`E${r + 1}${i}`],
          groundedIn: general ? ('GENERAL_KNOWLEDGE' as const) : ('EVIDENCE' as const),
          note: verdict === 'UNCONFIRMED' ? '확인한 자료에서 발견되지 않음' : null,
        }
      }),
    })),
    narrative: [
      {
        heading: '공통으로 확인된 것',
        body: '두 패키지 모두 경로 매개변수 라우팅과 미들웨어 체인을 README 에서 직접 설명한다.',
        evidenceIds: ['E10', 'E11'],
      },
      {
        heading: '구성 방식의 차이',
        body: '비동기 오류 처리와 템플릿 렌더링은 한쪽만 기본으로 제공한다. 나머지는 확인한 자료 범위에서 판단하지 않았다.',
        evidenceIds: ['E30', 'E51'],
      },
    ],
    narrativeError: null,
    sources: packages.map((p, i) => ({
      package: p.package,
      version: p.version,
      // 두 번째 패키지를 짧은 문헌으로 두어 안내 문구를 확인한다
      status: i === 1 ? ('LIMITED' as const) : ('OK' as const),
      readmeBytes: i === 1 ? 900 : 12_000,
      proseChars: i === 1 ? 300 : 5_200,
    })),
  }
}

/** 개발 서버에서 망가진 `result` 를 미리보기 값으로 바꾼다. 그 밖에는 그대로 돌려준다. */
export function patchBrokenRagResult(response: FeatureRunResponse): FeatureRunResponse {
  if (!import.meta.env.DEV) return response
  if (response.status !== 'COMPLETED' || !isBroken(response.result)) return response
  console.warn('[preview-rag] 서버 result 가 망가져 있어 미리보기 값으로 바꿨다 (BE Jackson 버그)')
  return { ...response, result: previewResult(response.refs) }
}
