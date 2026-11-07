import { AnimatePresence, motion } from 'framer-motion'
import { Clock3 } from 'lucide-react'
import type { ItemEventResponse, ItemStatus } from './types'

function durationLabel(minutes: number) {
  if (minutes < 1) return '不足 1 分钟'
  const hours = Math.floor(minutes / 60)
  const remaining = minutes % 60
  return hours ? `${hours} 小时 ${remaining} 分钟` : `${remaining} 分钟`
}

export function ItemTimeline({ data, status }: { data: ItemEventResponse | null; status: ItemStatus }) {
  const events = data?.events || []
  const isFinished = status === 'COMPLETED' || status === 'ARCHIVED'
  return <section className="panel timeline-panel" aria-label="物品流转记录">
    <div className="panel-heading"><Clock3 size={21} /><h2>流转记录</h2></div>
    {events.length ? <ol className="item-timeline"><AnimatePresence initial={false}>{events.map((event, index) => <motion.li key={event.id} className={index === events.length - 1 && !isFinished ? 'current' : 'done'} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25, delay: Math.min(index * 0.025, 0.2) }}><span className="timeline-dot" /><div><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</time><strong>{event.text}</strong></div></motion.li>)}</AnimatePresence></ol>
      : <p className="muted">正在加载流转记录…</p>}
    {data?.total_minutes !== null && data?.total_minutes !== undefined && <div className="timeline-total"><span>总流转时间</span><strong>{durationLabel(data.total_minutes)}</strong></div>}
  </section>
}
