import { useEffect, useState } from 'react'

/**
 * 响应式断点检测 Hook
 */
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

/** 是否桌面端（≥768px） */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)')
}
