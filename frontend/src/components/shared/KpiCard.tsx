import { cn } from '@/lib/utils'

interface KpiCardProps {
  label: string
  value: number | string
  icon: React.ReactNode
  onClick?: () => void
  className?: string
}

/**
 * 仪表盘统计卡片
 *
 * 展示一个关键指标数值，可点击跳转。
 */
export function KpiCard({ label, value, icon, onClick, className }: KpiCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card p-4 transition-colors',
        onClick && 'cursor-pointer hover:border-primary/30 hover:bg-accent/50',
        className
      )}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="text-muted-foreground/50">{icon}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold text-foreground">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
    </div>
  )
}
