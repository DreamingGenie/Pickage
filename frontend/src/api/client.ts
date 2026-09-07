export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const DEFAULT_TIMEOUT_MS = 15_000

export interface ApiErrorBody {
  code: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

type Params = Record<string, unknown> | undefined

function buildUrl(path: string, params: Params): string {
  const url = `${API_BASE_URL}${path}`
  if (!params) return url

  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue
    search.append(key, String(value))
  }
  const qs = search.toString()
  return qs ? `${url}?${qs}` : url
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> = {}
  try {
    body = (await res.json()) as Partial<ApiErrorBody>
  } catch {
    // 본문이 비었거나 JSON 이 아닌 경우 — 상태코드로만 판단한다.
  }
  return new ApiError(res.status, body.code ?? `HTTP_${res.status}`, body.message ?? res.statusText)
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

  if (!res.ok) throw await toApiError(res)
  if (res.status === 204) return undefined as T

  return (await res.json()) as T
}

export function get<T>(path: string, params?: Params): Promise<T> {
  return request<T>('GET', path, { params })
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, { body })
}
