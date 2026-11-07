import type { HandoverSlot, Item, TradeType } from './types'

export function priceLabel(item: { trade_type: TradeType; price: number | null }) {
  if (item.trade_type === 'FREE') return '免费送'
  if (item.trade_type === 'NEGOTIABLE') return '随便给'
  return `¥ ${item.price ?? 0}`
}

export function freshLabel(date: string) {
  const hours = Math.max(0, (Date.now() - new Date(date).getTime()) / 3600000)
  if (hours < 24) return '刚上架'
  if (hours < 72) return '新上架'
  return `已上架 ${Math.floor(hours / 24)} 天`
}

export function timeAgo(date: string) {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 60000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`
  return `${Math.floor(minutes / 1440)} 天前`
}

export function slotLabel(slot: HandoverSlot | { starts_at: string; ends_at: string }) {
  const start = new Date(slot.starts_at)
  const end = new Date(slot.ends_at)
  const now = new Date()
  const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  const day = sameDay(start, now) ? '今天' : sameDay(start, tomorrow) ? '明天' : `${start.getMonth() + 1}月${start.getDate()}日`
  const time = (value: Date) => `${String(value.getHours()).padStart(2, '0')}:${String(value.getMinutes()).padStart(2, '0')}`
  return `${day} ${time(start)}–${time(end)}`
}

export function statusLabel(item: Item) {
  if (item.status === 'UNCONFIRMED') return '等待确认'
  if (item.status === 'RESERVED') return '已预约'
  if (item.status === 'COMPLETED') return '已完成'
  if (item.status === 'ARCHIVED') return '已归档'
  return freshLabel(item.created_at)
}

export function durationFromHours(hours: number) {
  return hours < 1 ? `${Math.max(1, Math.round(hours * 60))} 分钟` : `${hours} 小时`
}

export function distanceLabel(meters: number | null | undefined) {
  if (meters === null || meters === undefined) return null
  const rounded = meters < 500 ? Math.round(meters / 10) * 10 : Math.round(meters / 100) * 100
  return rounded >= 1000 ? `距你约 ${(rounded / 1000).toFixed(1)} km` : `距你约 ${rounded} m`
}
