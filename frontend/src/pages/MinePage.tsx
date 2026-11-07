import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Clock3, Leaf, MapPin, Package, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { priceLabel, slotLabel, statusLabel, timeAgo } from '../format'
import type { Item, MyReservation, MySummary } from '../types'
import { Avatar, Empty, Loading, ProductImage } from '../ui'

type ItemTab = 'AVAILABLE' | 'RESERVED' | 'COMPLETED' | 'UNCONFIRMED'
const tabs: { key: ItemTab; label: string }[] = [
  { key: 'AVAILABLE', label: '在架' }, { key: 'RESERVED', label: '已预约' },
  { key: 'UNCONFIRMED', label: '待确认' }, { key: 'COMPLETED', label: '已结束' },
]

function firstUsefulTab(items: Item[]): ItemTab {
  if (items.some(item => item.status === 'AVAILABLE')) return 'AVAILABLE'
  if (items.some(item => item.status === 'RESERVED')) return 'RESERVED'
  if (items.some(item => item.status === 'UNCONFIRMED')) return 'UNCONFIRMED'
  return 'COMPLETED'
}

export function MinePage() {
  const { userId, bootstrap, notify, authUser, logout, refreshSession } = useApp()
  const navigate = useNavigate()
  const user = bootstrap.users.find(entry => entry.id === userId) || authUser
  const [items, setItems] = useState<Item[] | null>(null)
  const [summary, setSummary] = useState<MySummary | null>(null)
  const [reservations, setReservations] = useState<MyReservation[]>([])
  const [tab, setTab] = useState<ItemTab>('AVAILABLE')
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const loadMine = useCallback(async () => {
    const [myItems, mySummary, myReservations] = await Promise.all([
      api<Item[]>('/api/my/items', userId),
      api<MySummary>('/api/my/summary', userId),
      api<MyReservation[]>('/api/my/reservations?limit=6', userId),
    ])
    return { myItems, mySummary, myReservations }
  }, [userId])
  const refresh = async () => {
    const data = await loadMine()
    setItems(data.myItems); setSummary(data.mySummary); setReservations(data.myReservations)
  }
  useEffect(() => {
    let active = true
    loadMine().then(data => {
      if (!active) return
      setItems(data.myItems); setSummary(data.mySummary); setReservations(data.myReservations)
      setTab(firstUsefulTab(data.myItems))
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [loadMine])

  const act = async (path: string, method: 'POST' | 'PATCH', message: string) => {
    setBusy(true); setError('')
    try { await api(path, userId, { method }); await refresh(); notify(message) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  if (error && !items) return <Empty title="个人中心加载失败" detail={error} />
  if (!items || !summary || !user) return <Loading />

  const groups: Record<ItemTab, Item[]> = {
    AVAILABLE: items.filter(item => item.status === 'AVAILABLE'),
    RESERVED: items.filter(item => item.status === 'RESERVED'),
    UNCONFIRMED: items.filter(item => item.status === 'UNCONFIRMED'),
    COMPLETED: items.filter(item => ['COMPLETED', 'ARCHIVED'].includes(item.status)),
  }
  const visibleItems = showAll ? groups[tab] : groups[tab].slice(0, 4)

  return <div className="container page profile-page">
    <section className="profile-banner"><div><span className="eyebrow"><Leaf size={16} /> {bootstrap.community?.name}</span><h1>个人中心</h1><p>我的闲置、预约和社区记录</p></div><div className="profile-banner-image" aria-hidden="true" /></section>
    {error && <div className="inline-error">{error}</div>}
    <div className="profile-compact-layout">
      <section className="panel profile-identity"><div className="profile-identity-top"><Avatar user={user} size="large" /><div><h2>{user.display_name}</h2><span><MapPin size={13} /> {user.location_name || '社区成员'}</span></div></div><div className="profile-mini-stats"><div><strong>{summary.published_count}</strong><span>已发布</span></div><div><strong>{summary.completed_count}</strong><span>已流转</span></div><div><strong>{summary.received_interests}</strong><span>收到想要</span></div><div><strong>{summary.helped_neighbors}</strong><span>帮助邻居</span></div></div></section>
      <div className="profile-main">
        <section className="panel profile-items-panel"><div className="dashboard-card-head"><div><h2><Package size={22} /> 我的闲置</h2><p>按状态管理发布的物品</p></div></div><div className="profile-tabs">{tabs.map(entry => <button key={entry.key} className={tab === entry.key ? 'selected' : ''} onClick={() => { setTab(entry.key); setShowAll(false) }}>{entry.label} <span>{groups[entry.key].length}</span></button>)}</div>{visibleItems.length ? <div className="profile-item-grid">{visibleItems.map(item => <article className="profile-item-card" key={item.id}><Link to={`/item/${item.id}`} className="profile-item-image"><ProductImage imageKey={item.image_key} /><span className={`mine-status status-${item.status.toLowerCase()}`}>{statusLabel(item)}</span></Link><div className="profile-item-body"><h3>{item.title}</h3><strong className={`price notranslate ${item.trade_type === 'FIXED_PRICE' ? 'priced' : ''}`} translate="no">{priceLabel(item)}</strong><p><MapPin size={13} /> {item.building_name} · {timeAgo(item.created_at)}</p><div className="profile-item-actions"><Link className="btn btn-outline" to={`/item/${item.id}`}>查看详情</Link>{['AVAILABLE', 'UNCONFIRMED'].includes(item.status) && <button className="btn btn-primary" disabled={busy} onClick={() => act(`/api/items/${item.id}/confirm-active`, 'PATCH', '已确认在架')}>确认还在</button>}</div>{item.status === 'UNCONFIRMED' && <button className="profile-archive" disabled={busy} onClick={() => act(`/api/items/${item.id}/archive`, 'POST', '物品已归档')}>已经处理掉了</button>}</div></article>)}</div> : <Empty title="这一栏暂时没有物品" detail="可以切换其他状态查看。" />}{groups[tab].length > 4 && <button className="profile-show-more" onClick={() => setShowAll(!showAll)}>{showAll ? '收起' : `查看全部 ${groups[tab].length} 件`} <ArrowRight size={15} /></button>}</section>
        {reservations.length > 0 && <section className="panel profile-reservations" id="my-reservations"><div className="dashboard-card-head"><div><h2><Clock3 size={22} /> 待处理预约</h2><p>交接操作在双方私聊中进行</p></div><Link className="text-link" to="/messages?tab=reservations">查看全部 <ArrowRight size={15} /></Link></div>{reservations.slice(0, 2).map(reservation => <Link className="profile-reservation-summary" to={`/messages?item=${reservation.item_id}&other=${reservation.item.owner.id}`} key={reservation.id}><ProductImage imageKey={reservation.item.image_key} /><span><strong>{reservation.item.title}</strong><small>{reservation.overdue ? '已过预约时间' : reservation.status === 'CONFIRMED' ? '已确认' : '待发布者确认'} · {slotLabel(reservation.slot)}</small></span><ArrowRight size={16} /></Link>)}</section>}
      </div>
      <details className="panel profile-account profile-account-collapsed"><summary><ShieldCheck size={19} /><strong>账号与设置</strong><ArrowRight size={16} /></summary><p>{authUser?.email || '当前使用演示账号'}</p><div className="profile-account-links"><Link to="/settings/preferences">兴趣与交易偏好 <ArrowRight size={15} /></Link><Link to="/communities">我的社区 <ArrowRight size={15} /></Link>{authUser && <button onClick={async () => { await api('/api/me/product-tour/reset', userId, { method: 'POST' }); await refreshSession(); navigate('/market') }}>重新查看新手引导 <ArrowRight size={15} /></button>}<button onClick={() => { void logout() }}>退出登录 <ArrowRight size={15} /></button></div></details>
    </div>
  </div>
}
