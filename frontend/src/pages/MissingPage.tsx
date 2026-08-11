import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import React from 'react'
import {
  Search, ChevronRight, BellOff, Send,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import api from '@/lib/api'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { BatchActionBar } from '@/components/shared/BatchActionBar'
import { EmptyState } from '@/components/shared/EmptyState'
import { TableSkeleton } from '@/components/shared/Skeleton'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface ShowItem {
  tmdb_id: number
  name: string
  year: string
  poster: string
  source_names: string[]
  ignore_entire: boolean
  status: string
  seasons: Array<{
    season_number: number
    total_episodes: number
    aired_episodes: number
    present_count: number
    missing_count: number
    missing_episodes: number[]
    status: string
    data_quality: string
    subscribed: boolean
    ignored: boolean
    mp_state: string
  }>
}

/**
 * 缺集列表页 —— 高密度表格视图
 *
 * 功能：分页、筛选、搜索、批量操作、单行订阅/忽略、展开详情
 */
export default function MissingPage() {
  const [searchParams] = useSearchParams()
  const [shows, setShows] = useState<ShowItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [selectedSource, setSelectedSource] = useState<string>(
    searchParams.get('status') || 'partial'
  )
  const [sortBy, setSortBy] = useState<string>('missing_count')
  const [searchText, setSearchText] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const pageSize = 50

  const fetchShows = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize, sort: sortBy }
      if (selectedSource && selectedSource !== 'all') params.status = selectedSource
      if (searchText) params.search = searchText
      const res = await api.get('/shows', { params })
      if (res.data.success) {
        setShows(res.data.data.items)
        setTotal(res.data.data.total)
      }
    } catch (e) {
      console.error('获取列表失败:', e)
    }
    setLoading(false)
  }, [page, selectedSource, searchText, sortBy])

  useEffect(() => { fetchShows() }, [fetchShows])

  const totalPages = Math.ceil(total / pageSize)

  const toggleSelect = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // 计算所有可选项 (非 complete, 非 ignored)
  const selectableKeys = useMemo(() => {
    const keys: string[] = []
    shows.forEach((show) => {
      show.seasons
        .filter((s) => s.status !== 'complete' && !s.ignored)
        .forEach((s) => keys.push(`${show.tmdb_id}:${s.season_number}`))
    })
    return keys
  }, [shows])

  const allSelected = selectableKeys.length > 0 && selectableKeys.every((k) => selected.has(k))
  const someSelected = selectableKeys.some((k) => selected.has(k))
  const headerCheckboxRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate = someSelected && !allSelected
    }
  }, [someSelected, allSelected])

  const handleSubscribe = async (tmdbId: number, season: number) => {
    try {
      const res = await api.post(`/shows/${tmdbId}/subscribe`, { season })
      toast.success(res.data.message || '订阅已提交')
      fetchShows()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '订阅失败')
    }
  }

  const handleIgnore = async (tmdbId: number, season: number, scope: string) => {
    try {
      const res = await api.post(`/shows/${tmdbId}/ignore`, { season })
      toast.success(res.data.message || `已忽略${scope}`)
      fetchShows()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '操作失败')
    }
  }

  const handleBatchSubscribe = async () => {
    const items = Array.from(selected).map((k) => {
      const [tmdbId, season] = k.split(':').map(Number)
      return { tmdb_id: tmdbId, season }
    })
    try {
      const res = await api.post('/shows/batch/subscribe', { items })
      toast.success(res.data.message || '批量订阅已提交')
      setSelected(new Set())
      fetchShows()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '操作失败')
    }
  }

  const handleBatchIgnore = async () => {
    const items = Array.from(selected).map((k) => {
      const [tmdbId, season] = k.split(':').map(Number)
      return { tmdb_id: tmdbId, season }
    })
    try {
      const res = await api.post('/shows/batch/ignore', { items })
      toast.success(res.data.message || '批量忽略已提交')
      setSelected(new Set())
      fetchShows()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '操作失败')
    }
  }

  const statusOptions = [
    { value: 'all', label: '全部' },
    { value: 'partial', label: '缺集补全' },
    { value: 'full_missing', label: '整季缺失' },
    { value: 'complete', label: '已完成' },
    { value: 'ignored', label: '已忽略' },
    { value: 'error', label: '异常' },
  ]

  // 搜索防抖
  useEffect(() => {
    const timer = setTimeout(() => { setSearchText(searchInput); setPage(1) }, 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  return (
    <div className="space-y-4">
      {/* ========== 筛选栏 ========== */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-border">
          {statusOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => { setSelectedSource(opt.value); setPage(1) }}
              className={cn(
                'border-r border-border px-3 py-1.5 text-xs last:border-r-0 transition-colors',
                selectedSource === opt.value
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {/* 排序 */}
        <select value={sortBy} onChange={(e) => { setSortBy(e.target.value); setPage(1) }}
          className="rounded-md border border-border bg-background px-2 py-1.5 text-xs text-foreground focus:border-primary focus:outline-none">
          <option value="missing_count">缺集多→少</option>
          <option value="missing_count_asc">缺集少→多</option>
          <option value="name">剧名 A→Z</option>
        </select>
        {/* 搜索框 + 清除 */}
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="搜索剧名或 TMDB ID..."
            className="w-full rounded-md border border-border bg-background py-1.5 pl-8 pr-7 text-xs text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
          />
          {searchInput && (
            <button onClick={() => { setSearchInput(''); setSearchText(''); setPage(1) }}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              <span className="text-xs">✕</span>
            </button>
          )}
        </div>
        <span className="text-xs text-muted-foreground ml-auto">共 {total} 条</span>
      </div>

      {/* ========== 批量操作条 ========== */}
      <BatchActionBar
        count={selected.size}
        onSubscribe={handleBatchSubscribe}
        onIgnore={handleBatchIgnore}
        onClear={() => setSelected(new Set())}
      />

      {/* ========== 表格 ========== */}
      {loading ? (
        <TableSkeleton rows={8} cols={6} />
      ) : shows.length === 0 ? (
        <EmptyState
          title="暂无缺集记录"
          description="点击仪表盘的「开始扫描」按钮，让系统分析你的媒体库"
        />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-card/50">
                  <th className="w-10 px-3 py-2 text-left">
                    <input
                      ref={headerCheckboxRef}
                      type="checkbox"
                      checked={allSelected}
                      onChange={(e) => {
                        if (!e.target.checked) { setSelected(new Set()); return }
                        const all: Set<string> = new Set()
                        shows.forEach((show) => {
                          show.seasons
                            .filter((s) => s.status !== 'complete' && !s.ignored)
                            .forEach((s) => all.add(`${show.tmdb_id}:${s.season_number}`))
                        })
                        setSelected(all)
                      }}
                      className="rounded border-border"
                    />
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">剧名</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">来源</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">季</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">已获/已播</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">缺集</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-muted-foreground">状态</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-muted-foreground">操作</th>
                </tr>
              </thead>
              <tbody>
                {shows.flatMap((show) =>
                  show.seasons
                    .filter((s) => {
                      if (selectedSource === 'all') return true
                      if (selectedSource === 'partial') return s.status === 'partial'
                      if (selectedSource === 'full_missing') return s.status === 'full_missing'
                      if (selectedSource === 'complete') return s.status === 'complete'
                      if (selectedSource === 'ignored') return s.ignored
                      if (selectedSource === 'error') return show.status === 'error'
                      return s.status !== 'complete'
                    })
                    .map((season) => {
                      const key = `${show.tmdb_id}:${season.season_number}`
                      const isExpanded = expanded.has(key)
                      return (
                        <React.Fragment key={key}>
                          <tr
                            onClick={() => toggleExpand(key)}
                            className={cn(
                              'border-b border-border transition-colors hover:bg-accent/30 cursor-pointer',
                              season.ignored && 'opacity-50'
                            )}
                          >
                            <td className="px-3 py-2">
                              {season.status !== 'complete' && !season.ignored && (
                                <input
                                  type="checkbox"
                                  checked={selected.has(key)}
                                  onChange={() => toggleSelect(key)}
                                  className="rounded border-border"
                                />
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <span className="font-medium text-foreground">{show.name}</span>
                              {show.year && (
                                <span className="ml-1 text-xs text-muted-foreground">({show.year})</span>
                              )}
                            </td>
                            <td className="px-3 py-2 text-xs text-muted-foreground">
                              {show.source_names.join(', ')}
                            </td>
                            <td className="px-3 py-2 font-mono text-xs">S{String(season.season_number).padStart(2, '0')}</td>
                            <td className="px-3 py-2 text-xs text-muted-foreground">
                              {season.present_count}/{season.aired_episodes}
                            </td>
                            <td className="px-3 py-2">
                              {season.missing_count > 0 ? (
                                <span className="text-amber-400">{season.missing_count} 集</span>
                              ) : (
                                <span className="text-emerald-400">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2">
                              <div className="flex items-center gap-1.5">
                                <StatusBadge value={season.status} variant="status" />
                                {season.data_quality === 'degraded' && (
                                  <StatusBadge value="degraded" variant="quality" />
                                )}
                                {season.subscribed && (
                                  <span className="text-xs text-blue-400">已订阅</span>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2 text-right">
                              <div className="flex items-center justify-end gap-1">
                                <button
                                  onClick={() => toggleExpand(key)}
                                  className={cn(
                                    'rounded p-1 text-muted-foreground hover:text-foreground transition-transform',
                                    isExpanded && 'rotate-90'
                                  )}
                                  title="展开详情"
                                >
                                  <ChevronRight size={14} />
                                </button>
                                {season.status !== 'complete' && !season.subscribed && (
                                  <button
                                    onClick={() => handleSubscribe(show.tmdb_id, season.season_number)}
                                    className="rounded p-1 text-muted-foreground hover:text-primary"
                                    title="订阅此季"
                                  >
                                    <Send size={14} />
                                  </button>
                                )}
                                {!season.ignored && (
                                  <button
                                    onClick={() => handleIgnore(show.tmdb_id, season.season_number, `S${season.season_number}`)}
                                    className="rounded p-1 text-muted-foreground hover:text-amber-400"
                                    title="忽略此季"
                                  >
                                    <BellOff size={14} />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                          {/* 展开行：缺集详情 */}
                          {isExpanded && season.missing_count > 0 && (
                            <tr key={`${key}-detail`} className="border-b border-border bg-accent/20">
                              <td colSpan={8} className="px-6 py-3">
                                <div className="space-y-2">
                                  <p className="text-xs text-muted-foreground">
                                    缺失集 (共 {season.missing_count} 集)：
                                  </p>
                                  <div className="flex flex-wrap gap-1.5">
                                    {season.missing_episodes.map((ep) => (
                                      <span key={ep} className="rounded border border-amber-500/20 bg-amber-500/5 px-2 py-0.5 text-xs text-amber-400">
                                        E{String(ep).padStart(2, '0')}
                                      </span>
                                    ))}
                                  </div>
                                  <div className="flex gap-2">
                                    <button
                                      onClick={() => handleSubscribe(show.tmdb_id, season.season_number)}
                                      disabled={season.subscribed}
                                      className="rounded bg-primary px-3 py-1 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                                    >
                                      {season.subscribed ? '已订阅' : '订阅此季'}
                                    </button>
                                    <button
                                      onClick={() => handleIgnore(show.tmdb_id, season.season_number, `S${season.season_number}`)}
                                      className="rounded border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
                                    >
                                      忽略此季
                                    </button>
                                    <button
                                      onClick={() => handleIgnore(show.tmdb_id, -1, `《${show.name}》`)}
                                      className="rounded border border-border px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
                                    >
                                      忽略整部剧
                                    </button>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      )
                    })
                )}
              </tbody>
            </table>
          </div>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page <= 1}
                className="rounded border border-border px-3 py-1 text-sm text-muted-foreground hover:text-foreground disabled:opacity-30"
              >
                上一页
              </button>
              <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
              <button
                onClick={() => setPage(Math.min(totalPages, page + 1))}
                disabled={page >= totalPages}
                className="rounded border border-border px-3 py-1 text-sm text-muted-foreground hover:text-foreground disabled:opacity-30"
              >
                下一页
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
