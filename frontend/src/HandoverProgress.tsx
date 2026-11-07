import { Clock3, MapPin, MessageCircle, Navigation, TimerReset } from 'lucide-react'
import { Link } from 'react-router-dom'
import { jsonBody } from './api'
import type { Item, Reservation } from './types'

type Action = (path: string, init: RequestInit, message: string) => Promise<unknown>

function progressText(reservation: Reservation) {
  if (reservation.handover_status === 'DEPARTED') return `${reservation.buyer.display_name}正在路上`
  if (reservation.handover_status === 'ARRIVED') {
    const time = reservation.arrived_at ? new Date(reservation.arrived_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''
    return `${reservation.buyer.display_name}已到达 ${time}`
  }
  if (reservation.handover_status === 'DELAYED') return `${reservation.buyer.display_name}预计晚到约${reservation.delay_minutes || 10}分钟`
  return `等待${reservation.buyer.display_name}出发`
}

export function BuyerHandoverProgress({ reservation, busy, onAction }: {
  reservation: Reservation; busy: boolean; onAction: Action
}) {
  if (reservation.status !== 'CONFIRMED') return null
  const update = (status: 'DEPARTED' | 'ARRIVED' | 'DELAYED', message: string) =>
    onAction(`/api/reservations/${reservation.id}/handover-status`, { method: 'POST', body: jsonBody({ status }) }, message)
  return <section className="panel handover-progress-panel">
    <div className="panel-heading"><Navigation size={21} /><h2>交接进度</h2></div>
    <p className="handover-progress-state"><span className={`progress-dot progress-${reservation.handover_status.toLowerCase()}`} />{reservation.handover_status === 'ARRIVED' ? '已到达交接地点' : reservation.handover_status === 'DELAYED' ? '已告知发布者预计晚到10分钟' : reservation.handover_status === 'DEPARTED' ? '你正在前往交接地点' : '准备出发时可以告诉发布者'}</p>
    {reservation.handover_status !== 'ARRIVED' && <div className="handover-quick-actions">
      {reservation.handover_status !== 'DEPARTED' && <button className="btn btn-outline" disabled={busy} onClick={() => update('DEPARTED', '已告知发布者你出发了')}><Navigation size={16} /> 我出发了</button>}
      <button className="btn btn-primary" disabled={busy} onClick={() => update('ARRIVED', '已告知发布者你到了')}><MapPin size={16} /> 我到了</button>
      {reservation.handover_status !== 'DELAYED' && <button className="btn btn-outline" disabled={busy} onClick={() => update('DELAYED', '已告知发布者你预计晚到10分钟')}><TimerReset size={16} /> 晚到10分钟</button>}
    </div>}
    <Link className="text-link" to={`/messages?item=${reservation.item_id}&other=${reservation.seller_id}`}><MessageCircle size={16} /> 私聊发布者确认交接细节</Link>
  </section>
}

export function SellerHandoverProgress({ item, busy, onAction }: { item: Item; busy: boolean; onAction: Action }) {
  const confirmed = item.reservations?.filter(reservation => reservation.status === 'CONFIRMED') || []
  if (!confirmed.length) return null
  return <section className="panel handover-progress-panel">
    <div className="panel-heading"><Clock3 size={21} /><h2>交接进度</h2></div>
    {confirmed.map(reservation => <div key={reservation.id} className="seller-progress-entry"><strong>{progressText(reservation)}</strong>{reservation.arrived_at && <small>到达时间：{new Date(reservation.arrived_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</small>}{reservation.wait_until && !reservation.overdue && <small>已延长等待至 {new Date(reservation.wait_until).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</small>}<Link className="text-link" to={`/messages?item=${reservation.item_id}&other=${reservation.buyer.id}`}><MessageCircle size={15} /> 私聊{reservation.buyer.display_name}</Link>{reservation.overdue && <div className="overdue-prompt"><p>预约时间已经过去 {reservation.minutes_past_slot} 分钟</p><div><button className="btn btn-outline" disabled={busy} onClick={() => onAction(`/api/reservations/${reservation.id}/wait`, { method: 'POST' }, '已决定再等10分钟')}>再等10分钟</button><button className="btn btn-outline" disabled={busy} onClick={() => onAction(`/api/reservations/${reservation.id}/release`, { method: 'POST' }, '预约已释放，物品恢复可预约')}>释放预约</button></div></div>}</div>)}
  </section>
}
