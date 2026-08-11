import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * 合并 className（支持条件类名 + Tailwind 冲突去重）
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 格式化时间字符串
 */
export function formatTime(ts: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 将秒数格式化为可读时间
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分${seconds % 60}秒`
  return `${Math.floor(seconds / 3600)}时${Math.round((seconds % 3600) / 60)}分`
}

/**
 * 状态常量映射
 */
export const STATUS_MAP: Record<string, { label: string; color: string }> = {
  partial:      { label: '缺集补全',  color: 'bg-amber-500' },
  full_missing: { label: '整季缺失',  color: 'bg-red-500' },
  complete:     { label: '完整',       color: 'bg-emerald-500' },
  error:        { label: '异常',       color: 'bg-red-600' },
}

export const SCAN_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending:   { label: '等待中',  color: 'bg-zinc-500' },
  running:   { label: '扫描中',  color: 'bg-blue-500' },
  paused:    { label: '已暂停',  color: 'bg-amber-500' },
  completed: { label: '已完成',  color: 'bg-emerald-500' },
  failed:    { label: '失败',    color: 'bg-red-500' },
  cancelled: { label: '已取消',  color: 'bg-zinc-400' },
}

export const LOG_LEVEL_COLORS: Record<string, string> = {
  INFO:    'text-blue-400',
  SUCCESS: 'text-emerald-400',
  WARN:    'text-amber-400',
  ERROR:   'text-red-400',
}
