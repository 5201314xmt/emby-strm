import { useEffect } from 'react'
import { wsClient } from '@/lib/ws'

/**
 * WebSocket 连接 Hook
 *
 * 组件挂载时自动连接，卸载时自动断开。
 * 用法：
 *   useWebSocket('scan.progress', (data) => { ... })
 */
export function useWebSocket(event: string, handler: (data: any) => void) {
  useEffect(() => {
    wsClient.connect()
    const unsubscribe = wsClient.on(event, handler)
    return () => { unsubscribe(); }
  }, [event, handler])
}

/**
 * 订阅多个 WebSocket 事件
 */
export function useWebSocketEvents(handlers: Record<string, (data: any) => void>) {
  useEffect(() => {
    wsClient.connect()
    const unsubs = Object.entries(handlers).map(([event, fn]) =>
      wsClient.on(event, fn)
    )
    return () => { unsubs.forEach((unsub) => { unsub(); }); }
  }, [])
}
