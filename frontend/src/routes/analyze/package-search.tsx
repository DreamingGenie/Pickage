import { SearchIcon } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'

import { searchPackages } from '@/routes/analyze/sample-registry'
import { cn } from '@/lib/utils'

/**
 * 패키지명 검색창.
 *
 * 레지스트리에서 이름이 같거나 가까운 것을 찾아 아래에 편다.
 * 이건 **검색**이지 추천이 아니다. 어느 쪽이 낫다는 정렬을 하지 않는다.
 *
 * 어떤 규칙으로 걸렸는지는 적지 않는다. 여기서 관련성을 따지는 게 아니라
 * 이름을 고르기만 하면 되기 때문이다. 관련성 근거는 후보 카드에서 다룬다.
 *
 * 목록에 없는 이름도 그대로 확인할 수 있다. 레지스트리 사본이 최신이 아닐 수 있어서,
 * 검색 결과가 없다고 입력을 막지 않는다.
 */
export function PackageSearch({
  value,
  onChange,
  onSubmit,
  placeholder = '패키지명 하나 (예: winston)',
  ariaLabel,
  disabled = false,
  autoFocus = false,
  className,
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
}) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  const hits = useMemo(() => searchPackages(value), [value])

  /**
   * 강조된 항목. 질의가 바뀌면 0 으로 돌아가야 하는데, effect 로 되돌리면
   * 한 프레임 어긋난다. 어느 질의에 대한 선택인지 함께 들고 렌더에서 파생시킨다.
   */
  const [mark, setMark] = useState({ q: '', i: 0 })
  const active = mark.q === value ? Math.min(mark.i, Math.max(hits.length - 1, 0)) : 0
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
    if (!open || hits.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((active + 1) % hits.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((active - 1 + hits.length) % hits.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      choose(hits[active].entry.name)
    }
  }

  const showList = open && value.trim().length > 0

  return (
    <div ref={boxRef} className={cn('relative flex-1', className)}>
      <SearchIcon
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
      />
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
        aria-activedescendant={showList && hits.length ? `${listId}-${active}` : undefined}
        className="h-11 w-full rounded-lg border border-input bg-background pr-3 pl-10 font-mono text-[15px] transition-shadow outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-50"
      />

      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="검색 결과"
          className="absolute top-full right-0 left-0 z-30 mt-1.5 max-h-[320px] overflow-y-auto rounded-xl border bg-background p-1 shadow-lg"
        >
          {hits.length === 0 ? (
            <li className="px-3 py-4 text-[12.5px] text-muted-foreground">
              레지스트리 사본에서 <span className="font-mono">{value.trim()}</span> 을(를) 찾지
              못했습니다. 그대로 확인해 볼 수 있습니다.
            </li>
          ) : (
            hits.map((h, i) => (
              <li
                key={h.entry.name}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
              >
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(h.entry.name)}
                  className={cn(
                    'flex w-full flex-col gap-0.5 rounded-lg px-3 py-2 text-left transition-colors',
                    i === active && 'bg-muted',
                  )}
                >
                  <span className="font-mono text-[13.5px]">
                    <Highlight name={h.entry.name} hit={h.hit} />
                  </span>
                  <span className="truncate text-[11.5px] text-muted-foreground">
                    {h.entry.description}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}

function Highlight({ name, hit }: { name: string; hit?: [number, number] }) {
  if (!hit) return <>{name}</>
  return (
    <>
      {name.slice(0, hit[0])}
      <mark className="bg-transparent font-semibold underline underline-offset-2">
        {name.slice(hit[0], hit[1])}
      </mark>
      {name.slice(hit[1])}
    </>
  )
}
