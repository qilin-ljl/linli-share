import { useCallback, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, MessageCircle, Search } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import { slotLabel, timeAgo } from '../format'
import { PrivateChat } from '../PrivateChat'
import type { Item, MessageThread, Reservation } from '../types'
import { Avatar, Empty, Loading, ProductImage } from '../ui'

type Tab = 'messages' | 'wanted' | 'reservations'

export function MessagesPage() {
  const { userId, notify } = useApp()
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState<Tab>(() => params.get('tab') === 'reservations' ? 'reservations' : 'messages')
  const [threads, setThreads] = useState<MessageThread[] | null>(null)
  const [wanted, setWanted] = useState<Item[]>([])
  const [detail, setDetail] = useState<Item | null>(null)
  const [pickupCode, setPickupCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const itemId = Number(params.get('item'))
  const otherId = Number(params.get('other'))
  const load = useCallback(() => api<MessageThread[]>('/api/messages/threads', userId).then(setThreads).catch(e => setError(e.message)), [userId])
  useEffect(() => {
    void load()
    const timer = window.setInterval(load, 5000)
    return () => window.clearInterval(timer)
  }, [load])
  useEffect(() => {
    api<Item[]>('/api/my/interests', userId).then(data => setWanted(data.filter(item => item.status === 'AVAILABLE' || item.status === 'RESERVED'))).catch(() => {})
  }, [userId])
  useEffect(() => {
    if (!itemId) return
    api<Item>(`/api/items/${itemId}`, userId).then(setDetail).catch(e => setError(e.message))
  }, [itemId, userId])
  const selected = threads?.find(thread => thread.item.id === itemId && thread.other_user.id === otherId)
  const other = selected?.other_user || (detail?.owner.id === otherId ? detail.owner : null)
  const open = (item: number, person: number) => { setParams({ item: String(item), other: String(person) }); setError('') }
  const action = async (path: string, body?: object) => {
    setBusy(true); setError('')
    try {
      await api(path, userId, { method: 'POST', ...(body ? { body: jsonBody(body) } : {}) })
      if (itemId) setDetail(await api<Item>(`/api/items/${itemId}`, userId))
      await load()
      notify('交接状态已更新，双方可在私聊中查看')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  const reservation: Reservation | undefined = detail?.owner.id === userId
    ? detail.reservations?.find(row => row.buyer.id === otherId && (row.status === 'PENDING' || row.status === 'CONFIRMED'))
    : detail?.my_reservation || undefined
  const visibleThreads = (threads || []).filter(thread => tab !== 'reservations' || thread.reservation_status === 'PENDING' || thread.reservation_status === 'CONFIRMED')

  return <div className="container page messages-page">
    <div className="page-intro"><div><span className="eyebrow"><MessageCircle size={16} /> 邻里私聊</span><h1>消息</h1><p>预约、问答与交接只在双方私聊中沟通。</p></div></div>
    <div className="message-tabs" role="tablist" aria-label="消息分类">
      <button role="tab" aria-selected={tab === 'messages'} className={tab === 'messages' ? 'active' : ''} onClick={() => setTab('messages')}>我的消息 {threads?.reduce((sum, row) => sum + row.unread_count, 0) || ''}</button>
      <button role="tab" aria-selected={tab === 'wanted'} className={tab === 'wanted' ? 'active' : ''} onClick={() => setTab('wanted')}>我想要</button>
      <button role="tab" aria-selected={tab === 'reservations'} className={tab === 'reservations' ? 'active' : ''} onClick={() => setTab('reservations')}>我的预约</button>
    </div>
    {error && <p className="inline-error">{error}</p>}
    <div className={`messages-layout ${itemId ? 'thread-open' : ''}`}>
      <aside className="panel thread-list">
        {tab === 'wanted' ? wanted.length ? wanted.map(item => <button key={item.id} onClick={() => open(item.id, item.owner.id)}><ProductImage imageKey={item.image_key} /><span><strong>{item.title}</strong><small>我表达过想要 · 与发布者聊聊</small></span></button>) : <Empty title="还没有想要的物品" detail="逛逛市集，点开喜欢的物品。" />
          : !threads ? <Loading /> : visibleThreads.length ? visibleThreads.map(thread => <button key={`${thread.item.id}-${thread.other_user.id}`} className={itemId === thread.item.id && otherId === thread.other_user.id ? 'selected' : ''} onClick={() => open(thread.item.id, thread.other_user.id)}><ProductImage imageKey={thread.item.image_key} /><span><strong>{thread.other_user.display_name} · {thread.item.title}</strong><small>{thread.last_message.is_ai ? 'AI 助手：' : ''}{thread.last_message.body}</small><small>{timeAgo(thread.last_message.created_at)}</small></span>{thread.unread_count > 0 && <em>{thread.unread_count}</em>}</button>) : <Empty title={tab === 'reservations' ? '暂无预约消息' : '暂无私聊消息'} detail="从物品详情发起私聊，消息会显示在这里。" />}
      </aside>
      <section className="message-conversation">
        {itemId && detail?.id === itemId && other ? <>
          <div className="panel message-item-head"><button className="message-back" onClick={() => setParams({})} aria-label="返回消息列表"><ArrowLeft size={20} /></button><Avatar user={other} size="small" /><div><strong>{other.display_name}</strong><Link to={`/item/${itemId}`}>{detail.title} · 查看详情</Link></div></div>
          {reservation && <div className="panel chat-reservation"><strong>预约交接 · {reservation.status === 'PENDING' ? '待发布者确认' : '已确认'}</strong><p>{slotLabel(reservation.slot)}{reservation.status === 'CONFIRMED' ? ` · ${detail.visible_location}` : ''}{reservation.handover_status !== 'WAITING' ? ` · ${reservation.handover_status === 'ARRIVED' ? '买家已到达' : reservation.handover_status === 'DEPARTED' ? '买家已出发' : '买家将晚到'}` : ''}</p>
            {detail.owner.id === userId && reservation.status === 'PENDING' && <div><button className="btn btn-primary" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/confirm`)}>接受预约</button><button className="btn btn-outline" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/reject`)}>婉拒</button></div>}
            {detail.owner.id !== userId && reservation.status === 'CONFIRMED' && <div><span>领取码：<strong>{reservation.pickup_code}</strong></span><button className="btn btn-outline" disabled={busy || reservation.handover_status === 'DEPARTED' || reservation.handover_status === 'ARRIVED'} onClick={() => action(`/api/reservations/${reservation.id}/handover-status`, { status: 'DEPARTED' })}>{reservation.handover_status === 'DEPARTED' || reservation.handover_status === 'ARRIVED' ? '已出发' : '我出发了'}</button><button className="btn btn-outline" disabled={busy || reservation.handover_status === 'ARRIVED'} onClick={() => action(`/api/reservations/${reservation.id}/handover-status`, { status: 'ARRIVED' })}>{reservation.handover_status === 'ARRIVED' ? '已到达' : '我到了'}</button>{reservation.handover_status !== 'ARRIVED' && <button className="btn btn-outline" disabled={busy || reservation.handover_status === 'DELAYED'} onClick={() => action(`/api/reservations/${reservation.id}/handover-status`, { status: 'DELAYED' })}>晚到10分钟</button>}</div>}
            {detail.owner.id === userId && reservation.status === 'CONFIRMED' && <div><input aria-label="输入领取码" inputMode="numeric" maxLength={4} value={pickupCode} onChange={e => setPickupCode(e.target.value.replace(/\D/g, ''))} placeholder="4 位领取码" /><button className="btn btn-primary" disabled={busy || pickupCode.length !== 4} onClick={() => action(`/api/reservations/${reservation.id}/complete`, { pickup_code: pickupCode })}>确认交接</button></div>}
            {detail.owner.id === userId && reservation.status === 'CONFIRMED' && reservation.overdue && <div><span>预约时间已过，可以继续等候或释放物品。</span><button className="btn btn-outline" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/wait`)}>再等10分钟</button><button className="btn btn-outline" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/release`)}>释放预约</button></div>}
            <button className="text-link" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/cancel`)}>取消预约</button>
          </div>}
          <PrivateChat key={`${itemId}-${other.id}`} itemId={itemId} userId={userId} otherUser={other} showFaq={detail.owner.id !== userId} />
        </> : <div className="panel message-empty"><Search size={30} /><h2>选一位邻居聊聊</h2><p>预约申请和 AI 快捷问答也会汇入私人会话。</p></div>}
      </section>
    </div>
  </div>
}
