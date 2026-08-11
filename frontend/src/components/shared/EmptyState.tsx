import { AlertTriangle, Search } from 'lucide-react'

interface EmptyStateProps {
  icon?: 'search' | 'alert'
  title: string
  description: string
  action?: React.ReactNode
}

/**
 * 空状态引导页
 *
 * 当列表无数据时显示，引导用户进行下一步操作。
 */
export function EmptyState({ icon = 'search', title, description, action }: EmptyStateProps) {
  const Icon = icon === 'search' ? Search : AlertTriangle

  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 rounded-full bg-accent p-4">
        <Icon size={32} className="text-muted-foreground" />
      </div>
      <h3 className="text-lg font-medium text-foreground">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
