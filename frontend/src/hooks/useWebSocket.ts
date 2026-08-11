import { useEffect, useRef } from 'react'
import { wsClient } from '@/lib/ws'

/**
 * WebSocket 连接 Hook
 *
 * 组件挂载时自动连接，卸载时自动断开。
 * 使用 useRef 持有 handler，避免每次渲染重订阅。
 *
 * 用法：
 *   useWebSocket('scan.progress', (data) => { ... })
 */
export function useWebSocket(event: string, handler: (data: any) => void) {
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    wsClient.connect()
    // 注册稳定回调：调用最新的 handlerRef
    const stableHandler = (data: any) => handlerRef.current(data)
    const unsubscribe = wsClient.on(event, stableHandler)
    return () => { unsubscribe(); }
  }, [event])
}

/**
 * 订阅多个 WebSocket 事件
 */
export function useWebSocketEvents(handlers: Record<string, (data: any) => void>) {
  // 序列化 handlers 为稳定 key（避免每次渲染重建）
  const key = JSON.stringify(Object.keys(handlers).sort())
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  useEffect(() => {
    wsClient.connect()
    const entries = Object.entries(handlersRef.current)
    const unsubs = entries.map(([event]) => {
      const stableHandler = (data: any) => {
        const fn = handlersRef.current[event]
        if (fn) fn(data)
      }
      return wsClient.on(event, stableHandler)
    })
    return () => { unsubs.forEach((unsub) => { unsub(); }); }
  }, [key])
}

/** 是否桌面端 */
import { useState } from 'react'
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)
  useEffect(() => {
    const mq = window.matchMedia(query)
    setMatches(mq.matches)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [query])
  return matches
}
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)')
}
