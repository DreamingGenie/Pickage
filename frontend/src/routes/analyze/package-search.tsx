import { SearchIcon } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { usePackageAutocomplete } from '@/api/autocomplete'
import { cn } from '@/lib/utils'

/** npm 패키지 이름 최대 길이(scope 포함). 이보다 긴 입력은 어차피 존재할 수 없다. */
export const PACKAGE_NAME_MAX = 214

/**
 * 패키지명 검색창.
 *
 * 명세 §2.3 의 두 겹 구조를 그대로 쓴다 — 사전(메모리)에서 먼저 찾고,
 * 결과가 모자랄 때만 서버에 물어 아래에 이어붙인다. 실제 흐름은
 * `api/autocomplete.ts` 에 있고 여기는 그 결과를 그리기만 한다.
 *
 * **접두사 검색만 한다.** 중간 일치("dash"로 lodash 찾기)는 v1 범위 밖이다 —
 * 서버 인덱스(`text_pattern_ops`)와 사전 배포가 둘 다 접두사 전제로 설계돼 있어서,
 * 화면만 중간 일치를 흉내내면 사전에 있는 이름과 없는 이름이 다르게 동작한다.
 *
 * 목록에 없는 이름도 그대로 확인할 수 있다. 사전은 상위 N개뿐이고 서버 폴백도
 * 상한이 있어서, 검색 결과가 없다고 입력을 막지 않는다.
 */
export function PackageSearch({
  value,
  onChange,
  onSubmit,
  placeholder = '패키지 이름 (예: winston)',
  ariaLabel,
  disabled = false,
  autoFocus = false,
  className,
  inputClassName,
  icon = true,
  invalid = false,
  describedBy,
  showCount = false,
}: {
  value: string
  onChange: (v: string) => void
  /** 확정. 목록에서 고르거나 Enter 를 눌렀을 때 */
  onSubmit: (name: string) => void
  placeholder?: string
  ariaLabel: string
  disabled?: boolean
  autoFocus?: boolean
  className?: string
  /** 입력 요소 자체에 얹을 추가 스타일. 크기·모양이 다른 자리(인트로 히어로 등)에 재사용할 때 쓴다. */
  inputClassName?: string
  /** 왼쪽 돋보기 아이콘. 히어로처럼 오른쪽에 별도 제출 버튼을 두는 자리에서는 끈다. */
  icon?: boolean
  /** 호출 측이 들고 있는 오류 상태를 입력에 반영한다(`aria-invalid`). */
  invalid?: boolean
  /** 오류 문구 요소 id. `aria-describedby` 로 연결한다. */
  describedBy?: string
  /** 입력창 아래에 글자 수(`N / 214자`)를 보여 준다. 길이 제한이 있다는 걸 미리 알린다. */
  showCount?: boolean
}) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  const { suggestions, fallbackPending } = usePackageAutocomplete(value)

  /**
   * 강조된 항목. 질의가 바뀌면 0 으로 돌아가야 하는데, effect 로 되돌리면
   * 한 프레임 어긋난다. 어느 질의에 대한 선택인지 함께 들고 렌더에서 파생시킨다.
   */
  const [mark, setMark] = useState({ q: '', i: 0 })
  const active = mark.q === value ? Math.min(mark.i, Math.max(suggestions.length - 1, 0)) : 0
  const setActive = (i: number) => setMark({ q: value, i })

  useEffect(() => {
    function onDocDown(e: MouseEvent) {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocDown)
    return () => document.removeEventListener('mousedown', onDocDown)
  }, [])

  function choose(name: string) {
    onChange(name)
    setOpen(false)
    onSubmit(name)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      setOpen(false)
      return
    }
    if (e.key === 'Enter' && (!open || suggestions.length === 0)) {
      // 목록에 없어도 입력한 이름 그대로 확정할 수 있다.
      const typed = value.trim()
      if (typed) {
        e.preventDefault()
        choose(typed)
      }
      return
    }
    if (!open || suggestions.length === 0) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((active + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((active - 1 + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(suggestions[active].name)
    }
  }

  const query = value.trim()
  const showList = open && query.length > 0

  return (
    <div ref={boxRef} className={cn('relative flex-1', className)}>
      {icon && (
        <SearchIcon
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
      )}
      <input
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        aria-label={ariaLabel}
        disabled={disabled}
        autoFocus={autoFocus}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && suggestions.length ? `${listId}-${active}` : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        maxLength={PACKAGE_NAME_MAX}
        spellCheck={false}
        autoComplete="off"
        className={cn(
          'h-11 w-full rounded-lg border border-input bg-background pr-3 font-mono text-base transition-shadow outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-50',
          icon ? 'pl-10' : 'pl-4',
          inputClassName,
        )}
      />

      {showList && (
        <div className="absolute top-full right-0 left-0 z-30 mt-1.5 overflow-hidden rounded-xl border bg-background shadow-lg">
          <ul
            id={listId}
            role="listbox"
            aria-label="검색 결과"
            className="max-h-[320px] overflow-y-auto p-1"
          >
            {suggestions.length === 0 ? (
              <li className="px-3 py-4 text-base leading-relaxed text-muted-foreground">
                {fallbackPending ? (
                  '찾는 중…'
                ) : (
                  <>
                    <span className="font-mono">{query}</span> 로 시작하는 패키지가 목록에 없어요.
                    Enter 를 누르면 이 이름 그대로 확인해 볼게요.
                  </>
                )}
              </li>
            ) : (
              suggestions.map((s, i) => (
                <li key={s.name} id={`${listId}-${i}`} role="option" aria-selected={i === active}>
                  <button
                    type="button"
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(s.name)}
                    className={cn(
                      'flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left transition-colors',
                      i === active && 'bg-muted',
                    )}
                  >
                    <span className="truncate font-mono text-base">
                      {/* 접두사 검색이라 강조 구간은 항상 앞에서부터 질의 길이만큼이다 */}
                      <mark className="bg-transparent font-semibold underline underline-offset-2">
                        {s.name.slice(0, query.length)}
                      </mark>
                      {s.name.slice(query.length)}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>

          {/*
            사전 결과를 이미 띄운 채로 서버를 기다리는 중.
            목록을 지우고 로딩으로 바꾸면 방금 보이던 후보가 깜빡이며 사라진다.
          */}
          {fallbackPending && suggestions.length > 0 && (
            <p className="border-t px-3 py-1.5 text-base text-muted-foreground" role="status">
              더 찾는 중…
            </p>
          )}
        </div>
      )}
      {showCount && (
        <p className="mt-1.5 text-right text-sm text-muted-foreground tabular-nums">
          {value.length} / {PACKAGE_NAME_MAX}자
        </p>
      )}
    </div>
  )
}
