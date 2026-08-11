import { Routes, Route, Navigate } from 'react-router-dom'
import { useEffect } from 'react'
import { useAuthStore } from '@/stores/authStore'
import { AppShell } from '@/components/layout/AppShell'
import LoginPage from '@/pages/LoginPage'
import SetupPage from '@/pages/SetupPage'
import DashboardPage from '@/pages/DashboardPage'
import MissingPage from '@/pages/MissingPage'
import SubscriptionsPage from '@/pages/SubscriptionsPage'
import SourcesPage from '@/pages/SourcesPage'
import SettingsPage from '@/pages/SettingsPage'
import LogsPage from '@/pages/LogsPage'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { loggedIn, initialized, loading, checkStatus } = useAuthStore()

  useEffect(() => {
    checkStatus()
  }, [])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    )
  }

  if (!initialized) return <Navigate to="/setup" replace />
  if (!loggedIn) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      {/* 首次安装向导 */}
      <Route path="/setup" element={<SetupPage />} />

      {/* 登录页 */}
      <Route path="/login" element={<LoginPage />} />

      {/* 根路径 → 仪表盘 */}
      <Route path="/" element={
        <ProtectedRoute><AppShell /></ProtectedRoute>
      } />

      {/* 需要登录的应用页面 */}
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/shows" element={<MissingPage />} />
        <Route path="/subscriptions" element={<SubscriptionsPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/logs" element={<LogsPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  )
}
