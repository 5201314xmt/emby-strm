import { useState, useEffect, useCallback } from 'react'
import { Trash2, Copy, Search } from 'lucide-react'
import api from '@/lib/api'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/Skeleton'
import { LOG_LEVEL_COLORS, formatTime } from '@/lib/utils'
import { toast } from 'sonner'

interface LogItem {
  id: number
  timestamp: string
  level: string
  category: string
  source?: string
  message: string
}

/**
 * 日志页 —— 运维风格，筛选级别/分类，可复制
 */
export default function LogsPage() {
  const [logs, setLogs] = useState<LogItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [level, setLevel] = useState('')
  const [category, setCategory] = useState('')
  const [search, setSearch] = useState('')
  const limit = 200

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { limit }
      if (level) params.level = level
      if (category) params.category = category
      if (search) params.search = search
      const res = await api.get('/logs', { params })
      if (res.data.success) {
        setLogs(res.data.data.items)
        setTotal(res.data.data.total)
      }
    } catch (e) {
      console.error('获取日志失败:', e)
    }
    setLoading(false)
  }, [level, category, search])

  useEffect(() => { fetch() }, [fetch])

  const handleClear = async () => {
    if (!confirm('确定清空所有日志吗？')) return
    try {
      await api.delete('/logs')
      toast.success('日志已清空')
      fetch()
    } catch (e) {
      toast.error('清空失败')
    }
  }

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('已复制')
  }

  const levels = ['', 'INFO', 'SUCCESS', 'WARN', 'ERROR']
  const categories = ['', 'system', 'scan', 'subscribe', 'tmdb']

  return (
    <div className="space-y-4">
      {/* 筛选栏 */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:border-primary focus:outline-none"
        >
          {levels.map((l) => (
            <option key={l} value={l}>{l || '全部级别'}</option>
          ))}
        </select>

        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground focus:border-primary focus:outline-none"
        >
          {categories.map((c) => (
            <option key={c} value={c}>{c || '全部分类'}</option>
          ))}
        </select>

        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && fetch()}
            placeholder="搜索关键字..."
            className="rounded-md border border-border bg-background py-1.5 pl-8 pr-3 text-xs text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none w-48"
          />
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted-foreground">共 {total} 条</span>
          <button
            onClick={handleClear}
            className="flex items-center gap-1 rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:text-red-400 transition-colors"
          >
            <Trash2 size={12} /> 清空
          </button>
        </div>
      </div>

      {/* 日志列表 */}
      {loading ? (
        <TableSkeleton rows={10} cols={4} />
      ) : logs.length === 0 ? (
        <EmptyState title="暂无日志" description="系统运行时产生的日志会显示在这里" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full font-mono text-xs">
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className="border-b border-border hover:bg-accent/20 transition-colors group">
                  <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground w-2">
                    {formatTime(log.timestamp)}
                  </td>
                  <td className={`whitespace-nowrap px-3 py-1.5 w-2 ${LOG_LEVEL_COLORS[log.level] || ''}`}>
                    {log.level === 'INFO' ? 'ℹ' : log.level === 'SUCCESS' ? '✓' : log.level === 'WARN' ? '⚠' : log.level === 'ERROR' ? '✗' : ''}
                    {' '}{log.level}
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground w-2">
                    [{log.category}]
                  </td>
                  <td className="px-3 py-1.5 text-foreground group-hover:bg-accent/30">
                    {log.message}
                  </td>
                  <td className="w-2 px-2 py-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() => handleCopy(log.message)}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                      title="复制"
                    >
                      <Copy size={12} />
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
