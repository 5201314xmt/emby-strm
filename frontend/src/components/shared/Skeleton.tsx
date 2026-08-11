import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
}

/**
 * 骨架屏 —— 加载占位，避免空白闪烁
 */
export function Skeleton({ className }: SkeletonProps) {
  return <div className={cn('animate-pulse rounded bg-accent', className)} />
}

/** 表格骨架（N 行 × 自适应列数） */
export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4 rounded border border-border p-3">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} className={cn('h-4', j === 0 ? 'w-8' : 'flex-1')} />
          ))}
        </div>
      ))}
    </div>
  )
}

/** KPI 卡片骨架 */
export function KpiSkeleton() {
  return (
    <div className="grid grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border bg-card p-4">
          <Skeleton className="mb-2 h-4 w-20" />
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </div>
  )
}
