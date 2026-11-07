import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, Flame, Leaf, MapPin, X } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from '../api'
import { useApp } from '../context'
import type { Item, MapBuilding, NeedSummary } from '../types'
import { Empty, Loading, ProductImage } from '../ui'
import { StatsPage } from './StatsPage'
import { distanceLabel, freshLabel, priceLabel, slotLabel, statusLabel } from '../format'

const defaultPoints = [{ x: 24, y: 35 }, { x: 50, y: 18 }, { x: 78, y: 34 }]
const markerOffsets: [number, number][] = [[-9, 13], [7, 21], [-7, 32], [9, 36]]

export function MapPage() {
  const { userId, bootstrap, currentLocation } = useApp()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const needMode = params.get('mode') === 'needs'
  const communityId = bootstrap.community?.id
  const [buildings, setBuildings] = useState<MapBuilding[] | null>(null)
  const [needSummary, setNeedSummary] = useState<NeedSummary | null>(null)
  const [trade, setTrade] = useState('')
  const [selected, setSelected] = useState<Item | null>(null)
  const [nearSelected, setNearSelected] = useState(false)

  useEffect(() => {
    let active = true
    const refresh = () => api<{ buildings: MapBuilding[] }>(`/api/community/map${trade ? `?trade_type=${trade}` : ''}`, userId)
      .then(result => {
        if (!active) return
        setBuildings(result.buildings)
        setSelected(previous => previous && result.buildings.some(building => building.items.some(item => item.id === previous.id)) ? previous : null)
      }).catch(() => {})
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [userId, trade, communityId])
  useEffect(() => {
    if (!communityId) return
    let active = true
    const refresh = () => api<NeedSummary>(`/api/communities/${communityId}/need-summary`, userId)
      .then(result => { if (active) setNeedSummary(result) }).catch(() => {})
    refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [communityId, userId])
  useEffect(() => {
    if (!currentLocation || !communityId) return
    let active = true
    api<{ id: number }[]>(`/api/communities/nearby?latitude=${currentLocation.latitude}&longitude=${currentLocation.longitude}`, userId)
      .then(result => { if (active) setNearSelected(result.some(entry => entry.id === communityId)) }).catch(() => {})
    return () => { active = false }
  }, [currentLocation, communityId, userId])

  const chooseMode = (needs: boolean) => { setParams(needs ? { mode: 'needs' } : {}); setSelected(null) }
  const demand = new Map(needSummary?.buildings.map(building => [building.building_id, building]) || [])
  const hasScene = bootstrap.community?.kind !== 'OFFICE' && bootstrap.buildings.some(building => building.map_x !== null)
  const totalItems = buildings?.reduce((sum, building) => sum + building.active_count, 0) ?? 0
  const modeSwitch = <div className="map-mode-switch"><button className={!needMode ? 'active' : ''} onClick={() => chooseMode(false)}>闲置物品</button><button className={needMode ? 'active' : ''} onClick={() => chooseMode(true)}>邻里需求</button></div>

  if (!hasScene) return <><div className="container page generic-map-page"><div className="page-intro"><div><span className="eyebrow"><MapPin size={16} /> {bootstrap.community?.name}</span><h1>社区位置</h1><p>按楼栋或办公区域查看闲置与明确需求。</p></div><Link className="btn btn-outline" to={needMode ? '/needs' : '/market'}>查看全部{needMode ? '需求' : '物品'} <ArrowRight size={17} /></Link></div>{modeSwitch}{!buildings ? <Loading /> : <div className="location-grid">{buildings.map(building => <section className="location-card" key={building.id}><div><h2>{building.name}</h2><strong>{needMode ? `${demand.get(building.id)?.count || 0} 条明确需求` : `${building.active_count} 件正在流转`}</strong></div>{needMode ? <div className="need-map-categories">{demand.get(building.id)?.categories.map(entry => <span key={entry.category}>{entry.category} × {entry.count}</span>)}</div> : building.items.length ? <div className="location-items">{building.items.map(item => <Link key={item.id} to={`/item/${item.id}`}><ProductImage imageKey={item.image_key} /><span>{item.title}</span></Link>)}</div> : <Empty title="这里还没有物品" detail="发布一件闲置，让邻居发现它。" />}<Link className="text-link" to={needMode ? `/needs?building_id=${building.id}` : `/market?building_id=${building.id}`}>查看这个位置 <ArrowRight size={16} /></Link></section>)}</div>}</div><StatsPage embedded /></>

  return <><div className="map-page"><aside className="map-sidebar"><span className="eyebrow">{bootstrap.community?.name}</span><h1>发现地图</h1><p>从熟悉的楼栋出发，看看附近的闲置和明确需求。</p>{modeSwitch}
    {needMode ? <><div className="map-sidebar-block"><h3>邻里正在找</h3>{needSummary?.buildings.map(entry => <div className="sidebar-need" key={entry.building_id}><strong>{entry.name} · {entry.count} 条</strong><small>{entry.categories.map(category => `${category.category} × ${category.count}`).join('，') || '暂无需求'}</small></div>)}</div><Link className="btn btn-outline map-sidebar-link" to="/needs"><Flame size={16} /> 打开邻里需求</Link></> : <><div className="map-sidebar-block"><h3>交易方式</h3>{[['', '全部物品'], ['FREE', '免费送'], ['NEGOTIABLE', '随便给'], ['FIXED_PRICE', '标价转让']].map(([value, label]) => <button key={value} className={`sidebar-choice ${trade === value ? 'selected' : ''}`} onClick={() => { setBuildings(null); setTrade(value); setSelected(null) }}><span className="radio-dot" />{label}</button>)}</div><div className="map-sidebar-block"><h3>楼栋</h3>{buildings?.map(building => <button key={building.id} className="sidebar-building" onClick={() => navigate(`/market?building_id=${building.id}`)}><span><MapPin size={16} /> {building.name}</span><strong>{building.active_count} 件</strong></button>)}</div><div className="map-hint"><Leaf size={20} /><span>点击物品标记查看预览，再进入详情。</span></div><Link className="btn btn-outline map-sidebar-link" to="/market">切换到列表浏览 <ArrowRight size={17} /></Link></>}
  </aside><div className="map-main"><div className="map-topbar"><span><span className="scene-dot" /> {bootstrap.community?.name}</span><strong><AnimatePresence mode="wait"><motion.b key={needMode ? needSummary?.total : totalItems} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }} transition={{ duration: .2 }}>{needMode ? needSummary?.total ?? '…' : totalItems}</motion.b></AnimatePresence> {needMode ? '条明确需求' : '件符合条件'}</strong></div>
    <div className="map-canvas"><img src="/images/community-map.png" alt="当前社区楼栋与中央广场的数字示意图" />{nearSelected && <span className="map-you-here" style={{ left: '50%', top: '56%' }}><i /> 你在附近（大致位置）</span>}
      {buildings?.map((building, buildingIndex) => {
        const point = { x: building.map_x ?? defaultPoints[buildingIndex % 3].x,
          y: building.map_y ?? defaultPoints[buildingIndex % 3].y }
        const need = demand.get(building.id)
        return <div key={building.id}>{needMode ? <button className={`need-heat-badge ${need?.count ? 'has-needs' : ''}`} style={{ left: `${point.x}%`, top: `${point.y}%`, width: Math.min(104, 62 + (need?.count || 0) * 8), height: Math.min(104, 62 + (need?.count || 0) * 8) }} onClick={() => navigate(`/needs?building_id=${building.id}`)}><strong>{building.name}</strong><b>{need?.count || 0} 条需求</b><small>{need?.categories.map(entry => `${entry.category} × ${entry.count}`).join('、') || '暂无需求'}</small></button> : <><button className="building-badge" style={{ left: `${point.x}%`, top: `${point.y}%` }} onClick={() => navigate(`/market?building_id=${building.id}`)}><strong>{building.name}</strong><AnimatePresence mode="wait"><motion.small key={building.active_count} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: .2 }}>{building.active_count} 件在流转</motion.small></AnimatePresence></button><AnimatePresence initial={false}>{building.items.map((item, index) => <span key={item.id} className={`map-marker-anchor status-${item.status.toLowerCase()} ${Date.now() - new Date(item.created_at).getTime() < 86400000 ? 'is-new' : ''}`} style={{ left: `${point.x + markerOffsets[index][0]}%`, top: `${point.y + markerOffsets[index][1]}%` }}><motion.button className={`map-marker ${selected?.id === item.id ? 'selected' : ''}`} initial={{ opacity: 0, scale: 0 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.18 }} whileHover={{ scale: 1.09 }} transition={{ duration: .32, ease: 'easeOut' }} onClick={() => setSelected(item)} aria-label={`查看${item.title}，${statusLabel(item)}`} title={`${item.title} · ${statusLabel(item)}`}><ProductImage imageKey={item.image_key} /></motion.button></span>)}</AnimatePresence></>}</div>
      })}
      {!needMode && selected && <div className="map-preview"><button className="preview-close" onClick={() => setSelected(null)} aria-label="关闭预览"><X size={18} /></button><ProductImage imageKey={selected.image_key} /><div><span className="eyebrow">{selected.building_name} · {selected.status === 'AVAILABLE' ? freshLabel(selected.created_at) : statusLabel(selected)}</span><h3>{selected.title}</h3><strong className="price notranslate" translate="no">{priceLabel(selected)}</strong><p>{distanceLabel(selected.distance_meters) || '社区内自提'} · {selected.status === 'RESERVED' ? `已预约${selected.scheduled_handover_at ? `，预计${slotLabel({ starts_at: selected.scheduled_handover_at, ends_at: selected.scheduled_handover_at }).split('–')[0]}交接` : ''}` : selected.status === 'UNCONFIRMED' ? '等待发布者确认是否还在' : selected.description}</p><Link className="btn btn-primary" to={`/item/${selected.id}`}>查看详情 <ArrowRight size={17} /></Link></div></div>}
    </div></div></div><StatsPage embedded /></>
}
