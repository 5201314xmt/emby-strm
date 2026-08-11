import { useState, useEffect, useCallback } from 'react'
import { Plus, Pencil, Trash2, Play, CheckCircle } from 'lucide-react'
import api from '@/lib/api'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { EmptyState } from '@/components/shared/EmptyState'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

interface SourceItem {
  id: number
  name: string
  path: string
  type: string
  enabled: boolean
  emby_url?: string
  emby_api_key?: string
  last_scan_at?: string
  last_scan_status?: string
  last_error?: string
  show_count?: number
  created_at?: string
}

/**
 * 扫描源管理页 —— 添加/编辑/删除/检查 STRM 目录和 Emby 源
 */
export default function SourcesPage() {
  const [sources, setSources] = useState<SourceItem[]>([])
  const [loading, setLoading] = useState(true)
  const [editItem, setEditItem] = useState<SourceItem | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formName, setFormName] = useState('')
  const [formPath, setFormPath] = useState('')
  const [formType, setFormType] = useState('filesystem')
  const [formEmbyUrl, setFormEmbyUrl] = useState('')
  const [formEmbyKey, setFormEmbyKey] = useState('')

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/sources')
      if (res.data.success) setSources(res.data.data.items)
    } catch (e) {
      console.error('获取源列表失败:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const resetForm = () => {
    setFormName('')
    setFormPath('')
    setFormType('filesystem')
    setFormEmbyUrl('')
    setFormEmbyKey('')
  }

  const handleSave = async () => {
    if (!formName.trim() || !formPath.trim()) {
      toast.error('名称和路径不能为空')
      return
    }
    const body: any = { name: formName, path: formPath, type: formType }
    if (formType === 'emby') {
      body.emby_url = formEmbyUrl
      body.emby_api_key = formEmbyKey
    }
    try {
      if (editItem) {
        await api.put(`/sources/${editItem.id}`, body)
        toast.success('已更新')
      } else {
        await api.post('/sources', body)
        toast.success('已添加')
      }
      setShowForm(false)
      setEditItem(null)
      resetForm()
      fetch()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '操作失败')
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`确定删除扫描源「${name}」吗？`)) return
    try {
      await api.delete(`/sources/${id}`)
      toast.success('已删除')
      fetch()
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '删除失败')
    }
  }

  const handleCheck = async (id: number) => {
    try {
      const res = await api.post(`/sources/${id}/check`)
      if (res.data.success) toast.success(res.data.message)
      else toast.error(res.data.message)
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '检查失败')
    }
  }

  const handleScan = async (sourceId: number) => {
    try {
      const res = await api.post('/scan/start', { source_ids: [sourceId] })
      if (res.data.success) toast.success('扫描已开始')
      else toast.error(res.data.message || '启动失败')
    } catch (e: any) {
      toast.error('启动扫描失败')
    }
  }

  const openEdit = (item: SourceItem) => {
    setEditItem(item)
    setFormName(item.name)
    setFormPath(item.path)
    setFormType(item.type || 'filesystem')
    setFormEmbyUrl(item.emby_url || '')
    setFormEmbyKey(item.emby_api_key || '')
    setShowForm(true)
  }

  const openAdd = () => {
    setEditItem(null)
    resetForm()
    setShowForm(true)
  }

  return (
    <div className="space-y-4">
      {/* 头部 */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm text-muted-foreground">
          共 {sources.length} 个扫描源
        </h2>
        <button
          onClick={openAdd}
          className="flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Plus size={12} /> 添加源
        </button>
      </div>

      {/* 添加/编辑表单 */}
      {showForm && (
        <div className="rounded-lg border border-border bg-card p-4 space-y-3">
          <h3 className="text-sm font-medium">{editItem ? '编辑扫描源' : '添加扫描源'}</h3>

          {/* 类型选择 */}
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground">类型：</span>
            <button
              onClick={() => setFormType('filesystem')}
              className={cn('rounded px-3 py-1 border transition-colors',
                formType === 'filesystem' ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground')}
            >
              STRM 目录
            </button>
            <button
              onClick={() => setFormType('emby')}
              className={cn('rounded px-3 py-1 border transition-colors',
                formType === 'emby' ? 'border-primary bg-primary/10 text-primary' : 'border-border text-muted-foreground')}
            >
              Emby 服务器
            </button>
          </div>

          <div className="flex gap-3">
            <input
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              placeholder="源名称（如 '139_video1'）"
              className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
            />
            <input
              value={formPath}
              onChange={(e) => setFormPath(e.target.value)}
              placeholder={formType === 'filesystem' ? "容器内路径（如 '/media/139_video1'）" : "Emby 地址（如 'http://192.168.1.100:8096'）"}
              className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>

          {/* Emby 专用字段 */}
          {formType === 'emby' && (
            <div className="flex gap-3">
              <input
                value={formEmbyKey}
                onChange={(e) => setFormEmbyKey(e.target.value)}
                placeholder="Emby API Key（Emby 设置→高级→API密钥）"
                className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
                type="password"
              />
            </div>
          )}

          <div className="flex gap-2">
            <button
              onClick={handleSave}
              className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90"
            >
              保存
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="rounded border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 源列表 */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-accent" />
          ))}
        </div>
      ) : sources.length === 0 ? (
        <EmptyState
          title="还没有扫描源"
          description="添加 STRM 文件目录或 Emby 服务器，系统才能扫描媒体库"
          action={
            <button
              onClick={openAdd}
              className="flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90"
            >
              <Plus size={14} /> 添加第一个源
            </button>
          }
        />
      ) : (
        <div className="space-y-3">
          {sources.map((src) => (
            <div key={src.id} className="rounded-lg border border-border bg-card p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{src.name}</span>
                    <span className={cn('inline-flex items-center rounded border px-1.5 py-0.5 text-xs',
                      src.type === 'emby' ? 'border-violet-500/30 text-violet-400 bg-violet-500/10' : 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10'
                    )}>
                      {src.type === 'emby' ? 'Emby' : 'STRM'}
                    </span>
                    {!src.enabled && (
                      <span className="text-xs text-zinc-500">已禁用</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{src.path}</p>
                  {src.emby_url && (
                    <p className="text-xs text-muted-foreground">Emby: {src.emby_url}</p>
                  )}
                  {src.last_scan_at && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>上次扫描：{src.last_scan_at}</span>
                      {src.last_scan_status && (
                        <StatusBadge value={src.last_scan_status} variant="scan" />
                      )}
                      {src.show_count != null && <span>{src.show_count} 部剧</span>}
                    </div>
                  )}
                  {src.last_error && (
                    <p className="text-xs text-red-400 truncate">{src.last_error}</p>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  <button onClick={() => handleCheck(src.id)} className="rounded p-1.5 text-muted-foreground hover:text-foreground" title="测试连通性">
                    <CheckCircle size={14} />
                  </button>
                  <button onClick={() => handleScan(src.id)} className="rounded p-1.5 text-muted-foreground hover:text-primary" title="扫描此源">
                    <Play size={14} />
                  </button>
                  <button onClick={() => openEdit(src)} className="rounded p-1.5 text-muted-foreground hover:text-foreground" title="编辑">
                    <Pencil size={14} />
                  </button>
                  <button onClick={() => handleDelete(src.id, src.name)} className="rounded p-1.5 text-muted-foreground hover:text-red-400" title="删除">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
