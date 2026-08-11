import { cn, STATUS_MAP, SCAN_STATUS_MAP } from '@/lib/utils'

type BadgeVariant = 'status' | 'scan' | 'log' | 'quality'

interface StatusBadgeProps {
  value: string
  variant?: BadgeVariant
  className?: string
}

const variantMaps: Record<BadgeVariant, Record<string, { label: string; color: string }>> = {
  status: STATUS_MAP,
  scan: SCAN_STATUS_MAP,
  log: {
    INFO:    { label: '信息',  color: 'border-blue-500/30 text-blue-400 bg-blue-500/10' },
    SUCCESS: { label: '成功',  color: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' },
    WARN:    { label: '警告',  color: 'border-amber-500/30 text-amber-400 bg-amber-500/10' },
    ERROR:   { label: '错误',  color: 'border-red-500/30 text-red-400 bg-red-500/10' },
  },
  quality: {
    normal:   { label: '正常',  color: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10' },
    degraded: { label: '降级',  color: 'border-amber-500/30 text-amber-400 bg-amber-500/10' },
  },
}

/**
 * 统一状态标签组件
 *
 * 用法：
 *   <StatusBadge value="partial" variant="status" />
 *   <StatusBadge value="running" variant="scan" />
 *   <StatusBadge value="ERROR" variant="log" />
 */
export function StatusBadge({ value, variant = 'status', className }: StatusBadgeProps) {
  const map = variantMaps[variant]
  const item = map[value]

  if (!item) {
    // 未知状态 → 显示原始值
    return (
      <span className={cn('inline-flex items-center rounded border px-1.5 py-0.5 text-xs',
        'border-zinc-500/30 text-zinc-400 bg-zinc-500/10', className)}>
        {value}
      </span>
    )
  }

  return (
    <span className={cn(
      'inline-flex items-center rounded border px-1.5 py-0.5 text-xs',
      item.color, className
    )}>
      {item.label}
    </span>
  )
}
