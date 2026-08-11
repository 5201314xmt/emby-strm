import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { ShieldCheck } from 'lucide-react'
import { toast } from 'sonner'

/**
 * 首次安装向导 —— 设置管理员密码
 */
export default function SetupPage() {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const { setup, checkStatus, initialized, loggedIn, loading: authLoading } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => { checkStatus() }, [checkStatus])

  // 等待认证状态加载完成后再判断跳转
  useEffect(() => {
    if (authLoading) return
    if (initialized && loggedIn) {
      navigate('/dashboard', { replace: true })
    } else if (initialized && !loggedIn) {
      navigate('/login', { replace: true })
    }
  }, [initialized, loggedIn, authLoading, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 6) {
      toast.error('密码至少 6 位')
      return
    }
    if (password !== confirm) {
      toast.error('两次输入的密码不一致')
      return
    }
    setLoading(true)
    const ok = await setup(password)
    setLoading(false)
    if (ok) {
      toast.success('密码设置成功，请牢记！')
      navigate('/dashboard', { replace: true })
    } else {
      toast.error('设置失败')
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-8">
        <div className="mb-6 flex flex-col items-center">
          <div className="mb-3 rounded-full bg-primary/10 p-3">
            <ShieldCheck size={28} className="text-primary" />
          </div>
          <h1 className="text-lg font-semibold">欢迎使用缺集管家</h1>
          <p className="mt-1 text-sm text-muted-foreground">第 1 步：设置管理员密码</p>
        </div>

        {/* 步骤指示 */}
        <div className="mb-4 flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">1</span>
          <span>密码</span>
          <span className="text-border">→</span>
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-xs">2</span>
          <span>配置</span>
          <span className="text-border">→</span>
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-xs">3</span>
          <span>扫描</span>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">
          设置密码后，请前往「设置」页填写 MoviePilot 地址和 Token，再到「扫描源」页添加 STRM 目录。
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="管理员密码（至少 6 位）"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
            autoFocus
          />
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="确认密码"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {loading ? '设置中...' : '设置密码并进入'}
          </button>
        </form>
      </div>
    </div>
  )
}
