import { XIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

export function PackageChip({
  name,
  range,
  onRemove,
  className,
}: {
  name: string
  range?: string | null
  onRemove?: () => void
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border bg-background px-2 py-1 text-xs',
        className,
      )}
    >
      <span className="font-medium">{name}</span>
      {range && <span className="font-mono text-muted-foreground">{range}</span>}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`${name} 제거`}
          className="-mr-0.5 rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
        >
          <XIcon className="size-3" />
        </button>
      )}
    </span>
  )
}
