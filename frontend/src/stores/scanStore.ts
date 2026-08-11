import { create } from 'zustand'
import api from '@/lib/api'

export interface DashboardData {
  kpi: {
    show_count: number
    missing_count: number
    full_missing_count: number
    subscribed_count: number
    partial_count: number
    unrecognized_count: number
  }
  active_scan: {
    job_id: number
    status: string
    phase: string
    progress: number
    done_shows: number
    total_shows: number
    current_item: string
    eta_seconds: number
  } | null
  recent_scans: Array<{
    id: number
    status: string
    source_names: string[]
    started_at: string | null
    duration_seconds: number | null
    show_count: number
    missing_count: number
  }>
}

interface ScanState {
  dashboard: DashboardData | null
  loading: boolean
  fetchDashboard: () => Promise<void>
  updateScanProgress: (data: any) => void
}

// 节流：最多每 200ms 更新一次 store（约 5 FPS），避免高频更新导致 UI 抖动
let _pendingUpdate: any = null
let _rafId: number | null = null

function _flushUpdate(set: any, get: any) {
  if (!_pendingUpdate) return
  const data = _pendingUpdate
  _pendingUpdate = null
  _rafId = null

  const current = get().dashboard
  if (!current) return

  const newActive = {
    job_id: data.job_id,
    status: data.status || 'running',
    phase: data.phase || '',
    progress: data.progress || 0,
    done_shows: data.done || data.done_shows || 0,
    total_shows: data.total || data.total_shows || 0,
    current_item: data.current || data.current_item || '',
    eta_seconds: data.eta_seconds || 0,
  }

  // 只在数据真正变化时才更新（防止相同值的重复渲染）
  const prev = current.active_scan
  if (prev &&
    prev.job_id === newActive.job_id &&
    prev.status === newActive.status &&
    prev.phase === newActive.phase &&
    prev.progress === newActive.progress &&
    prev.done_shows === newActive.done_shows &&
    prev.total_shows === newActive.total_shows &&
    prev.current_item === newActive.current_item &&
    prev.eta_seconds === newActive.eta_seconds) {
    return
  }

  set({
    dashboard: {
      ...current,
      active_scan: newActive,
    },
  })
}

export const useScanStore = create<ScanState>((set, get) => ({
  dashboard: null,
  loading: false,

  fetchDashboard: async () => {
    set({ loading: true })
    try {
      const res = await api.get('/dashboard')
      if (res.data.success) {
        set({ dashboard: res.data.data, loading: false })
        return
      }
    } catch (e) {
      console.error('获取仪表盘失败:', e)
    }
    set({ loading: false })
  },

  updateScanProgress: (data: any) => {
    if (!get().dashboard) return
    _pendingUpdate = data
    if (_rafId === null) {
      _rafId = requestAnimationFrame(() => _flushUpdate(set, get))
    }
  },
}))
