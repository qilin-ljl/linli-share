import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Gift, Leaf, Search, SlidersHorizontal, X } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import type { Item } from '../types'
import { Empty, ItemCard, Loading } from '../ui'
import { CommunityActivityFeed } from '../CommunityActivityFeed'
import { priceLabel } from '../format'
import { ProductImage } from '../ui'
import { ChannelTabs } from '../ChannelTabs'

type AdvancedDraft = { category: string; trade_type: string; building_id: string; condition: string; min_price: string; max_price: string; freshness_hours: string }
const advancedKeys: (keyof AdvancedDraft)[] = ['category', 'trade_type', 'building_id', 'condition', 'min_price', 'max_price', 'freshness_hours']
const conditions = ['全新未使用', '九成新', '八成新', '七成新', '长势良好', '有使用痕迹']
const sortNames: Record<string, string> = { NEWEST: '最近发布', MOST_WANTED: '最多人想要', PRICE_ASC: '价格从低到高', PRICE_DESC: '价格从高到低' }

export function MarketPage() {
  const { userId, bootstrap } = useApp()
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const [draftQuery, setDraftQuery] = useState(params.get('q') || '')
  const [items, setItems] = useState<Item[] | null>(null)
  const [error, setError] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [advancedError, setAdvancedError] = useState('')
  const [draft, setDraft] = useState<AdvancedDraft>(() => draftFromParams(params))
  const [recommendationMode, setRecommendationMode] = useState<'FOR_YOU' | 'NEW' | 'FREE' | 'NEARBY'>('FOR_YOU')
  const [recommended, setRecommended] = useState<Item[]>([])

  useEffect(() => {
    let active = true
    api<{ items: Item[] }>(`/api/recommendations?mode=${recommendationMode}&limit=18`, userId)
      .then(data => { if (active) setRecommended(data.items) }).catch(() => {})
    return () => { active = false }
  }, [recommendationMode, userId])

  useEffect(() => {
    let cancelled = false
    api<Item[]>(`/api/items?${query}`, userId)
      .then(result => { if (!cancelled) setItems(result) })
      .catch(e => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
  }, [query, userId])

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value); else next.delete(key)
    setParams(next)
  }
  const toggleAdvanced = () => { setDraft(draftFromParams(params)); setAdvancedError(''); setAdvancedOpen(!advancedOpen) }
  const applyAdvanced = () => {
    if (draft.min_price && draft.max_price && Number(draft.min_price) > Number(draft.max_price)) {
      setAdvancedError('最低价格不能高于最高价格'); return
    }
    const next = new URLSearchParams(params)
    for (const key of advancedKeys) { if (draft[key]) next.set(key, draft[key]); else next.delete(key) }
    setParams(next); setAdvancedOpen(false); setAdvancedError('')
  }
  const clearAdvanced = () => { const next = new URLSearchParams(params); advancedKeys.forEach(key => next.delete(key)); setParams(next); setDraft(draftFromParams(next)); setAdvancedOpen(false) }
  const advancedCount = advancedKeys.filter(key => params.get(key)).length
  const sortBy = params.get('sort_by') || 'NEWEST'

  return <div className="container page market-page">
    <ChannelTabs />
    <div className="market-top"><div className="page-intro market-intro"><div><span className="eyebrow"><Leaf size={16} /> 好东西，总会在附近相遇</span><h1>闲置市集</h1><p>按交易方式、楼栋、成色和价格找到合适的物品。</p></div><div className="intro-note">邻里分享 · 就在身边</div></div><div className="mobile-market-activity"><CommunityActivityFeed /></div></div>
    <section className="mobile-recommendations" aria-label="为你推荐"><div className="mobile-quick-filters">{([['FOR_YOU', '为你推荐'], ['NEW', '最新'], ['FREE', '免费送'], ['NEARBY', '同楼栋']] as const).map(([key, label]) => <button className={recommendationMode === key ? 'active' : ''} key={key} onClick={() => setRecommendationMode(key)}>{label}</button>)}</div><div className="mobile-recommend-head"><strong>猜你喜欢</strong><small>滑动看看附近的新发现</small></div><div className="mobile-recommend-rail">{recommended.map(item => <Link className="recommend-card" to={`/item/${item.id}`} key={item.id}><ProductImage imageKey={item.image_key} /><span><strong>{item.title}</strong><b className="notranslate" translate="no">{priceLabel(item)}</b><small>{item.recommendation_reason}</small></span></Link>)}</div></section>
    <form className="market-search" data-tour="market-search" onSubmit={e => { e.preventDefault(); setFilter('q', draftQuery.trim()) }}><Search size={22} /><input value={draftQuery} onChange={e => setDraftQuery(e.target.value)} placeholder="搜索物品名称或描述…" aria-label="搜索物品名称或描述" /><button className="btn btn-primary" type="submit">搜索</button></form>
    <div className="filter-row"><div className="filter-scroll"><button className={`chip ${!params.get('category') && !params.get('trade_type') ? 'active' : ''}`} onClick={() => { const next = new URLSearchParams(params); next.delete('category'); next.delete('trade_type'); setParams(next) }}>全部类别</button><button className={`chip ${params.get('trade_type') === 'FREE' ? 'active' : ''}`} onClick={() => setFilter('trade_type', params.get('trade_type') === 'FREE' ? '' : 'FREE')}><Gift size={16} /> 免费送</button><button className={`chip ${params.get('trade_type') === 'NEGOTIABLE' ? 'active' : ''}`} onClick={() => setFilter('trade_type', params.get('trade_type') === 'NEGOTIABLE' ? '' : 'NEGOTIABLE')}>随便给</button><button className={`chip ${params.get('trade_type') === 'FIXED_PRICE' ? 'active' : ''}`} onClick={() => setFilter('trade_type', params.get('trade_type') === 'FIXED_PRICE' ? '' : 'FIXED_PRICE')}>标价</button><span className="filter-divider" />{bootstrap.categories.map(category => <button key={category} className={`chip ${params.get('category') === category ? 'active' : ''}`} onClick={() => setFilter('category', params.get('category') === category ? '' : category)}>{category}</button>)}</div></div>
    <div className="market-toolbar"><button className={`btn btn-outline advanced-trigger ${advancedCount ? 'has-filter' : ''}`} onClick={toggleAdvanced}><SlidersHorizontal size={17} /> 高级筛选 {advancedCount > 0 && <span>{advancedCount}</span>}</button><label>排序：<select aria-label="市集排序" value={sortBy} onChange={e => setFilter('sort_by', e.target.value === 'NEWEST' ? '' : e.target.value)}>{Object.entries(sortNames).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label></div>
    {advancedOpen && <div className="advanced-panel"><div className="advanced-title"><h2>高级筛选</h2><button aria-label="关闭高级筛选" onClick={() => setAdvancedOpen(false)}><X size={18} /></button></div><div className="advanced-fields"><label>物品类别<select value={draft.category} onChange={e => setDraft({ ...draft, category: e.target.value })}><option value="">全部类别</option>{bootstrap.categories.map(category => <option key={category}>{category}</option>)}</select></label><label>交易方式<select value={draft.trade_type} onChange={e => setDraft({ ...draft, trade_type: e.target.value })}><option value="">全部方式</option><option value="FREE">免费送</option><option value="NEGOTIABLE">随便给</option><option value="FIXED_PRICE">标价</option></select></label><label>所在楼栋<select value={draft.building_id} onChange={e => setDraft({ ...draft, building_id: e.target.value })}><option value="">全部楼栋</option>{bootstrap.buildings.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label><label>成色<select value={draft.condition} onChange={e => setDraft({ ...draft, condition: e.target.value })}><option value="">不限成色</option>{conditions.map(c => <option key={c}>{c}</option>)}</select></label><label>发布时间<select value={draft.freshness_hours} onChange={e => setDraft({ ...draft, freshness_hours: e.target.value })}><option value="">不限时间</option><option value="24">24 小时内</option><option value="72">3 天内</option><option value="168">7 天内</option></select></label><div className="advanced-price"><span>标价区间（元）</span><div><input type="number" min="0" placeholder="最低" value={draft.min_price} onChange={e => setDraft({ ...draft, min_price: e.target.value })} /><span>—</span><input type="number" min="0" placeholder="最高" value={draft.max_price} onChange={e => setDraft({ ...draft, max_price: e.target.value })} /></div><small>填写价格后仅筛选标价物品。</small></div></div>{advancedError && <p className="advanced-error">{advancedError}</p>}<div className="advanced-actions"><button className="text-link" onClick={clearAdvanced}>清空高级条件</button><button className="btn btn-primary" onClick={applyAdvanced}>应用筛选 <ArrowRight size={16} /></button></div></div>}
    <div className="results-line"><strong>{items?.length ?? '…'} 件物品</strong><span>{sortNames[sortBy]}优先</span></div>
    {error ? <Empty title="列表加载失败" detail={error} /> : !items ? <Loading /> : items.length ? <div className="item-grid market-grid">{items.map(item => <ItemCard key={item.id} item={item} />)}</div> : <Empty title="暂时没有符合条件的物品" detail="换个关键词或筛选条件试试。" />}
  </div>
}

function draftFromParams(params: URLSearchParams): AdvancedDraft {
  return { category: params.get('category') || '', trade_type: params.get('trade_type') || '', building_id: params.get('building_id') || '', condition: params.get('condition') || '',
    min_price: params.get('min_price') || '', max_price: params.get('max_price') || '',
    freshness_hours: params.get('freshness_hours') || '' }
}
