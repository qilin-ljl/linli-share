import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Check, Leaf, MapPin, Search } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import type { Community, Stats, UserPreference } from '../types'

const goals = [
  ['CLEAR', '📦', '清理闲置', '让家里的东西更快找到新主人'],
  ['FIND', '🛍', '淘附近好物', '看看邻居有什么正好用得上'],
  ['GIVE', '🎁', '免费分享', '把不用的东西送给真正需要的人'],
  ['NEED', '🔍', '我在找东西', '浏览邻里需求，也可以发布自己在找的东西'],
  ['MOVE', '🏠', '正在搬家', '一次整理多件闲置，快速处理'],
  ['BROWSE', '🌱', '逛逛社区', '看看附近最近在发生什么'],
] as const
const categoryOptions = [
  ['家居', '🏠', '家居'], ['家电', '🍳', '厨房家电'], ['数码', '💻', '数码'],
  ['图书', '📚', '图书学习'], ['绿植', '🌱', '绿植'], ['运动', '🏸', '运动'],
  ['母婴', '👶', '母婴'], ['衣物', '👕', '衣物'], ['生活用品', '📦', '生活日用'], ['其他', '🎨', '其他'],
] as const
const trades = [['FREE', '免费送'], ['LOW_PRICE', '邻里低价'], ['NEGOTIABLE', '随便给'], ['ANY', '都可以']] as const

