import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Building2, Check, Leaf, MapPin, Plus, Search, Users, X } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import type { Community } from '../types'
import { Empty, Loading } from '../ui'

const kindNames: Record<Community['kind'], string> = {
  NEIGHBORHOOD: '小区', BUILDING: '楼栋', OFFICE: '办公室',
}

export function CommunityPage() {
  const { userId, communityId, setCommunityId, notify, isAuthenticated, requestAuth, authUser, refreshSession, setCurrentLocation } = useApp()
  const navigate = useNavigate()
  const [communities, setCommunities] = useState<Community[] | null>(null)
  const [query, setQuery] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [joinTarget, setJoinTarget] = useState<Community | null>(null)
  const [joinCode, setJoinCode] = useState('')
  const [joinBuilding, setJoinBuilding] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [form, setForm] = useState({ name: '', kind: 'NEIGHBORHOOD' as Community['kind'], city: '', district: '', locations: '', is_public: false })
  const [coordinates, setCoordinates] = useState<{ latitude: number; longitude: number } | null>(null)
  useEffect(() => { api<Community[]>('/api/communities', userId).then(setCommunities).catch(e => setError(e.message)) }, [userId])

  const selectCommunity = async (community: Community) => {
    try {
      if (authUser && community.joined) {
        await api('/api/me/community', userId, { method: 'PATCH', body: jsonBody({ community_id: community.id, building_id: community.member_building_id }) })
        await refreshSession()
      }
      setCommunityId(community.id); navigate('/')
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const create = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const locations = form.locations.split(/[，,、\n]+/).map(value => value.trim()).filter(Boolean)
      const created = await api<Community>('/api/communities', userId, { method: 'POST', body: jsonBody({ name: form.name.trim(), kind: form.kind, city: form.city.trim(), district: form.district.trim(), location_names: locations, is_public: form.is_public, ...(coordinates || {}) }) })
      notify(`已创建 ${created.name}，加入码可在社区选择页查看`)
      await selectCommunity(created)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const join = async (event: React.FormEvent) => {
    event.preventDefault(); if (!joinTarget) return
    setBusy(true); setError('')
    try {
      const joined = await api<Community>(`/api/communities/${joinTarget.id}/join`, userId, { method: 'POST', body: jsonBody({ join_code: joinCode.trim(), building_id: joinBuilding }) })
      notify(`已加入 ${joined.name}`)
      await selectCommunity(joined)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  const visible = communities?.filter(community => `${community.name} ${community.city} ${community.district}`.toLowerCase().includes(query.trim().toLowerCase()))
  const joined = visible?.filter(community => community.joined) || []
  const discover = visible?.filter(community => !community.joined) || []
  return <div className="container page community-page">
    <div className="page-intro"><div><span className="eyebrow"><MapPin size={16} /> 你身边的分享空间</span><h1>选择社区</h1><p>加入所在的小区、楼栋或办公室，在同一空间里发现和发布闲置。</p></div><button className="btn btn-primary" onClick={() => { if (!isAuthenticated) { requestAuth('/communities'); return }; setShowCreate(true); setJoinTarget(null); setError('') }}><Plus size={17} /> 创建社区</button></div>
    <div className="community-search"><Search size={19} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索社区名称或城市" aria-label="搜索社区" /></div>
    <p className="community-location-note">可手动查找社区；创建者也可以自愿标记社区位置，方便附近邻居定位发现。</p>
    {error && <div className="inline-error">{error}</div>}
    {!communities ? <Loading /> : <>
      <section className="community-section"><h2>我加入的社区 <span>{joined.length}</span></h2>{joined.length ? <div className="community-grid">{joined.map(community => <div className="community-card" key={community.id}><div className="community-card-top"><span className="community-kind"><Building2 size={15} /> {kindNames[community.kind]}</span>{community.id === communityId && <span className="current-community"><Check size={13} /> 当前社区</span>}</div><h3>{community.name}</h3><p><MapPin size={15} /> {community.city}{community.district ? ` · ${community.district}` : ''}</p><p><Users size={15} /> {community.buildings.length} 个楼栋或区域</p><div className="community-card-bottom"><span>加入码：<strong>{community.join_code}</strong></span><button className="btn btn-outline" onClick={() => selectCommunity(community)}>{community.id === communityId ? '进入社区' : '切换到这里'} <ArrowRight size={15} /></button></div></div>)}</div> : <Empty title="还没有加入社区" detail="搜索社区并输入加入码，或创建一个新的社区。" />}</section>
      <section className="community-section"><h2>发现其他社区</h2>{discover.length ? <div className="community-grid">{discover.map(community => <div className="community-card" key={community.id}><div className="community-card-top"><span className="community-kind"><Building2 size={15} /> {kindNames[community.kind]}</span></div><h3>{community.name}</h3><p><MapPin size={15} /> {community.city}{community.district ? ` · ${community.district}` : ''}</p><p><Users size={15} /> {community.buildings.length} 个楼栋或区域</p><div className="community-card-bottom">{community.is_public ? <button className="text-link" onClick={() => selectCommunity(community)}>先浏览</button> : <span>加入后可浏览</span>}<button className="btn btn-outline" onClick={() => { if (!isAuthenticated) { requestAuth('/communities'); return }; setJoinTarget(community); setJoinBuilding(community.buildings[0]?.id || 0); setShowCreate(false); setError('') }}>{community.is_public ? '加入社区' : '输入加入码'} <ArrowRight size={15} /></button></div></div>)}</div> : <p className="muted">没有找到其他社区。</p>}</section>
    </>}
    {showCreate && <div className="modal-backdrop" role="presentation"><form className="community-modal" onSubmit={create}><div className="modal-title"><div><span className="eyebrow"><Leaf size={16} /> 邻里分享从这里开始</span><h2>创建社区</h2></div><button type="button" aria-label="关闭创建社区" onClick={() => setShowCreate(false)}><X size={18} /></button></div><label>社区名称 <b>*</b><input required minLength={2} maxLength={50} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="例如：绿荫花园、A座邻里圈" /></label><label>社区类型 <select value={form.kind} onChange={e => setForm({ ...form, kind: e.target.value as Community['kind'] })}><option value="NEIGHBORHOOD">小区</option><option value="BUILDING">楼栋</option><option value="OFFICE">办公室</option></select></label><div className="form-two"><label>城市 <b>*</b><input required minLength={2} value={form.city} onChange={e => setForm({ ...form, city: e.target.value })} placeholder="城市名称" /></label><label>区域（选填）<input value={form.district} onChange={e => setForm({ ...form, district: e.target.value })} placeholder="区或片区" /></label></div><label>楼栋或区域 <b>*</b><textarea required value={form.locations} onChange={e => setForm({ ...form, locations: e.target.value })} placeholder={form.kind === 'OFFICE' ? '例如：三楼、四楼、A区' : '例如：1号楼、2号楼、3号楼'} rows={2} /><small>用逗号分隔，最多 8 个。创建后会生成加入码。</small></label><label className="community-public-choice"><input type="checkbox" checked={form.is_public} onChange={e => setForm({ ...form, is_public: e.target.checked })} /> 允许附近邻居公开浏览并加入</label><button className="text-link" type="button" onClick={() => navigator.geolocation?.getCurrentPosition(position => { setCoordinates({ latitude: position.coords.latitude, longitude: position.coords.longitude }); setCurrentLocation({ latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy }) }, () => setError('未获得定位权限，仍可创建社区。'))}><MapPin size={16} /> {coordinates ? '已标记社区位置' : '可选：使用当前位置标记社区'}</button><button className="btn btn-primary btn-wide" disabled={busy} type="submit">{busy ? '创建中…' : '创建并进入社区'}</button></form></div>}
    {joinTarget && <div className="modal-backdrop" role="presentation"><form className="community-modal" onSubmit={join}><div className="modal-title"><div><span className="eyebrow">加入社区</span><h2>{joinTarget.name}</h2></div><button type="button" aria-label="关闭加入社区" onClick={() => setJoinTarget(null)}><X size={18} /></button></div><p>{joinTarget.is_public ? '选择你所在的楼栋或区域。' : '向创建者获取加入码，再选择楼栋或区域。'}</p>{!joinTarget.is_public && <label>加入码 <b>*</b><input required minLength={4} value={joinCode} onChange={e => setJoinCode(e.target.value.toUpperCase())} placeholder="输入 8 位加入码" /></label>}<label>所在楼栋或区域<select value={joinBuilding} onChange={e => setJoinBuilding(Number(e.target.value))}>{joinTarget.buildings.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label><button className="btn btn-primary btn-wide" disabled={busy} type="submit">{busy ? '加入中…' : '加入并进入社区'}</button></form></div>}
  </div>
}


