import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowRight, BookOpen, Check, Clock3, Flame, Heart, MapPin, MessageCircle, Package, Repeat2, Send, ShieldCheck, Users, X } from 'lucide-react'
import { motion } from 'framer-motion'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import type { Item, ItemConversation, ItemEventResponse, MatchingNeeds, Reservation } from '../types'
import { Avatar, Empty, Loading, ProductImage } from '../ui'
import { distanceLabel, priceLabel, slotLabel, statusLabel, timeAgo } from '../format'
import { ItemTimeline } from '../ItemTimeline'
import { BuyerHandoverProgress, SellerHandoverProgress } from '../HandoverProgress'

export function DetailPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const itemId = Number(id)
  const [searchParams, setSearchParams] = useSearchParams()
  const { userId, notify, isAuthenticated, requestAuth } = useApp()
  const [item, setItem] = useState<Item | null>(null)
  const [timeline, setTimeline] = useState<ItemEventResponse | null>(null)
  const [conversations, setConversations] = useState<ItemConversation[]>([])
  const [matchingNeeds, setMatchingNeeds] = useState<MatchingNeeds | null>(null)
  const [comment, setComment] = useState('')
  const [bookingOpen, setBookingOpen] = useState(false)
  const [slotId, setSlotId] = useState<number | null>(null)
  const [pickupCodes, setPickupCodes] = useState<Record<number, string>>({})
  const [finishedHours, setFinishedHours] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadDetail = useCallback(async () => {
    const latestItem = await api<Item>(`/api/items/${itemId}`, userId)
    const mine = latestItem.owner.id === userId
    const [latestEvents, latestConversations] = mine ? await Promise.all([
      api<ItemEventResponse>(`/api/items/${itemId}/events`, userId),
      api<ItemConversation[]>(`/api/items/${itemId}/conversations`, userId),
    ]) : [null, []]
    return { latestItem, latestEvents, latestConversations }
  }, [itemId, userId])
  const reload = useCallback(async () => {
    const data = await loadDetail()
    setItem(data.latestItem); setTimeline(data.latestEvents); setConversations(data.latestConversations)
  }, [loadDetail])
  useEffect(() => {
    let active = true
    loadDetail().then(data => { if (active) { setItem(data.latestItem); setTimeline(data.latestEvents); setConversations(data.latestConversations); setError('') } })
      .catch(e => { if (active) setError(e.message) })
    const timer = window.setInterval(() => reload().catch(() => {}), 15_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [itemId, userId, loadDetail, reload])
  useEffect(() => {
    api<MatchingNeeds>(`/api/items/${itemId}/matching-needs`, userId).then(setMatchingNeeds).catch(() => {})
  }, [itemId, userId])
  useEffect(() => {
    if (finishedHours === null) return
    const timer = window.setTimeout(() => setFinishedHours(null), 2200)
    return () => window.clearTimeout(timer)
  }, [finishedHours])

  const action = async <T,>(path: string, init: RequestInit, success: string): Promise<T | null> => {
    if (!isAuthenticated) { requestAuth(`/item/${itemId}`); return null }
    setBusy(true); setError('')
    try { const result = await api<T>(path, userId, init); await reload(); notify(success); return result }
    catch (e) { setError((e as Error).message); return null }
    finally { setBusy(false) }
  }
  const book = async (event: FormEvent) => {
    event.preventDefault(); if (!slotId) return
    const result = await action<Reservation>(`/api/items/${itemId}/reservations`, { method: 'POST', body: jsonBody({ slot_id: slotId }) }, '预约申请已发送给发布者')
    if (result && item) { setBookingOpen(false); navigate(`/messages?item=${itemId}&other=${item.owner.id}`) }
  }
  const complete = async (reservationId: number) => {
    const result = await action<{ hours_to_complete: number }>(`/api/reservations/${reservationId}/complete`,
      { method: 'POST', body: jsonBody({ pickup_code: pickupCodes[reservationId] || '' }) }, '交接完成，流转记录已保存')
    if (result) setFinishedHours(result.hours_to_complete)
  }
  const openChat = (otherUserId: number) => {
    if (!isAuthenticated) { requestAuth(`/messages?item=${itemId}&other=${otherUserId}`); return }
    navigate(`/messages?item=${itemId}&other=${otherUserId}`)
  }

  if (!item || item.id !== itemId) return error ? <Empty title="无法打开物品" detail={error} /> : <Loading />
  const mine = item.owner.id === userId
  const ended = item.status === 'COMPLETED' || item.status === 'ARCHIVED'
  const canBook = item.status === 'AVAILABLE' && (item.handover_slots?.length || 0) > 0 && !item.my_reservation
  const confirmedAgo = timeAgo(item.last_confirmed_at)
  const statusText = item.status === 'AVAILABLE' ? `${confirmedAgo}确认还在` : item.status === 'UNCONFIRMED' ? '超过 72 小时未确认，等待发布者确认' : item.status === 'RESERVED' ? '已有人预约交接' : item.status === 'COMPLETED' ? '已完成流转' : '已归档'
  const bookingModalOpen = isAuthenticated && (bookingOpen || searchParams.get('reserve') === '1')

  return <div className="container page detail-page">
    <div className="breadcrumb"><Link to="/">首页</Link><span>/</span><Link to="/market">闲置市集</Link><span>/</span><strong>{item.title}</strong></div>
    <div className="detail-top">
      <div className="detail-photo"><ProductImage imageKey={item.image_key} /><span className={`fresh-pill status-${item.status.toLowerCase()}`}>{statusLabel(item)}</span></div>
      <div className="detail-summary">
        <span className="eyebrow">{item.category} · {item.condition}</span><h1>{item.title}</h1>
        <strong className={`detail-price notranslate ${item.trade_type === 'FIXED_PRICE' ? 'priced' : ''}`} translate="no">{priceLabel(item)}</strong>
        <div className="detail-meta"><span><MapPin size={18} /> {item.public_location}{distanceLabel(item.distance_meters) && ` · ${distanceLabel(item.distance_meters)}`}</span><time dateTime={item.created_at}><Clock3 size={18} /> 发布于 {new Date(item.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</time><button className={`interest-button ${item.viewer_interested ? 'selected' : ''}`} aria-pressed={mine ? undefined : item.viewer_interested} disabled={busy || (!mine && ended) || (!mine && !item.viewer_interested && item.status !== 'AVAILABLE')} onClick={() => mine ? document.getElementById('interested-neighbors')?.scrollIntoView({ behavior: 'smooth' }) : action(`/api/items/${item.id}/interest`, { method: item.viewer_interested ? 'DELETE' : 'POST' }, item.viewer_interested ? '已取消想要' : '已加入想要')}><Heart size={18} fill={item.viewer_interested ? 'currentColor' : 'none'} /> {item.interest_count} 人想要{!mine && !ended ? ` · ${item.viewer_interested ? '取消' : '点我想要'}` : ''}</button></div>
        <div className={`heartbeat-badge heartbeat-${item.status.toLowerCase()}`}><span className="heartbeat-dot" /><strong>{statusText}</strong></div>
        {item.status === 'RESERVED' && !mine && !item.my_reservation && <p className="status-explain">这件物品已有确认的预约，暂时不能再预约。</p>}
        {item.status === 'UNCONFIRMED' && !mine && <p className="status-explain">发布者重新确认在架后，才能预约领取。</p>}
        <div className="detail-actions">
          {ended ? <div className="completed-banner"><Check size={22} /> {item.status === 'COMPLETED' ? '这件物品已完成流转' : '这件物品已归档'}</div>
            : mine ? item.status === 'RESERVED' ? <div className="reservation-action-note"><ShieldCheck size={20} /> 预约已确认，等待见面交接</div> : <div className="owner-actions"><Link className="btn btn-outline" to={`/publish?edit=${item.id}`}>编辑物品</Link><button className="btn btn-primary" disabled={busy} onClick={() => action(`/api/items/${item.id}/confirm-active`, { method: 'PATCH' }, '已确认在架，邻居现在可以放心预约')}>还在，继续流转</button></div>
            : item.my_reservation ? <div className="reservation-action-note"><ShieldCheck size={20} /> {item.my_reservation.status === 'PENDING' ? '预约申请已发送，等待发布者确认' : '预约已确认，请按约定时间交接'}</div>
            : <button disabled={!canBook || busy} className="btn btn-primary btn-wide" onClick={() => { if (!isAuthenticated) { requestAuth(`/item/${itemId}?reserve=1`); return }; setSlotId(item.handover_slots?.[0]?.id || null); setBookingOpen(true) }}><Clock3 size={20} /> {canBook ? '预约领取' : item.status === 'UNCONFIRMED' ? '等待发布者确认' : item.status === 'RESERVED' ? '已有人预约' : '暂无可预约时间'}</button>}
        </div>
        <div className="seller-card"><Avatar user={item.owner} size="large" /><div><strong>{item.owner.display_name}</strong><span>{item.building_name} · 发布者</span></div>{mine ? <span className="seller-badge">这是你的物品</span> : <button className="btn btn-outline seller-chat-button" onClick={() => openChat(item.owner.id)}><MessageCircle size={16} /> 私聊发布者</button>}</div>
      </div>
    </div>
    {error && <div className="inline-error">{error}</div>}
    <div className="detail-lower">
      <section className="panel"><div className="panel-heading"><Package size={21} /><h2>物品描述</h2></div><p className="description-text">{item.description}</p><div className="detail-tags"><span>{item.category}</span><span>{item.condition}</span><span>{item.disposal_goal === 'FAST' ? '尽快处理' : item.disposal_goal === 'PRICE_FIRST' ? '价格优先' : '均衡流转'}</span></div>{item.original_price && <p className="original-price">发布者填写的购入原价：¥ {item.original_price}</p>}</section>
      <section className="panel"><div className="panel-heading"><MapPin size={21} /><h2>预约交接</h2></div><p className="handover-place"><MapPin size={18} /> {item.visible_location}</p><p className="muted">{item.handover_location ? '已确认预约的双方可见具体公共交接点。' : '预约前只显示楼栋附近；发布者确认后向预约双方显示具体公共交接点。'}</p>{ended ? <p className="muted">交接已结束，发布者可在个人中心查看完整记录。</p> : <><h3 className="small-heading">可领取时间</h3>{item.handover_slots?.length ? <div className="handover-times">{item.handover_slots.map(slot => <span key={slot.id}><Clock3 size={15} />{slotLabel(slot)}</span>)}</div> : <p className="muted">目前没有未来的可领取时间。</p>}</>}</section>
    </div>
    {matchingNeeds && matchingNeeds.count > 0 && <section className="panel detail-need-matches"><div className="panel-heading"><Flame size={21} /><h2>附近正有人需要</h2><span className="panel-count">{matchingNeeds.count} 条明确需求</span></div><p>{matchingNeeds.budget_count} 条需求填写了预算；匹配来自当前社区的类别、关键词与价格条件。</p><div className="matching-need-list">{matchingNeeds.matches.map(entry => <div key={entry.need_id}><strong>{entry.summary}</strong><ul>{entry.reasons.map(reason => <li key={reason}>✓ {reason}</li>)}</ul></div>)}</div><Link className="text-link" to="/needs">查看需求池 <ArrowRight size={16} /></Link></section>}
    {item.passport_code && <section className="panel detail-passport"><div><BookOpen size={25} /><span><strong>物品流转护照 · {item.passport_code}</strong><small>查看这件物品在社区里的发布与交接记录</small></span></div><div><Link className="btn btn-outline" to={`/passport/${item.passport_code}`}>查看护照 <ArrowRight size={16} /></Link>{item.viewer_can_relist && <Link className="btn btn-primary" to={`/publish?relist=${item.id}`}><Repeat2 size={16} /> 再次发布</Link>}</div></section>}
    {mine && <ItemTimeline data={timeline} status={item.status} />}
    {item.my_reservation && <section className="panel my-reservation-panel"><div className="panel-heading"><ShieldCheck size={21} /><h2>我的预约</h2></div><div className="my-reservation-content"><div><strong>{item.my_reservation.status === 'PENDING' ? '等待发布者确认' : '预约已确认'}</strong><p>{slotLabel(item.my_reservation.slot)} · {item.visible_location}</p>{item.my_reservation.pickup_code && <div className="pickup-code"><span>领取码</span><strong>{item.my_reservation.pickup_code}</strong><small>见面后将领取码告诉发布者</small></div>}</div><div className="reservation-private-actions"><button className="btn btn-outline" onClick={() => openChat(item.owner.id)}><MessageCircle size={16} /> 私聊发布者</button><button className="btn btn-outline" disabled={busy} onClick={() => action(`/api/reservations/${item.my_reservation?.id}/cancel`, { method: 'POST' }, '预约已取消')}>取消预约</button></div></div></section>}
    {mine && !ended && <section className="panel interest-panel"><div className="panel-heading"><Users size={21} /><h2>预约申请</h2><span className="panel-count">{item.reservations?.length ?? 0}</span></div>{item.reservations?.length ? <div className="reservation-list">{item.reservations.map(reservation => <div className="reservation-person" key={reservation.id}><Avatar user={reservation.buyer} /><div className="reservation-person-info"><strong>{reservation.buyer.display_name}</strong><span>{slotLabel(reservation.slot)} · {item.handover_location}</span><small>{reservation.status === 'PENDING' ? '等待你确认' : '已确认，等待见面交接'}</small></div><div className="reservation-controls">{reservation.status === 'PENDING' ? <><button className="btn btn-primary" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/confirm`, { method: 'POST' }, '预约已接受，领取码已发给邻居')}>接受预约</button><button className="btn btn-outline" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/reject`, { method: 'POST' }, '已拒绝这次预约')}>拒绝</button></> : <><input aria-label={`输入${reservation.buyer.display_name}的领取码`} inputMode="numeric" maxLength={4} placeholder="输入领取码" value={pickupCodes[reservation.id] || ''} onChange={e => setPickupCodes(prev => ({ ...prev, [reservation.id]: e.target.value.replace(/\D/g, '') }))} /><button className="btn btn-primary" disabled={busy || (pickupCodes[reservation.id] || '').length !== 4} onClick={() => complete(reservation.id)}>确认交接</button><button className="btn btn-outline" disabled={busy} onClick={() => action(`/api/reservations/${reservation.id}/cancel`, { method: 'POST' }, '预约已取消')}>取消</button></>}</div><button className="btn btn-outline mobile-booking-chat" onClick={() => openChat(reservation.buyer.id)}><MessageCircle size={15} /> 去私聊处理</button></div>)}</div> : <p className="muted">还没有邻居预约这件物品。</p>}{item.status !== 'RESERVED' && <button className="text-link archive-link" disabled={busy} onClick={() => action(`/api/items/${item.id}/archive`, { method: 'POST' }, '物品已归档')}>已经处理掉了，归档物品 <ArrowRight size={15} /></button>}</section>}
    {item.my_reservation?.status === 'CONFIRMED' && <BuyerHandoverProgress reservation={item.my_reservation} busy={busy} onAction={action} />}
    {mine && item.status === 'RESERVED' && <SellerHandoverProgress item={item} busy={busy} onAction={action} />}
    {mine && <section className="panel interested-neighbors" id="interested-neighbors"><div className="panel-heading"><Heart size={21} /><h2>想要与咨询的邻居</h2><span className="panel-count">{item.interested_users?.length || 0} 人想要</span></div>{conversations.length ? <div className="interested-neighbor-list">{conversations.map(entry => <div key={entry.user.id}><Avatar user={entry.user} size="small" /><div><strong>{entry.user.display_name}</strong><small>{item.interested_users?.some(person => person.id === entry.user.id) ? '已表达想要' : '咨询过这件物品'}{entry.last_message ? ` · 最近消息：${entry.last_message.body}` : ''}</small></div><button className="btn btn-outline" onClick={() => openChat(entry.user.id)}><MessageCircle size={15} /> 私聊</button></div>)}</div> : <p className="muted">还没有邻居表达意向或咨询。</p>}</section>}
    <section className="panel comments-panel"><div className="panel-heading"><MessageCircle size={21} /><h2>邻里留言</h2><span className="panel-count">{item.comments?.length ?? 0}</span></div><div className="comment-list">{item.comments?.length ? item.comments.map(c => <div className="comment" key={c.id}><Avatar user={c.user} size="small" /><div><div className="comment-head"><strong>{c.user.display_name}</strong><span>{timeAgo(c.created_at)}</span></div><p>{c.body}</p></div></div>) : <p className="muted">还没有留言。</p>}</div>{!ended && (isAuthenticated ? <form className="comment-form" onSubmit={async e => { e.preventDefault(); if (!comment.trim()) return; const result = await action(`/api/items/${item.id}/comments`, { method: 'POST', body: jsonBody({ body: comment.trim() }) }, '留言已发布'); if (result) setComment('') }}><input value={comment} onChange={e => setComment(e.target.value)} placeholder="公开问问物品情况…" aria-label="留言内容" /><button disabled={busy || !comment.trim()} aria-label="发送留言"><Send size={19} /></button></form> : <button className="btn btn-outline" onClick={() => requestAuth(`/item/${itemId}`)}>登录后公开留言</button>)}</section>
    {bookingModalOpen && <div className="modal-backdrop" role="presentation"><form className="community-modal booking-modal" onSubmit={book}><div className="modal-title"><div><span className="eyebrow">私密预约 · 一对一交接</span><h2>预约领取</h2></div><button type="button" aria-label="关闭预约" onClick={() => { setBookingOpen(false); if (searchParams.has('reserve')) setSearchParams({}) }}><X size={18} /></button></div><p>大致位置：<strong>{item.public_location}</strong></p><p className="muted">发布者确认预约后，双方可见具体公共交接点。</p><div className="booking-slots">{item.handover_slots?.map(slot => <label key={slot.id} className={slotId === slot.id ? 'selected' : ''}><input type="radio" name="pickup-time" checked={slotId === slot.id} onChange={() => setSlotId(slot.id)} />{slotLabel(slot)}</label>)}</div><button className="btn btn-primary btn-wide" disabled={busy || !slotId} type="submit">{busy ? '提交中…' : '发送预约申请'}</button></form></div>}
    {finishedHours !== null && <div className="completion-overlay" role="status"><motion.div initial={{ opacity: 0, y: 18, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ duration: 0.4, ease: 'easeOut' }}><motion.span initial={{ scale: 0.7 }} animate={{ scale: 1 }} transition={{ delay: 0.15, duration: 0.3 }}><Check size={38} /></motion.span><motion.h2 initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}>又一件闲置找到了新主人</motion.h2><p>{item.title}</p><small>流转耗时：{finishedHours < 1 ? `${Math.max(1, Math.round(finishedHours * 60))} 分钟` : `${finishedHours} 小时`}</small><p className="completion-thanks">感谢你让它继续发挥价值。</p><button className="btn btn-outline" onClick={() => setFinishedHours(null)}>查看流转记录 <ArrowRight size={16} /></button></motion.div></div>}
  </div>
}
