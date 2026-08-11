import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BatchActionBarProps {
  count: number
  onSubscribe: () => void
  onIgnore: () => void
  onClear: () => void
  className?: string
}

/**
 * 批量操作条 —— 勾选了表格行后出现
 */
export function BatchActionBar({ count, onSubscribe, onIgnore, onClear, className }: BatchActionBarProps) {
  if (count === 0) return null

  return (
    <div className={cn(
      'flex items-center gap-3 rounded-lg border border-blue-500/30 bg-blue-500/10 px-4 py-2 text-sm',
      className
    )}>
      <span className="text-blue-400">
        已选 <strong>{count}</strong> 项
      </span>
      <button
        onClick={onSubscribe}
        className="rounded bg-blue-500 px-3 py-1 text-white hover:bg-blue-600 transition-colors"
      >
        批量订阅
      </button>
      <button
        onClick={onIgnore}
        className="rounded border border-border px-3 py-1 text-muted-foreground hover:text-foreground transition-colors"
      >
        批量忽略
      </button>
      <button onClick={onClear} className="ml-auto rounded p-1 text-muted-foreground hover:text-foreground" title="取消选择">
        <X size={14} />
      </button>
    </div>
  )
}
