import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, Film, Rss, FolderOpen, Wrench, ScrollText,
  ChevronLeft, ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUIStore } from '@/stores/uiStore'
import { TopBar } from './TopBar'

const navItems = [
  { to: '/dashboard',     icon: LayoutDashboard, label: '仪表盘' },
  { to: '/shows',         icon: Film,            label: '缺集列表' },
  { to: '/subscriptions', icon: Rss,             label: '订阅管理' },
  { to: '/sources',       icon: FolderOpen,      label: '扫描源' },
  { to: '/settings',      icon: Wrench,          label: '设置' },
  { to: '/logs',          icon: ScrollText,      label: '日志' },
]

/**
 * 应用布局外壳 —— 左侧导航 + 顶部状态条 + 内容区
 * 参考 MoviePilot 风格：深色底、低对比边框、紧凑布局。
 */
export function AppShell() {
  const { sidebarCollapsed, toggleSidebar } = useUIStore()

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ========== 左侧导航 ========== */}
      <aside
        className={cn(
          'flex flex-col border-r border-border bg-card transition-all duration-200',
          sidebarCollapsed ? 'w-16' : 'w-60'
        )}
      >
        {/* 标题区 */}
        <div className="flex h-12 items-center justify-between border-b border-border px-4">
          {!sidebarCollapsed && (
            <span className="text-sm font-semibold text-foreground">缺集管家</span>
          )}
          <button
            onClick={toggleSidebar}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* 导航列表 */}
        <nav className="flex-1 space-y-1 p-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )
              }
              title={sidebarCollapsed ? item.label : undefined}
            >
              <item.icon size={18} />
              {!sidebarCollapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* 底部版本 */}
        {!sidebarCollapsed && (
          <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
            v2.0.0
          </div>
        )}
      </aside>

      {/* ========== 右侧主区域 ========== */}
      <div className="flex flex-1 flex-col min-w-0">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
