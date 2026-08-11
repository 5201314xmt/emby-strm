/**
 * HTTP API 客户端 —— 基于 Axios 封装
 *
 * 特性：
 *   - Cookie 自动携带（认证用）
 *   - 401 自动跳转登录页
 *   - 统一错误处理
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true,      // 自动携带 Cookie
})

// 响应拦截器：401 → 跳转登录
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const path = window.location.pathname
      if (path !== '/login' && path !== '/setup') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

export default api
