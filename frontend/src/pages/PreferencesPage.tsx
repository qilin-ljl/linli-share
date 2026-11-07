import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Check, Leaf, MapPin } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import { CATEGORY_OPTIONS, GOAL_OPTIONS, TRADE_OPTIONS } from '../preferenceOptions'
import type { UserPreference } from '../types'

export function PreferencesPage() {
  const { userId, authUser, preferences, setPreferences, notify, refreshSession, logout } = useApp()
  const navigate = useNavigate()
  const [draft, setDraft] = useState<UserPreference>(() => preferences || { goals: [], categories: [], trade_preferences: [], use_distance: false })
  const [nickname, setNickname] = useState(authUser?.nickname || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [locationPermission, setLocationPermission] = useState('未知')
  useEffect(() => {
    if (!navigator.permissions) return
    navigator.permissions.query({ name: 'geolocation' }).then(result => setLocationPermission(result.state === 'granted' ? '已允许' : result.state === 'denied' ? '已拒绝' : '待授权')).catch(() => setLocationPermission('浏览器未提供状态'))
  }, [])
  const toggle = (key: 'goals' | 'categories' | 'trade_preferences', value: string, limit: number) => {
    setDraft(current => ({ ...current, [key]: current[key].includes(value) ? current[key].filter(entry => entry !== value)
      : current[key].length < limit ? [...current[key], value] : current[key] }))
  }
  const toggleTrade = (value: string) => setDraft(current => ({ ...current, trade_preferences: value === 'ANY' ? ['ANY']
    : current.trade_preferences.includes(value) ? current.trade_preferences.filter(entry => entry !== value)
      : [...current.trade_preferences.filter(entry => entry !== 'ANY'), value] }))
  const save = async () => {
    setBusy(true); setError('')
    try {
      const updated = await api<UserPreference>('/api/me/preferences', userId, { method: 'PATCH', body: jsonBody(draft) })
      setPreferences(updated)
      if (authUser && nickname.trim() && nickname.trim() !== authUser.nickname) {
        await api('/api/me/profile', userId, { method: 'PATCH', body: jsonBody({ nickname: nickname.trim() }) })
        await refreshSession()
      }
      notify('偏好已保存，首页已按你的选择调整')
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  const replayTour = async () => {
    try { await api('/api/me/product-tour/reset', userId, { method: 'POST' }); await refreshSession(); navigate('/') }
    catch (e) { setError((e as Error).message) }
  }
  const toggleDistance = () => {
    if (draft.use_distance) { setDraft(current => ({ ...current, use_distance: false })); return }
    if (!navigator.geolocation) { setError('当前浏览器不支持定位。'); return }
    navigator.geolocation.getCurrentPosition(() => { setLocationPermission('已允许'); setDraft(current => ({ ...current, use_distance: true })) },
      () => { setLocationPermission('已拒绝'); setError('未获得位置权限，无法开启距离显示。') }, { timeout: 10000 })
  }
  return <div className="container page settings-page"><div className="page-intro"><div><span className="eyebrow"><Leaf size={16} /> 我的 NeighLoop</span><h1>账号与偏好</h1><p>只按你主动选择的内容安排首页，不分析浏览历史。</p></div></div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <section className="panel settings-section"><h2>账号设置</h2><div className="form-two"><label>邮箱<input value={authUser?.email || '演示账号'} disabled /></label><label>昵称<input maxLength={24} value={authUser ? nickname : '演示身份仅供本地展示'} disabled={!authUser} onChange={event => setNickname(event.target.value)} /></label></div></section>
    <section className="panel settings-section"><h2>我的社区</h2><p>{authUser?.community_id ? '可以随时切换社区或所在楼栋。' : '还没有选择社区。'}</p><Link className="text-link" to="/communities">选择社区 <ArrowRight size={16} /></Link></section>
    <section className="panel settings-section"><h2>你最近更需要什么？</h2><p>最多 3 项。</p><div className="onboarding-choice-grid">{GOAL_OPTIONS.map(([key, icon, title, detail]) => <button key={key} className={draft.goals.includes(key) ? 'selected' : ''} onClick={() => toggle('goals', key, 3)}><span>{icon}</span><strong>{title}</strong><small>{detail}</small></button>)}</div></section>
    <section className="panel settings-section"><h2>感兴趣的类别</h2><div className="onboarding-category-grid">{CATEGORY_OPTIONS.map(([key, icon, title]) => <button key={key} className={draft.categories.includes(key) ? 'selected' : ''} onClick={() => toggle('categories', key, 10)}><span>{icon}</span>{title}</button>)}</div></section>
    <section className="panel settings-section"><h2>交易偏好</h2><div className="onboarding-trades">{TRADE_OPTIONS.map(([key, label]) => <button key={key} className={draft.trade_preferences.includes(key) ? 'selected' : ''} onClick={() => toggleTrade(key)}>{draft.trade_preferences.includes(key) && <Check size={16} />} {label}</button>)}</div><button className={`onboarding-distance ${draft.use_distance ? 'selected' : ''}`} onClick={toggleDistance}><MapPin size={19} /> 位置权限：{locationPermission} · {draft.use_distance ? '附近距离已开启' : '附近距离未开启'}</button></section>
    <div className="settings-actions"><button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? '保存中…' : '保存偏好'}</button>{authUser && <button className="btn btn-outline" onClick={() => { void replayTour() }}>重新查看新手引导</button>}<button className="text-link" onClick={() => { void logout() }}>退出登录</button></div>
  </div>
}
