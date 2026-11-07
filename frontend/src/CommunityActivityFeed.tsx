import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, Clock3, Leaf, Package, Sparkles } from 'lucide-react'
import { api } from './api'
import { useApp } from './context'
import { timeAgo } from './format'
import type { ActivityEvent } from './types'

function eventIcon(type: string) {
  if (type === 'TRANSACTION_COMPLETED') return <Check size={20} />
  if (type === 'RESERVATION_CONFIRMED') return <Clock3 size={20} />
  if (type === 'ACTIVE_CONFIRMED') return <Leaf size={20} />
  return <Package size={20} />
}

export function CommunityActivityFeed() {
  const { userId } = useApp()
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [index, setIndex] = useState(0)
  const latestId = useRef<number | null>(null)

  useEffect(() => {
    let active = true
    const refresh = () => api<ActivityEvent[]>('/api/activity?limit=6', userId)
      .then(data => {
        if (!active) return
        if (data[0]?.id !== latestId.current) { latestId.current = data[0]?.id ?? null; setIndex(0) }
        setEvents(data)
      }).catch(() => {})
    refresh()
    const timer = window.setInterval(refresh, 8_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [userId])
  useEffect(() => {
    if (events.length < 2) return
    const timer = window.setInterval(() => setIndex(current => (current + 1) % events.length), 5_000)
    return () => window.clearInterval(timer)
  }, [events.length])

  const event = events[index % events.length]
  return <div className="hero-activity-card" aria-label="实时邻里动态">
    <div className="hero-activity-head"><span><Sparkles size={15} /> 邻里动态</span><small><i /> 8 秒更新</small></div>
    <div className="hero-activity-window"><AnimatePresence mode="wait" initial={false}>{event ? <motion.div key={event.id} initial={{ opacity: 0, y: 19 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -19 }} transition={{ duration: 0.35 }}><Link to={`/item/${event.item_id}`}><span className={`activity-icon activity-${event.type.toLowerCase()}`}>{eventIcon(event.type)}</span><span><small>{timeAgo(event.created_at)}</small><strong>{event.text}</strong></span></Link></motion.div> : <p>有新的邻里流转时，这里会自动显示。</p>}</AnimatePresence></div>
    {events.length > 1 && <div className="hero-activity-dots" aria-label={`第 ${index + 1} 条，共 ${events.length} 条`}>{events.map((entry, position) => <i key={entry.id} className={position === index ? 'active' : ''} />)}</div>}
  </div>
}