export function OnboardingPage() {
  const { userId, authUser, preferences, setCommunityId, refreshSession, bootstrap, setCurrentLocation } = useApp()
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [communities, setCommunities] = useState<Community[]>([])
  const [nearby, setNearby] = useState<(Community & { distance_m: number })[]>([])
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Community | null>(null)
  const [joinedCommunity, setJoinedCommunity] = useState<Community | null>(null)
  const [buildingId, setBuildingId] = useState<number | null>(null)
  const [joinCode, setJoinCode] = useState('')
  const [locationAllowed, setLocationAllowed] = useState(false)
  const [finding, setFinding] = useState(false)
  const [draft, setDraft] = useState<UserPreference>(() => preferences || { goals: [], categories: [], trade_preferences: [], use_distance: false })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [welcome, setWelcome] = useState<{ name: string; active: number | null } | null>(null)

  useEffect(() => { api<Community[]>('/api/communities', userId).then(setCommunities).catch(e => setError(e.message)) }, [userId])
  const visible = communities.filter(community => `${community.name} ${community.city}`.toLowerCase().includes(query.trim().toLowerCase()))
  const choose = (community: Community) => { setSelected(community); setBuildingId(community.member_building_id || null); setError('') }
  const locate = () => {
    if (!navigator.geolocation) { setError('当前浏览器不支持定位，请手动选择社区。'); return }
    setFinding(true); setError('')
    navigator.geolocation.getCurrentPosition(position => {
      setLocationAllowed(true)
      const current = { latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy }
      setCurrentLocation(current)
      api('/api/location/resolve-community', userId, { method: 'POST', body: jsonBody(current) }).catch(() => {})
      api<(Community & { distance_m: number })[]>(`/api/communities/nearby?latitude=${position.coords.latitude}&longitude=${position.coords.longitude}`, userId)
        .then(data => { setNearby(data); if (!data.length) setError('附近暂无已设置位置的社区，请手动搜索。') })
        .catch(e => setError(e.message)).finally(() => setFinding(false))
    }, () => { setFinding(false); setError('未获得位置权限，可继续手动选择社区。') }, { enableHighAccuracy: false, timeout: 10000 })
  }
  const saveCommunity = async () => {
    if (!selected) { setStep(2); return }
    setBusy(true); setError('')
    try {
      await api('/api/me/community', userId, { method: 'PATCH', body: jsonBody({ community_id: selected.id, building_id: buildingId, join_code: joinCode || null }) })
      setJoinedCommunity(selected)
      setCommunityId(selected.id)
      await refreshSession()
      setStep(2)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  const toggle = (key: 'goals' | 'categories' | 'trade_preferences', value: string, limit: number) => {
    setDraft(current => {
      const entries = current[key]
      const next = entries.includes(value) ? entries.filter(entry => entry !== value) : entries.length < limit ? [...entries, value] : entries
      return { ...current, [key]: next }
    })
  }
  const toggleTrade = (value: string) => {
    setDraft(current => ({ ...current, trade_preferences: value === 'ANY' ? ['ANY']
      : current.trade_preferences.includes(value) ? current.trade_preferences.filter(entry => entry !== value)
        : [...current.trade_preferences.filter(entry => entry !== 'ANY'), value] }))
  }
  const toggleDistance = () => {
    if (draft.use_distance) { setDraft(current => ({ ...current, use_distance: false })); return }
    if (locationAllowed) { setDraft(current => ({ ...current, use_distance: true })); return }
    if (!navigator.geolocation) { setError('当前浏览器不支持定位。'); return }
    navigator.geolocation.getCurrentPosition(() => { setLocationAllowed(true); setDraft(current => ({ ...current, use_distance: true })) },
      () => setError('未获得位置权限，之后可在个人中心开启。'), { timeout: 10000 })
  }
  const finish = async () => {
    setBusy(true); setError('')
    try {
      await api('/api/me/preferences', userId, { method: 'PATCH', body: jsonBody(draft) })
      await api('/api/me/onboarding/complete', userId, { method: 'POST' })
      await refreshSession()
      let active: number | null = null
      if (authUser?.community_id || joinedCommunity) {
        try { active = (await api<Stats>('/api/community/stats', userId)).active_count } catch { /* generic welcome */ }
      }
      setWelcome({ name: joinedCommunity?.name || (authUser?.community_id ? bootstrap.community?.name : null) || 'NeighLoop', active })
      window.setTimeout(() => navigate('/market'), 1200)
    } catch (e) { setError((e as Error).message); setBusy(false) }
  }

  return <div className="onboarding-page container page">
    <div className="onboarding-progress"><span className="eyebrow"><Leaf size={17} /> 找到属于你的附近</span><strong>{step} / 4</strong></div>
    <div className="onboarding-track"><i style={{ width: `${step * 25}%` }} /></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {step === 1 && <section className="onboarding-panel panel"><h1>先找到你的社区</h1><p>NeighLoop 从附近开始。</p><div className="onboarding-location-actions"><button className="btn btn-outline" disabled={finding} onClick={locate}><MapPin size={18} /> {finding ? '正在查找…' : '使用当前位置'}</button><span>或手动选择小区</span></div>
      {nearby.length > 0 && <div className="onboarding-communities"><h2>找到附近社区</h2>{nearby.map(community => <button key={community.id} className={selected?.id === community.id ? 'selected' : ''} onClick={() => choose(community)}><strong>{community.name}</strong><small>距你约 {community.distance_m} m</small></button>)}</div>}
      <div className="onboarding-search"><Search size={19} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索社区名称" aria-label="搜索社区名称" /></div><div className="onboarding-communities">{visible.slice(0, 8).map(community => <button key={community.id} className={selected?.id === community.id ? 'selected' : ''} onClick={() => choose(community)}><strong>{community.name}</strong><small>{community.city}{community.district ? ` · ${community.district}` : ''}</small></button>)}</div>
      {selected && <div className="onboarding-building"><strong>{selected.name}</strong><label>所在楼栋（可选）<select value={buildingId ?? ''} onChange={event => setBuildingId(event.target.value ? Number(event.target.value) : null)}><option value="">稍后选择</option>{selected.buildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}</select></label>{!selected.is_public && !selected.joined && <label>社区加入码<input value={joinCode} onChange={event => setJoinCode(event.target.value.toUpperCase())} placeholder="向社区创建者获取" /></label>}</div>}
      <div className="onboarding-actions"><button className="text-link" onClick={() => { setSelected(null); setStep(2) }}>稍后设置</button><button className="btn btn-primary" disabled={busy} onClick={saveCommunity}>{selected ? '加入这个社区' : '下一步'} <ArrowRight size={17} /></button></div></section>}
    {step === 2 && <section className="onboarding-panel panel"><h1>你最近更需要什么？</h1><p>最多选择 3 项，之后可以修改。</p><div className="onboarding-choice-grid">{goals.map(([key, icon, title, detail]) => <button key={key} className={draft.goals.includes(key) ? 'selected' : ''} onClick={() => toggle('goals', key, 3)}><span>{icon}</span><strong>{title}</strong><small>{detail}</small></button>)}</div><div className="onboarding-actions"><button className="text-link" onClick={() => setStep(3)}>稍后设置</button><button className="btn btn-primary" onClick={() => setStep(3)}>下一步 <ArrowRight size={17} /></button></div></section>}
    {step === 3 && <section className="onboarding-panel panel"><h1>你通常会关注哪些东西？</h1><p>只影响闲置市集的推荐顺序，不会隐藏其他物品；随时可以修改。</p><div className="onboarding-category-grid">{categoryOptions.map(([key, icon, title]) => <button key={key} className={draft.categories.includes(key) ? 'selected' : ''} onClick={() => toggle('categories', key, 10)}><span>{icon}</span>{title}</button>)}</div><div className="onboarding-actions"><button className="text-link" onClick={() => setStep(4)}>稍后设置</button><button className="btn btn-primary" onClick={() => setStep(4)}>下一步 <ArrowRight size={17} /></button></div></section>}
    {step === 4 && <section className="onboarding-panel panel"><h1>最后，再告诉我们一点偏好</h1><p>用来调整市集推荐，邻里需求频道仍可独立浏览和筛选。</p><h2>你更喜欢</h2><div className="onboarding-trades">{trades.map(([key, label]) => <button key={key} className={draft.trade_preferences.includes(key) ? 'selected' : ''} onClick={() => toggleTrade(key)}>{draft.trade_preferences.includes(key) && <Check size={16} />} {label}</button>)}</div><button className={`onboarding-distance ${draft.use_distance ? 'selected' : ''}`} onClick={toggleDistance}><MapPin size={19} /> {draft.use_distance ? '已开启附近距离' : '使用当前位置显示距离'}</button><div className="onboarding-actions"><button className="text-link" onClick={finish}>稍后设置</button><button className="btn btn-primary" disabled={busy} onClick={finish}>{busy ? '保存中…' : '进入我的 NeighLoop'} <ArrowRight size={17} /></button></div></section>}
    {welcome && <motion.div className="onboarding-welcome" initial={{ opacity: 0 }} animate={{ opacity: 1 }}><motion.div initial={{ y: 16, scale: .94 }} animate={{ y: 0, scale: 1 }}><span><Check size={32} /></span><p>欢迎来到</p><h2>{welcome.name}</h2><small>{welcome.active === null ? '从闲置市集和邻里需求两个频道开始。' : `这里有 ${welcome.active} 件闲置正在流转`}</small></motion.div></motion.div>}
  </div>
}
