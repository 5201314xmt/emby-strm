import { useLocation, useNavigate } from 'react-router-dom'
import { Search, Loader2 } from 'lucide-react'
import { useScanStore } from '@/stores/scanStore'
import { useUIStore } from '@/stores/uiStore'

const pageTitles: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/shows': '缺集列表',
  '/subscriptions': '订阅管理',
  '/sources': '扫描源',
  '/settings': '设置',
  '/logs': '日志',
}

/**
 * 顶部状态条 —— 页面标题 + 扫描进度指示 + 全局搜索入口
 */
export function TopBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const dashboard = useScanStore((s) => s.dashboard)
  const { setShowSearch } = useUIStore()

  const activeScan = dashboard?.active_scan
  const title = pageTitles[location.pathname] || '缺集管家'

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-border px-4">
      {/* 左侧：页面标题 */}
      <h1 className="text-sm font-medium text-foreground">{title}</h1>

      {/* 右侧：扫描指示 + 搜索 */}
      <div className="flex items-center gap-3">
        {/* 扫描中指示器 */}
        {activeScan && (
          <div className="flex items-center gap-2 rounded-full bg-blue-500/10 px-3 py-1 text-xs">
            <Loader2 size={12} className="animate-spin text-blue-400" />
            <span className="text-blue-400">
              {activeScan.phase} {Math.round(activeScan.progress)}%
            </span>
            <span className="text-muted-foreground">
              {activeScan.done_shows}/{activeScan.total_shows}
            </span>
          </div>
        )}

        {/* 搜索按钮 → 跳转缺集列表搜索 */}
        <button
          onClick={() => navigate('/shows')}
          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          title="搜索剧集"
        >
          <Search size={16} />
        </button>
      </div>
    </header>
  )
}
