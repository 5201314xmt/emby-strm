import { create } from 'zustand'
import api from '@/lib/api'

interface AuthState {
  initialized: boolean
  loggedIn: boolean
  loading: boolean
  checkStatus: () => Promise<void>
  login: (password: string) => Promise<boolean>
  logout: () => Promise<void>
  setup: (password: string) => Promise<boolean>
}

export const useAuthStore = create<AuthState>((set) => ({
  initialized: false,
  loggedIn: false,
  loading: true,

  checkStatus: async () => {
    try {
      const res = await api.get('/auth/status')
      if (res.data?.data) {
        const data = res.data.data
        set({ initialized: data.initialized, loggedIn: data.logged_in, loading: false })
      } else {
        set({ loading: false })
      }
    } catch {
      // 网络错误时不改变 initialized 状态（避免误跳到 setup 页）
      set((s) => ({ loading: false, loggedIn: false }))
    }
  },

  login: async (password: string) => {
    try {
      const res = await api.post('/auth/login', { password })
      if (res.data.success) {
        set({ loggedIn: true })
        return true
      }
      return false
    } catch {
      return false
    }
  },

  logout: async () => {
    try {
      await api.post('/auth/logout')
    } finally {
      set({ loggedIn: false })
    }
  },

  setup: async (password: string) => {
    try {
      const res = await api.post('/auth/setup', { password })
      if (res.data.success) {
        set({ initialized: true, loggedIn: true })
        return true
      }
      return false
    } catch {
      return false
    }
  },
}))
