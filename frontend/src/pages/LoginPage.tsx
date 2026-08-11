import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { KeyRound } from 'lucide-react'
import { toast } from 'sonner'

/**
 * 登录页 —— 输入管理员密码登录
 */
export default function LoginPage() {
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { login, checkStatus, initialized, loggedIn, loading: authLoading } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => { checkStatus() }, [checkStatus])

  // 等待认证状态加载完成后再判断跳转
  useEffect(() => {
    if (authLoading) return
    if (initialized && loggedIn) {
      navigate('/dashboard', { replace: true })
    }
    if (!initialized) {
      navigate('/setup', { replace: true })
    }
  }, [initialized, loggedIn, authLoading, navigate])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!password) return
    setLoading(true)
    const ok = await login(password)
    setLoading(false)
    if (ok) {
      navigate('/dashboard', { replace: true })
    } else {
      toast.error('密码不正确')
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-8">
        <div className="mb-6 flex flex-col items-center">
          <div className="mb-3 rounded-full bg-primary/10 p-3">
            <KeyRound size={28} className="text-primary" />
          </div>
          <h1 className="text-lg font-semibold">缺集管家</h1>
          <p className="mt-1 text-sm text-muted-foreground">请输入管理员密码</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="管理员密码"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder-muted-foreground focus:border-primary focus:outline-none"
            autoFocus
          />
          <button
            type="submit"
            disabled={loading || !password}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {authLoading ? '检查中...' : loading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  )
}
