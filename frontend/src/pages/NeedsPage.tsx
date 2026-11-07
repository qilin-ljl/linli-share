import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Flame, MapPin, MessageCircle, Search, SlidersHorizontal, X } from 'lucide-react'
import { api, jsonBody } from '../api'
import { ChannelTabs } from '../ChannelTabs'
import { useApp } from '../context'
import { timeAgo } from '../format'
import type { Item, Need, NeedReply } from '../types'
import { Avatar, Empty, Loading } from '../ui'

function NeedDiscussion({ need }: { need: Need }) {
  const { userId, isAuthenticated, requestAuth } = useApp()
  const [open, setOpen] = useState(false)
  const [replies, setReplies] = useState<NeedReply[]>([])
  const [ownedState, setOwnedState] = useState<{ userId: number; items: Item[]; error: string } | null>(null)
  const [draft, setDraft] = useState('')
  const [itemId, setItemId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const owned = ownedState?.userId === userId ? ownedState : null
  const myItems = owned?.items.filter(item => item.status === 'AVAILABLE') || []
  const ownedCount = owned?.items.length || 0
  const itemsError = owned?.error || ''
  const itemsLoading = open && isAuthenticated && !owned
  const refresh = useCallback(() => api<NeedReply[]>(`/api/needs/${need.id}/replies`, userId).then(setReplies).catch(e => setError(e.message)), [need.id, userId])
  useEffect(() => {
    if (!open) return
    void refresh()
    const timer = window.setInterval(refresh, 8_000)
    return () => window.clearInterval(timer)
  }, [open, refresh])
  useEffect(() => {
    if (!open || !isAuthenticated) return
    let active = true
    api<Item[]>('/api/my/items', userId).then(data => {
      if (active) setOwnedState({ userId, items: data, error: '' })
    }).catch(e => { if (active) setOwnedState({ userId, items: [], error: (e as Error).message }) })
    return () => { active = false }
  }, [open, isAuthenticated, userId])
  const send = async (event: FormEvent) => {
    event.preventDefault()
    if (!isAuthenticated) { requestAuth('/needs'); return }
    setBusy(true); setError('')
    try {
      await api(`/api/needs/${need.id}/replies`, userId, { method: 'POST', body: jsonBody({ body: draft, item_id: itemId ? Number(itemId) : null }) })
      setDraft(''); setItemId(''); await refresh()
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="need-discussion">
    <button type="button" className="need-discussion-trigger" aria-expanded={open} onClick={() => setOpen(!open)}><MessageCircle size={16} /> {open ? '收起讨论' : need.reply_count ? `查看 ${need.reply_count} 条讨论` : '参与讨论'} <ArrowRight size={15} /></button>
    {open && <div className="need-replies">{replies.length ? replies.map(reply => <div key={reply.id}><strong>{reply.user.display_name}</strong><small>{timeAgo(reply.created_at)}</small><p>{reply.body}</p>{reply.item && <Link to={`/item/${reply.item.id}`}>看看我的闲置：{reply.item.title} <ArrowRight size={14} /></Link>}</div>) : <p className="muted">还没有回复，来帮邻居出个主意吧。</p>}
      {need.status === 'ACTIVE' && <form onSubmit={send}><textarea maxLength={500} required value={draft} onChange={event => setDraft(event.target.value)} placeholder="回复邻居的需求…" rows={2} />{myItems.length ? <label>附上我的在架物品（选填）<select aria-label="附上我的在架物品" value={itemId} onChange={event => setItemId(event.target.value)}><option value="">不附物品</option>{myItems.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label> : itemsLoading ? <small className="need-attach-help">正在读取你在架的物品…</small> : isAuthenticated && !itemsError ? <small className="need-attach-help">{ownedCount ? <>当前没有可附的在架物品。到<Link to="/mine">我的闲置</Link>确认还在，或<Link to="/publish">发布新物品</Link>。</> : <>你在当前社区还没有发布物品。<Link to="/publish">先发布闲置物品</Link>后即可附上。</>}</small> : null}{itemsError && <small className="inline-error">物品列表加载失败：{itemsError}</small>}{error && <small className="inline-error">{error}</small>}<button className="btn btn-outline" disabled={busy || !draft.trim()} type="submit">{busy ? '发送中…' : '回复需求'}</button></form>}
    </div>}
  </div>
}

export function NeedsPage() {
  const { userId, bootstrap } = useApp()
  const [params, setParams] = useSearchParams()
  const focusId = Number(params.get('focus'))
  const query = new URLSearchParams(params)
  query.delete('focus')
  const queryString = query.toString()
  const [draftQuery, setDraftQuery] = useState(params.get('q') || '')
  const [result, setResult] = useState<{ query: string; items: Need[] } | null>(null)
  const [loadError, setLoadError] = useState<{ query: string; message: string } | null>(null)
  const needs = result?.query === queryString ? result.items : null
  const error = loadError?.query === queryString ? loadError.message : ''
  const categories = Array.from(new Set([...bootstrap.need_categories,
    ...(needs || []).map(need => need.category).filter((category): category is string => Boolean(category))]))
  const hasFilters = ['q', 'category', 'building_id', 'reply_state', 'budget_only', 'sort_by'].some(key => params.has(key))
  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.delete('focus')
    if (value) next.set(key, value); else next.delete(key)
    setParams(next)
  }
  useEffect(() => {
    let active = true
    api<Need[]>(`/api/needs?${queryString}`, userId)
      .then(data => { if (active) { setResult({ query: queryString, items: data }); setLoadError(null) } })
      .catch(e => { if (active) setLoadError({ query: queryString, message: e.message }) })
    return () => { active = false }
  }, [queryString, userId])
  useEffect(() => {
    if (focusId && needs?.some(need => need.id === focusId)) {
      window.requestAnimationFrame(() => document.getElementById(`need-${focusId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
    }
  }, [focusId, needs])

  return <div className="container page needs-page need-channel-page">
    <ChannelTabs />
    <div className="page-intro need-channel-intro"><div><span className="eyebrow"><Flame size={16} /> {bootstrap.community?.name} · 邻里频道</span><h1>邻里需求</h1><p>看看附近的人在找什么，在讨论里提供线索或分享自己的在架物品。</p></div><Link className="btn btn-outline" to="/map?mode=needs"><MapPin size={16} /> 需求地图</Link></div>
    <form className="need-channel-search" onSubmit={event => { event.preventDefault(); setFilter('q', draftQuery.trim()) }}><Search size={19} /><input value={draftQuery} onChange={event => setDraftQuery(event.target.value)} placeholder="搜索需求、类别或关键词" aria-label="搜索邻里需求" /><button className="btn btn-primary" type="submit">搜索</button></form>
    <div className="need-channel-categories" aria-label="需求类别筛选"><button className={!params.get('category') ? 'active' : ''} onClick={() => setFilter('category', '')}>全部</button>{categories.map(category => <button key={category} className={params.get('category') === category ? 'active' : ''} onClick={() => setFilter('category', params.get('category') === category ? '' : category)}>{category}</button>)}</div>
    <div className="need-channel-toolbar"><span><SlidersHorizontal size={16} /> 筛选</span><label>位置<select aria-label="筛选楼栋" value={params.get('building_id') || ''} onChange={event => setFilter('building_id', event.target.value)}><option value="">全社区</option>{bootstrap.buildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}</select></label><label>回应<select aria-label="筛选回应状态" value={params.get('reply_state') || 'ALL'} onChange={event => setFilter('reply_state', event.target.value === 'ALL' ? '' : event.target.value)}><option value="ALL">全部</option><option value="UNANSWERED">待回应</option><option value="WITH_LISTING">附有物品</option></select></label><label>排序<select aria-label="需求排序" value={params.get('sort_by') || 'NEWEST'} onChange={event => setFilter('sort_by', event.target.value === 'NEWEST' ? '' : event.target.value)}><option value="NEWEST">最新发布</option><option value="MOST_DISCUSSED">讨论最多</option></select></label><label className="need-budget-toggle"><input type="checkbox" checked={params.get('budget_only') === 'true'} onChange={event => setFilter('budget_only', event.target.checked ? 'true' : '')} /> 有预算</label>{hasFilters && <button className="need-clear" onClick={() => { setParams({}); setDraftQuery('') }}><X size={14} /> 清空</button>}</div>
    <div className="need-channel-count"><strong>{needs ? needs.length : '…'} 条需求</strong><span>只显示当前社区的公开内容</span></div>
    {error ? <Empty title="需求加载失败" detail={error} /> : !needs ? <Loading /> : needs.length ? <div className="need-grid">{needs.map(need => <article className={`panel need-card ${need.id === focusId ? 'need-focused' : ''}`} id={`need-${need.id}`} key={need.id}><div className="need-card-head"><Avatar user={need.user} size="small" /><div><strong>{need.user.display_name}</strong><small>{need.building_name} · {timeAgo(need.created_at)}</small></div><span className="need-category">{need.category || '其他需求'}</span></div><p>{need.raw_text}</p>{need.keywords.length > 0 && <div className="need-keywords">{need.keywords.map(word => <span key={word}>{word}</span>)}</div>}<div className="need-card-meta"><span>{need.budget_max === null ? '预算未填写' : `预算不超过 ¥${need.budget_max}`}</span>{need.has_listing_reply && <span>已有物品线索</span>}</div><NeedDiscussion need={need} /></article>)}</div> : <Empty title="没有符合条件的需求" detail="换个关键词或筛选条件，看看其他邻居正在找什么。" />}
  </div>
}
