import type { ApiEnvelope, ApiErrorCode, ClientErrorCode } from '@/api/types'

/**
 * HTTP 밑바닥.
 *
 * 이 파일은 **봉투를 벗기는 일까지만** 한다(명세 0.3).
 * 어떤 엔드포인트가 있는지, mock 을 쓸지는 `api/endpoints.ts` 가 정한다.
 */

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const DEFAULT_TIMEOUT_MS = 15_000

export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode | ClientErrorCode | string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }

  /** 0.4 — 400 계열은 전부 클라이언트가 규칙을 어긴 것이다. 재시도해도 같은 결과다. */
  get isValidation(): boolean {
    return this.code.startsWith('V')
  }
}

/**
 * 오류를 화면에 어떻게 말할지 정한다. **판단만 하고 그리지는 않는다.**
 *
 * 오류를 내는 자리가 둘 이상이고(탭 전체 · 지표 카드 안) 생김새가 서로 다른데,
 * "400 이면 재시도를 권하지 않는다" 는 판단은 같다. 그 판단이 두 벌이 되면
 * 한쪽만 고쳐진다.
 */
export function errorNotice(error: unknown): {
  message: string
  /** 서버가 준 코드. 우리가 만든 오류면 없다. */
  code?: string
  retryable: boolean
} {
  const api = error instanceof ApiError ? error : null
  return {
    message: api?.message ?? '자료를 불러오지 못했습니다.',
    code: api?.code,
    // 서버 코드가 아닌 오류(네트워크·타임아웃)는 다시 해 볼 값어치가 있다.
    retryable: !api?.isValidation,
  }
}

/**
 * 쿼리 파라미터 값.
 *
 * 배열은 **쉼표로 이어 붙인다**(0.1). Spring 은 `?names=a,b,c` 와 `?names=a&names=b` 를
 * 둘 다 `List<String>` 으로 받지만, 캐시 키가 URL 이므로 형태를 하나로 고정해야
 * 같은 요청이 같은 캐시 항목에 떨어진다.
 */
type ParamValue = string | number | boolean | readonly string[] | null | undefined
type Params = Record<string, ParamValue> | undefined

function buildUrl(path: string, params: Params): string {
  const url = `${API_BASE_URL}${path}`
  if (!params) return url

  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    if (Array.isArray(value)) {
      if (value.length === 0) continue
      search.append(key, value.join(','))
      continue
    }
    search.append(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${url}?${qs}` : url
}

/**
 * 0.3 — 봉투를 벗긴다.
 *
 * 명세상 실패는 `success: false` 로 오고 상태코드도 함께 바뀌지만, 둘 중 하나만
 * 어긋나는 경우가 실제로 생긴다(프록시가 만든 502, 본문 없는 500 등).
 * 그래서 **상태코드와 본문을 둘 다** 본다.
 */
async function unwrap<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T

  let body: unknown
  try {
    body = await res.json()
  } catch {
    throw new ApiError(
      res.status,
      `HTTP_${res.status}`,
      res.statusText || '응답을 읽지 못했습니다.',
    )
  }

  const envelope = body as Partial<ApiEnvelope<T>> & { code?: string; message?: string }

  if (envelope?.success === true) return (envelope as { data: T }).data
  if (envelope?.success === false) {
    throw new ApiError(
      res.status,
      envelope.code ?? 'S001',
      envelope.message ?? '오류가 발생했습니다.',
    )
  }

  // 봉투가 아닌 응답. 게이트웨이·프록시가 끼어든 경우다.
  throw new ApiError(
    res.status,
    `HTTP_${res.status}`,
    res.ok ? '서버 응답 형식이 올바르지 않습니다.' : res.statusText,
  )
}

async function request<T>(
  method: 'GET' | 'POST',
  path: string,
  { params, body }: { params?: Params; body?: unknown } = {},
): Promise<T> {
  let res: Response
  try {
    res = await fetch(buildUrl(path, params), {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
    })
  } catch (e) {
    const aborted = e instanceof DOMException && e.name === 'TimeoutError'
    throw new ApiError(
      0,
      aborted ? 'TIMEOUT' : 'NETWORK',
      aborted ? '요청 시간이 초과되었습니다.' : '서버에 연결하지 못했습니다.',
    )
  }

  return unwrap<T>(res)
}

/** 봉투를 벗겨 `data` 를 돌려준다. */
export function get<T>(path: string, params?: Params): Promise<T> {
  return request<T>('GET', path, { params })
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, { body })
}

/**
 * 봉투 없이 본문을 그대로 받는다(보고서 미리보기 HTML).
 *
 * <p>`get()` 은 JSON 을 파싱해 `data` 를 꺼내므로 HTML 에는 쓸 수 없다. 경로 규칙은
 * 같아야 하니 `API_BASE_URL` 은 그대로 붙인다 — 그래야 dev 프록시를 탄다.
 *
 * <p>실패는 봉투가 아니라 상태 코드로만 온다. 404 는 "그 보고서가 사라졌다" 는 뜻이고,
 * 보관이 메모리라 재시작·기한 만료로 실제로 일어난다.
 */
export async function getText(path: string): Promise<string> {
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) })
  } catch {
    throw new ApiError(0, 'NETWORK', '서버에 연결하지 못했습니다.')
  }
  if (!res.ok) {
    throw new ApiError(
      res.status,
      `HTTP_${res.status}`,
      res.status === 404
        ? '보고서가 만료되었습니다. 다시 만들어 주세요.'
        : '미리보기를 불러오지 못했습니다.',
    )
  }
  return res.text()
}

/**
 * 봉투를 쓰지 않는 정적 파일용(사전 파일 본문 등).
 * `API_BASE_URL` 을 붙이지 않고 경로를 그대로 쓴다.
 */
export async function getRaw<T>(url: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(url, { signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) })
  } catch {
    throw new ApiError(0, 'NETWORK', '파일을 내려받지 못했습니다.')
  }
  if (!res.ok) throw new ApiError(res.status, `HTTP_${res.status}`, res.statusText)
  return (await res.json()) as T
}
