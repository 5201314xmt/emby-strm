import { useState, useEffect, useCallback } from 'react'
import { RefreshCcw, Trash2 } from 'lucide-react'
import api from '@/lib/api'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/Skeleton'
import { toast } from 'sonner'

interface SubItem {
  id?: number
  tmdb_id: number
  season: number
  mp_id?: number
  name: string
  state: string
  auto: boolean
  created_at?: string
}

/**
 * 订阅管理页 —— 查看 / 刷新 / 删除 MoviePilot 订阅
 */
export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<SubItem[]>([])
  const [loading, setLoading] = useState(true)
  const [source, setSource] = useState('local')

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/subscriptions')
      if (res.data.success) {
        setSubs(res.data.data.subscriptions)
        setSource(res.data.data.source)
        if (res.data.data.warning) {
          toast.warning(res.data.data.warning)
        }
      }
    } catch (e) {
      console.error('获取订阅失败:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const handleRefresh = async () => {
    try {
      const res = await api.post('/subscriptions/refresh')
      toast.success(res.data.message)
      fetch()
    } catch (e) {
      toast.error('刷新失败')
    }
  }

  const handleDelete = async (mpId: number) => {
    if (mpId && !confirm('确定删除这个订阅吗？')) return
    try {
      const res = await api.delete(`/subscriptions/${mpId}`)
      toast.success(res.data.message || '已删除')
      fetch()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '删除失败')
    }
  }

  const stateMap: Record<string, string> = {
    R: '等待搜索', S: '搜索中', P: '已完成',
  }

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          数据来源：
          <StatusBadge value={source === 'mp' ? 'running' : 'paused'} variant="scan" />
          <span>{source === 'mp' ? 'MoviePilot 实时' : '本地记录'}</span>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCcw size={12} /> 刷新订阅
        </button>
      </div>

      {/* 列表 */}
      {loading ? (
        <TableSkeleton rows={5} cols={5} />
      ) : subs.length === 0 ? (
        <EmptyState
          title="暂无订阅记录"
          description="从缺集列表订阅缺失的季后，这里会出现记录"
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-card/50">
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">剧名</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">季</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">状态</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">MP ID</th>
                <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">操作</th>
              </tr>
            </thead>
            <tbody>
              {subs.map((sub) => (
                <tr key={sub.id ?? `${sub.tmdb_id}:${sub.season}`} className="border-b border-border hover:bg-accent/30 transition-colors">
                  <td className="px-3 py-2 font-medium">{sub.name || `TMDB:${sub.tmdb_id}`}</td>
                  <td className="px-3 py-2 font-mono text-xs">S{String(sub.season).padStart(2, '0')}</td>
                  <td className="px-3 py-2">
                    <StatusBadge value={sub.state} variant="scan" />
                    <span className="ml-1.5 text-xs text-muted-foreground">
                      {stateMap[sub.state] || sub.state}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {sub.mp_id || '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => {
                        if (!sub.mp_id) { toast.warning('缺少 MP ID，无法删除'); return }
                        handleDelete(sub.mp_id)
                      }}
                      className="rounded p-1 text-muted-foreground hover:text-red-400 transition-colors"
                      title="删除订阅"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
