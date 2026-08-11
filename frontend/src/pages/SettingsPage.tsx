import { useState, useEffect, useCallback } from 'react'
import { Save, Wifi, ShieldCheck, RefreshCw } from 'lucide-react'
import api from '@/lib/api'
import { toast } from 'sonner'

/**
 * 设置页 —— 分组卡片式布局
 *
 * 分组：
 *   1. MoviePilot 连接
 *   2. TMDB 数据源
 *   3. 自动化
 *   4. 安全（改密码）
 */
export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // 改密码
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [changingPwd, setChangingPwd] = useState(false)

  const fetch = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.get('/settings')
      if (res.data.success) {
        const map: Record<string, string> = {}
        res.data.data.items.forEach((item: any) => {
          map[item.key] = item.value
        })
        setSettings(map)
      }
    } catch (e) {
      console.error('获取设置失败:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { fetch() }, [fetch])

  const update = (key: string, value: any) => {
    setSettings((prev) => ({ ...prev, [key]: String(value) }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await api.put('/settings', {
        mp_url: settings.mp_url,
        mp_token: settings.mp_token,
        tmdb_key: settings.tmdb_key,
        tmdb_lang: settings.tmdb_lang,
        auto_scan: settings.auto_scan === '1',
        scan_interval: parseInt(settings.scan_interval || '12'),
        auto_subscribe: settings.auto_subscribe === '1',
        include_specials: settings.include_specials === '1',
      })
      if (res.data.success) toast.success('设置已保存')
      else toast.error(res.data.message || '保存失败')
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '保存失败')
    }
    setSaving(false)
  }

  const handleTestConnection = async () => {
    try {
      const res = await api.post('/settings/test', {
        mp_url: settings.mp_url,
        mp_token: settings.mp_token,
      })
      res.data.data?.results?.forEach((r: any) => {
        if (r.ok === true) toast.success(`${r.name}: ${r.detail}`)
        else if (r.ok === false) toast.error(`${r.name}: ${r.detail}`)
        else toast(r.name + ': ' + r.detail)
      })
    } catch (e) {
      toast.error('测试连接失败')
    }
  }

  const handleChangePwd = async () => {
    if (newPwd.length < 6) { toast.error('新密码至少 6 位'); return }
    setChangingPwd(true)
    try {
      const res = await api.post('/auth/change-password', {
        old_password: oldPwd,
        new_password: newPwd,
      })
      if (res.data.success) {
        toast.success('密码已修改，其他设备需要重新登录')
        setOldPwd('')
        setNewPwd('')
      } else {
        toast.error(res.data.message || '修改失败')
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.message || '修改失败')
    }
    setChangingPwd(false)
  }

  if (loading) {
    return <div className="space-y-4">{[1,2,3,4].map(i => <div key={i} className="h-32 animate-pulse rounded-lg bg-accent" />)}</div>
  }

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      {/* MoviePilot */}
      <SettingsCard title="MoviePilot" icon={<Wifi size={16} />} badge={settings.mp_url ? '已配置' : undefined}>
        <Field label="地址" value={settings.mp_url || ''} onChange={(v) => update('mp_url', v)} placeholder="http://192.168.1.100:3000" />
        <Field label="API Token" value={settings.mp_token || ''} onChange={(v) => update('mp_token', v)} placeholder="MoviePilot API Token" password />
      </SettingsCard>

      {/* TMDB */}
      <SettingsCard title="TMDB 数据源" icon={<RefreshCw size={16} />}>
        <Field label="API Key" value={settings.tmdb_key || ''} onChange={(v) => update('tmdb_key', v)} placeholder="TMDB API Key（MoviePilot v3 无需填写）" password />
        <Field label="语言" value={settings.tmdb_lang || ''} onChange={(v) => update('tmdb_lang', v)} placeholder="zh-CN" />
      </SettingsCard>

      {/* 自动化 */}
      <SettingsCard title="自动化" icon={<RefreshCw size={16} />}>
        <ToggleField label="自动扫描" checked={settings.auto_scan === '1'} onChange={(v) => update('auto_scan', v ? '1' : '0')} />
        <Field label="扫描间隔（小时）" value={settings.scan_interval || '12'} onChange={(v) => update('scan_interval', v)} type="number" />
        <ToggleField label="扫描后自动订阅" checked={settings.auto_subscribe === '1'} onChange={(v) => update('auto_subscribe', v ? '1' : '0')} />
        <ToggleField label="包含特别篇 S00" checked={settings.include_specials === '1'} onChange={(v) => update('include_specials', v ? '1' : '0')} />
      </SettingsCard>

      {/* 安全 */}
      <SettingsCard title="安全" icon={<ShieldCheck size={16} />}>
        <Field label="当前密码" value={oldPwd} onChange={setOldPwd} password placeholder="输入当前密码" />
        <Field label="新密码" value={newPwd} onChange={setNewPwd} password placeholder="至少 6 位" />
        <button
          onClick={handleChangePwd}
          disabled={changingPwd || !oldPwd || !newPwd}
          className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {changingPwd ? '修改中...' : '修改密码'}
        </button>
      </SettingsCard>

      {/* 底部按钮 */}
      <div className="flex gap-2 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 rounded bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <Save size={14} /> {saving ? '保存中...' : '保存设置'}
        </button>
        <button
          onClick={handleTestConnection}
          className="flex items-center gap-1.5 rounded border border-border px-4 py-2 text-sm text-muted-foreground hover:text-foreground"
        >
          <Wifi size={14} /> 测试连接
        </button>
      </div>
    </div>
  )
}

// ========== 子组件 ==========

function SettingsCard({ title, icon, badge, children }: {
  title: string; icon: React.ReactNode; badge?: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        {icon}
        <h3 className="text-sm font-medium">{title}</h3>
        {badge && (
          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-400">{badge}</span>
        )}
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type, password }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; type?: string; password?: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-xs text-muted-foreground">{label}</span>
      <input
        type={password ? 'password' : (type || 'text')}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
      />
    </div>
  )
}

function ToggleField({ label, checked, onChange }: {
  label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 text-xs text-muted-foreground">{label}</span>
      <button
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full transition-colors ${checked ? 'bg-primary' : 'bg-accent border border-border'}`}
      >
        <div className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${checked ? 'left-4' : 'left-0.5'}`} />
      </button>
    </div>
  )
}
