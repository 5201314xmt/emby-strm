import { useEffect, useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Tv, AlertTriangle, FolderOpen, Rss, RefreshCcw, Play, SearchX, BarChart3, ChevronRight,
} from 'lucide-react'
import { useScanStore } from '@/stores/scanStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { KpiCard } from '@/components/shared/KpiCard'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { KpiSkeleton } from '@/components/shared/Skeleton'
import { formatDuration } from '@/lib/utils'
import { toast } from 'sonner'
import api from '@/lib/api'

/**
 * 仪表盘页 —— 首页概览 + 快捷操作
 */
export default function DashboardPage() {
  const dashboard = useScanStore((s) => s.dashboard)
  const loading = useScanStore((s) => s.loading)
  const fetchDashboard = useScanStore((s) => s.fetchDashboard)
  const updateScanProgress = useScanStore((s) => s.updateScanProgress)
  const navigate = useNavigate()

  // 扫描速度计算
  const [scanStartDone, setScanStartDone] = useState(0)
  const startTimeRef = useRef(0)

  useEffect(() => { fetchDashboard() }, [])

  useWebSocket('scan.progress', (data) => {
    updateScanProgress(data)
    const done = data.done || data.done_shows || 0
    if (done > 0 && startTimeRef.current === 0) {
      startTimeRef.current = Date.now()
    }
    setScanStartDone(done)
  })
  useWebSocket('scan.completed', () => {
    fetchDashboard(); toast.success('扫描完成！')
    startTimeRef.current = 0; setScanStartDone(0)
  })
  useWebSocket('scan.failed', (data) => {
    fetchDashboard(); toast.error(`扫描失败：${data?.error || '未知错误'}`)
    startTimeRef.current = 0; setScanStartDone(0)
  })
  useWebSocket('dashboard.refresh', () => { fetchDashboard() })

  const handleStartScan = async () => {
    try {
      const res = await api.post('/scan/start')
      if (res.data.success) {
        toast.success('扫描已开始')
        startTimeRef.current = 0; setScanStartDone(0)
        setTimeout(() => fetchDashboard(), 1000)
      } else {
        toast.error(res.data.message || '启动失败')
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '启动扫描失败')
    }
  }

  if (loading || !dashboard) {
    return <div className="space-y-6"><KpiSkeleton /></div>
  }

  const { kpi, active_scan, recent_scans } = dashboard
  const allZero = kpi.show_count === 0 && kpi.missing_count === 0
  const elapsed = startTimeRef.current ? (Date.now() - startTimeRef.current) / 1000 : 0
  const scanSpeed = elapsed > 0 && scanStartDone > 0
    ? Math.round(scanStartDone / elapsed * 60) : 0

  return (
    <div className="space-y-6">
      {/* ========== KPI 卡片 ========== */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="剧集数" value={kpi.show_count} icon={<Tv size={16} />} onClick={() => navigate('/shows')} />
        <KpiCard label="缺集总数" value={kpi.missing_count} icon={<AlertTriangle size={16} />} onClick={() => navigate('/shows?status=partial')} />
        <KpiCard label="整季缺失" value={kpi.full_missing_count} icon={<SearchX size={16} />} onClick={() => navigate('/shows?status=full_missing')} />
        <KpiCard label="已订阅" value={kpi.subscribed_count} icon={<Rss size={16} />} onClick={() => navigate('/subscriptions')} />
        <KpiCard label="部分缺失" value={kpi.partial_count} icon={<BarChart3 size={16} />} onClick={() => navigate('/shows?status=partial')} />
        <KpiCard label="未识别" value={kpi.unrecognized_count} icon={<FolderOpen size={16} />} onClick={() => navigate('/sources')} />
      </div>

      {/* KPI 空状态引导 */}
      {allZero && !active_scan && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-6 text-center">
          <p className="text-sm text-muted-foreground">还没有扫描过 STRM 文件</p>
          <button onClick={handleStartScan} className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
            <Play size={14} /> 开始扫描
          </button>
          <p className="mt-2 text-xs text-muted-foreground">或先在「扫描源」页添加 STRM 目录</p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium">{active_scan ? '扫描进度' : '最近扫描'}</h2>
              <button onClick={handleStartScan} disabled={!!active_scan}
                className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
                <Play size={12} />{active_scan ? '扫描中...' : '开始扫描'}
              </button>
            </div>
            {active_scan ? (
              <div className="mt-4 space-y-3">
                <div className="flex items-center gap-3 text-sm">
                  <StatusBadge value={active_scan.status} variant="scan" />
                  <span className="text-muted-foreground">{active_scan.phase}</span>
                  <span className="ml-auto font-mono text-xs text-muted-foreground">
                    {active_scan.done_shows}/{active_scan.total_shows}
                    {scanSpeed > 0 && <span className="ml-2 text-primary">{scanSpeed} 部/分</span>}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-accent">
                  <div className="h-full rounded-full bg-primary transition-all duration-500"
                    style={{ width: `${Math.min(100, active_scan.progress)}%` }} />
                </div>
                {active_scan.current_item && (
                  <p className="text-xs text-muted-foreground truncate">当前：{active_scan.current_item}</p>
                )}
                {active_scan.eta_seconds > 0 && (
                  <p className="text-xs text-muted-foreground">预计剩余：{formatDuration(active_scan.eta_seconds)}</p>
                )}
              </div>
            ) : (
              <p className="mt-4 text-sm text-muted-foreground">无正在运行的扫描任务</p>
            )}
          </div>

          {recent_scans.length > 0 && (
            <div className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-medium">扫描历史</h2>
                <button onClick={() => navigate('/shows')} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary">
                  查看详情 <ChevronRight size={12} />
                </button>
              </div>
              <div className="space-y-2">
                {recent_scans.map((scan) => (
                  <div key={scan.id} className="flex items-center gap-3 rounded border border-border p-2 text-xs">
                    <StatusBadge value={scan.status} variant="scan" />
                    <span className="text-muted-foreground">{scan.source_names.join(', ') || '全部源'}</span>
                    <span className="text-muted-foreground">{scan.show_count} 部剧</span>
                    {scan.duration_seconds && <span className="text-muted-foreground">{formatDuration(scan.duration_seconds)}</span>}
                    <span className="ml-auto text-muted-foreground">{scan.started_at}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <h2 className="mb-3 text-sm font-medium">快捷操作</h2>
          <div className="space-y-2">
            <button onClick={handleStartScan} disabled={!!active_scan}
              className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50 transition-colors">
              <Play size={14} /> 开始扫描
            </button>
            <button onClick={async () => {
              try { const res = await api.post('/subscriptions/refresh'); toast.success(res.data.message || '已刷新'); fetchDashboard() }
              catch { toast.error('刷新失败') }
            }} className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
              <RefreshCcw size={14} /> 刷新订阅状态
            </button>
            <button onClick={async () => {
              try { await api.post('/cache/clear'); toast.success('已清空 TMDB 缓存') }
              catch { toast.error('清空失败') }
            }} className="flex w-full items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
              <RefreshCcw size={14} /> 清空 TMDB 缓存
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
