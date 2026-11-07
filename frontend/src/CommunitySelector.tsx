import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapPin, Search, X } from 'lucide-react'
import { api, jsonBody } from './api'
import { useApp } from './context'
import type { Community } from './types'

type Match = { matched: boolean; community_id?: number; community_name?: string; distance_meters?: number }
const RECENT_KEY = 'neighloop-recent-community-ids'

export function CommunitySelector({ onClose }: { onClose: () => void }) {
  const { userId, bootstrap, communityId, setCommunityId, currentLocation, setCurrentLocation } = useApp()
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')
  const [communities, setCommunities] = useState<Community[]>([])
  const [nearby, setNearby] = useState<(Community & { distance_m: number })[]>([])
  const [match, setMatch] = useState<Match | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api<Community[]>(`/api/communities?keyword=${encodeURIComponent(keyword)}`, userId)
      .then(data => { if (active) setCommunities(data) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [keyword, userId])
  useEffect(() => {
    if (!currentLocation) return
    api<(Community & { distance_m: number })[]>(`/api/communities/nearby?latitude=${currentLocation.latitude}&longitude=${currentLocation.longitude}`, userId)
      .then(setNearby).catch(() => {})
  }, [currentLocation, userId])

  const locate = () => {
    if (!navigator.geolocation) { setError('浏览器不支持定位，请手动搜索社区。'); return }
    setBusy(true); setError('')
    navigator.geolocation.getCurrentPosition(async position => {
      const location = { latitude: position.coords.latitude, longitude: position.coords.longitude,
        accuracy: position.coords.accuracy }
      setCurrentLocation(location)
      try {
        const result = await api<Match>('/api/location/resolve-community', userId,
          { method: 'POST', body: jsonBody(location) })
        setMatch(result)
        if (!result.matched) setError('附近暂时没有加入 NeighLoop 的社区，请手动选择。')
      } catch (e) { setError((e as Error).message) }
      finally { setBusy(false) }
    }, () => { setBusy(false); setError('未获得位置权限，可以手动选择社区。') },
    { enableHighAccuracy: false, timeout: 10000 })
  }
  const choose = (community: Community) => {
    if (!community.is_public && !community.joined) { onClose(); navigate('/communities'); return }
    let recent: number[] = []
    try { recent = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') as number[] } catch { /* reset corrupt history */ }
    localStorage.setItem(RECENT_KEY, JSON.stringify([community.id, ...recent.filter(id => id !== community.id)].slice(0, 5)))
    setCommunityId(community.id)
    onClose()
    navigate('/')
  }
  let recentIds: number[] = []
  try { recentIds = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') as number[] } catch { /* ignore old local data */ }
  const recent = recentIds.map(id => communities.find(community => community.id === id)).filter((entry): entry is Community => Boolean(entry))
  const matchedCommunity = match?.matched ? communities.find(community => community.id === match.community_id) : null

  return <div className="modal-backdrop selector-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><section className="community-selector" role="dialog" aria-modal="true" aria-label="选择社区"><div className="selector-head"><div><span className="eyebrow"><MapPin size={16} /> 找到你附近的 NeighLoop</span><h2>选择社区</h2></div><button aria-label="关闭社区选择" onClick={onClose}><X size={19} /></button></div>
    <div className="selector-actions"><button className="btn btn-outline" disabled={busy} onClick={locate}><MapPin size={17} /> {busy ? '正在定位…' : '使用当前位置'}</button><span>或手动选择社区</span></div>
    {error && <p className="inline-error">{error}</p>}
    {matchedCommunity && <div className="selector-match"><strong>找到附近社区：{matchedCommunity.name}</strong><small>距你约 {match?.distance_meters} m</small><button className="btn btn-primary" onClick={() => choose(matchedCommunity)}>选择这个社区</button></div>}
    <label className="selector-search"><Search size={18} /><input value={keyword} onChange={event => setKeyword(event.target.value)} placeholder="搜索社区名称、城市或区域" /></label>
    {recent.length > 0 && <div className="selector-section"><h3>最近访问</h3>{recent.map(community => <button key={community.id} onClick={() => choose(community)}>{community.name}</button>)}</div>}
    {nearby.length > 0 && <div className="selector-section"><h3>附近社区</h3>{nearby.map(community => <button key={community.id} onClick={() => choose(community)}>{community.name}<small>约 {community.distance_m} m</small></button>)}</div>}
    <div className="selector-section"><h3>全部搜索结果</h3>{communities.length ? communities.map(community => <button key={community.id} className={community.id === communityId ? 'selected' : ''} onClick={() => choose(community)}>{community.name}<small>{community.city}{community.district ? ` · ${community.district}` : ''}{community.is_public ? '' : ' · 需加入码'}</small></button>) : <p>暂时没有匹配的社区。</p>}</div>
    <button className="text-link" onClick={() => { onClose(); navigate('/communities') }}>查看社区列表与创建社区</button>
    <p className="selector-note">当前位置只在本次浏览中用于计算大致距离，不会公开精确坐标。当前浏览：{bootstrap.community?.name || '未选择'}</p>
  </section></div>
}
