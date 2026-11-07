import { useCallback, useEffect, useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Check, ChevronDown, House, Leaf, MapPin, MessageCircle, Plus, Search, UserRound, X } from 'lucide-react'
import { api, DEMO_MODE, setApiLocation } from './api'
import type { CurrentLocation } from './api'
import { AppContext, useApp } from './context'
import type { AuthResponse, AuthUser, Bootstrap, UserPreference } from './types'
import { Avatar, Loading } from './ui'
import { AuthDialog } from './AuthDialog'
import { CommunitySelector } from './CommunitySelector'
import { ProductTour } from './ProductTour'
import { EntrySplash } from './EntrySplash'
import { MarketPage } from './pages/MarketPage'
import { MapPage } from './pages/MapPage'
import { DetailPage } from './pages/DetailPage'
import { PublishPage } from './pages/PublishPage'
import { StatsPage } from './pages/StatsPage'
import { MinePage } from './pages/MinePage'
import { CommunityPage } from './pages/CommunityPage'
import { AuthPage } from './pages/AuthPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { PreferencesPage } from './pages/PreferencesPage'
import { PassportPage } from './pages/PassportPage'
import { NeedsPage } from './pages/NeedsPage'
import { PublishNeedPage } from './pages/PublishNeedPage'
import { MessagesPage } from './pages/MessagesPage'

type PublicDemoAccount = { id: number; display_name: string; role: string }

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, requestAuth } = useApp()
  useEffect(() => { if (!isAuthenticated) requestAuth() }, [isAuthenticated, requestAuth])
  return isAuthenticated ? children : <div className="container page auth-required"><h1>登录后继续</h1><p>加入社区后，才能管理自己的闲置与预约。</p></div>
}

export default function App() {
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null)
  const [userId, setUserIdState] = useState(() => DEMO_MODE ? Number(localStorage.getItem('neighloop-demo-user-id')) || 0 : 0)
  const [communityId, setCommunityIdState] = useState(() => Number(localStorage.getItem('neighloop-community-id')) || 1)
  const [authUser, setAuthUser] = useState<AuthUser | null>(null)
  const [publicDemoAccounts, setPublicDemoAccounts] = useState<PublicDemoAccount[]>([])
  const [preferences, setPreferences] = useState<UserPreference | null>(null)
  const [authReady, setAuthReady] = useState(false)
  const [authDialog, setAuthDialog] = useState(false)
  const [communitySelectorOpen, setCommunitySelectorOpen] = useState(false)
  const [mobilePublishOpen, setMobilePublishOpen] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [headerSearch, setHeaderSearch] = useState('')
  const [currentLocation, setLocationState] = useState<CurrentLocation | null>(null)
  const [showEntrySplash, setShowEntrySplash] = useState(true)
  const location = useLocation()
  const navigate = useNavigate()

  useEffect(() => {
    api<AuthResponse>('/api/auth/me', 0).then(result => {
      localStorage.removeItem('neighloop-demo-user-id')
      setAuthUser(result.user); setPreferences(result.preferences); setUserIdState(result.user.id)
      if (result.user.community_id) {
        localStorage.setItem('neighloop-community-id', String(result.user.community_id))
        setCommunityIdState(result.user.community_id)
      }
    }).catch(() => {}).finally(() => setAuthReady(true))
  }, [])
  useEffect(() => {
    if (DEMO_MODE) return
    api<PublicDemoAccount[]>('/api/auth/demo-accounts', 0).then(setPublicDemoAccounts).catch(() => {})
  }, [])
  useEffect(() => {
    if (!authReady) return
    let active = true
    api<Bootstrap>('/api/bootstrap', userId).then(data => {
      if (active) {
        setBootstrap(data)
        if (data.community && data.community.id !== communityId) {
          localStorage.setItem('neighloop-community-id', String(data.community.id))
          setCommunityIdState(data.community.id)
        }
      }
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [authReady, userId, communityId])
  useEffect(() => {
    if (!authReady || authUser || !DEMO_MODE || userId <= 0) return
    api<UserPreference>('/api/me/preferences', userId).then(setPreferences).catch(() => setPreferences(null))
  }, [authReady, authUser, userId])
  useEffect(() => { if (toast) { const id = setTimeout(() => setToast(''), 3800); return () => clearTimeout(id) } }, [toast])
  useEffect(() => {
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 450 : 2600
    const timer = window.setTimeout(() => setShowEntrySplash(false), duration)
    return () => window.clearTimeout(timer)
  }, [])
  useEffect(() => { window.scrollTo(0, 0) }, [location.pathname])
  useEffect(() => {
    if (!authReady || !userId || (!authUser && !DEMO_MODE)) return
    const beat = () => { void api('/api/presence/heartbeat', userId, { method: 'POST' }).catch(() => {}) }
    beat()
    const timer = window.setInterval(beat, 45_000)
    return () => window.clearInterval(timer)
  }, [authReady, authUser, userId])
  useEffect(() => {
    if (authReady && authUser && !authUser.onboarding_completed && location.pathname !== '/onboarding') navigate('/onboarding', { replace: true })
  }, [authReady, authUser, location.pathname, navigate])

  const refreshSession = async () => {
    const result = await api<AuthResponse>('/api/auth/me', 0)
    setAuthUser(result.user); setPreferences(result.preferences); setUserIdState(result.user.id)
    if (result.user.community_id) {
      localStorage.setItem('neighloop-community-id', String(result.user.community_id))
      setCommunityIdState(result.user.community_id)
    }
    const data = await api<Bootstrap>('/api/bootstrap', result.user.id)
    setBootstrap(data)
  }
  const onAuthenticated = (result: AuthResponse) => {
    localStorage.removeItem('neighloop-demo-user-id')
    setAuthUser(result.user); setPreferences(result.preferences); setUserIdState(result.user.id)
    if (result.user.community_id) {
      localStorage.setItem('neighloop-community-id', String(result.user.community_id))
      setCommunityIdState(result.user.community_id)
    }
    setBootstrap(null); setError(''); setAuthDialog(false)
    void api<Bootstrap>('/api/bootstrap', result.user.id).then(setBootstrap).catch(e => setError(e.message))
  }
  const switchPublicDemo = async (id: number) => {
    if (!id) return
    try {
      const result = await api<AuthResponse>('/api/auth/demo-login', userId,
        { method: 'POST', body: JSON.stringify({ user_id: id }) })
      onAuthenticated(result)
      setToast(`已切换到 ${result.user.display_name} 的演示账号`)
      navigate(result.user.onboarding_completed ? '/market' : '/onboarding')
    } catch (e) { setToast((e as Error).message) }
  }
  const logout = async () => {
    if (authUser) {
      try { await api('/api/auth/logout', 0, { method: 'POST' }) }
      catch { setToast('退出失败，请稍后重试'); return }
    }
    localStorage.removeItem('neighloop-demo-user-id')
    setAuthUser(null); setPreferences(null); setUserIdState(0); setBootstrap(null)
    setApiLocation(null); setLocationState(null)
    navigate('/'); setToast('已退出登录')
  }
  const setUserId = async (id: number) => {
    if (authUser) {
      try { await api('/api/auth/logout', 0, { method: 'POST' }) }
      catch { setToast('请先退出账号，再切换演示用户'); return }
    }
    if (id) localStorage.setItem('neighloop-demo-user-id', String(id))
    else localStorage.removeItem('neighloop-demo-user-id')
    setAuthUser(null); setPreferences(null); setUserIdState(id); setBootstrap(null)
    setToast(id ? '已切换演示用户' : '已进入游客模式')
  }
  const setCommunityId = (id: number) => {
    localStorage.setItem('neighloop-community-id', String(id)); setCommunityIdState(id)
  }
  const setCurrentLocation = (value: CurrentLocation | null) => { setApiLocation(value); setLocationState(value) }
  const requestAuth = useCallback((returnTo?: string) => {
    sessionStorage.setItem('neighloop-return-to', returnTo || `${location.pathname}${location.search}`)
    setAuthDialog(true)
  }, [location.pathname, location.search])
  const isAuthenticated = Boolean(authUser || (DEMO_MODE && userId > 0 && Number(localStorage.getItem('neighloop-demo-user-id')) === userId))
  const guardLink = (event: MouseEvent, target: string) => { if (!isAuthenticated) { event.preventDefault(); requestAuth(target) } }

  if (error) return <div className="fatal"><h1>社区暂时无法加载</h1><p>{error}</p><p>请先启动后端并运行数据库初始化。</p></div>
  if (!authReady || !bootstrap) return <><Loading />{showEntrySplash && <EntrySplash />}</>
  const currentBootstrap: Bootstrap = authUser && !bootstrap.users.some(user => user.id === authUser.id)
    ? { ...bootstrap, users: [...bootstrap.users, authUser] } : bootstrap
  const user = currentBootstrap.users.find(entry => entry.id === userId) || authUser

  return <><AppContext.Provider value={{ bootstrap: currentBootstrap, userId, setUserId, communityId, setCommunityId,
    notify: setToast, authUser, preferences, isAuthenticated, demoMode: DEMO_MODE, requestAuth,
    onAuthenticated, refreshSession, setPreferences, logout, currentLocation, setCurrentLocation }}>
    <div className={`site-shell ${location.pathname === '/login' || location.pathname === '/register' ? 'auth-route' : ''}`}>
      <header className="site-header">
        <Link to="/" className="brand"><span className="brand-mark"><Leaf size={25} strokeWidth={2.4} /></span><span><strong>NeighLoop</strong><small>让闲置流动，让社区更温暖</small></span></Link>
        <button className="community-switch" title="选择或创建社区" onClick={() => setCommunitySelectorOpen(true)}><MapPin size={16} /><span>{currentBootstrap.community?.name || '选择社区'}</span><ChevronDown size={14} /></button>
        <nav className="primary-nav" aria-label="主导航"><NavLink end to="/">首页</NavLink><NavLink to="/map">发现地图</NavLink><NavLink to="/market">闲置市集</NavLink><NavLink to="/needs">邻里需求</NavLink><NavLink to="/messages" data-tour="messages" onClick={event => guardLink(event, '/messages')}>消息</NavLink><NavLink to="/mine" onClick={event => guardLink(event, '/mine')}>我的</NavLink></nav>
        <form className="header-search" onSubmit={event => { event.preventDefault(); navigate(`/market?q=${encodeURIComponent(headerSearch.trim())}`) }}><Search size={18} /><input value={headerSearch} onChange={event => setHeaderSearch(event.target.value)} placeholder="搜索你想找的物品…" aria-label="搜索物品" /></form>
        {DEMO_MODE && <div className="header-user header-demo"><select aria-label="切换演示用户" value={authUser ? 0 : userId} onChange={event => { void setUserId(Number(event.target.value)) }}><option value={0}>演示用户</option>{currentBootstrap.users.filter(entry => !('email' in entry) || !entry.email).map(entry => <option key={entry.id} value={entry.id}>{entry.display_name} · {entry.location_name || '社区成员'}</option>)}</select><ChevronDown size={14} /></div>}
        {!DEMO_MODE && publicDemoAccounts.length > 0 && <div className="header-user header-demo public-demo"><select aria-label="切换演示账号" value={authUser && publicDemoAccounts.some(account => account.id === authUser.id) ? authUser.id : 0} onChange={event => { void switchPublicDemo(Number(event.target.value)) }}><option value={0}>演示用户</option>{publicDemoAccounts.map(account => <option key={account.id} value={account.id}>{account.display_name} · {account.role}</option>)}</select><ChevronDown size={14} /></div>}
        {isAuthenticated && user ? <details className="account-menu"><summary><Avatar user={user} size="small" /><span>{user.display_name}</span><ChevronDown size={14} /></summary><div><Link to="/mine">个人中心</Link><Link to="/mine#my-reservations">我的预约</Link><Link to="/settings/preferences">兴趣偏好</Link><button onClick={() => { void logout() }}>退出登录</button></div></details>
          : <div className="header-auth"><Link to="/login">登录</Link><Link className="btn btn-outline" to="/register">加入 NeighLoop</Link></div>}
        <div className="header-publish-group" data-tour="publish"><Link className="btn btn-primary header-publish" to="/publish" onClick={event => guardLink(event, '/publish')}><Plus size={17} /> 发布闲置</Link><Link className="btn btn-outline header-publish-need" to="/publish-need" onClick={event => guardLink(event, '/publish-need')}><Search size={16} /> 发布需求</Link></div>
      </header>
      <main key={location.pathname === '/onboarding' ? 'onboarding' : `${userId}-${communityId}`}><Routes>
        <Route path="/" element={<Navigate to="/market" replace />} /><Route path="/map" element={<MapPage />} /><Route path="/market" element={<MarketPage />} /><Route path="/needs" element={<NeedsPage />} />
        <Route path="/item/:id" element={<DetailPage />} /><Route path="/stats" element={<StatsPage />} /><Route path="/communities" element={<CommunityPage />} />
        <Route path="/messages" element={<RequireAuth><MessagesPage /></RequireAuth>} />
        <Route path="/passport/:code" element={<PassportPage />} />
        <Route path="/publish" element={<RequireAuth><PublishPage /></RequireAuth>} />
        <Route path="/publish-need" element={<RequireAuth><PublishNeedPage /></RequireAuth>} />
        <Route path="/mine" element={<RequireAuth><MinePage /></RequireAuth>} />
        <Route path="/settings/preferences" element={<RequireAuth><PreferencesPage /></RequireAuth>} />
        <Route path="/onboarding" element={<RequireAuth><OnboardingPage /></RequireAuth>} />
        <Route path="/login" element={<AuthPage mode="login" />} /><Route path="/register" element={<AuthPage mode="register" />} />
      </Routes></main>
      <footer className="site-footer"><span><Leaf size={18} /> NeighLoop · {currentBootstrap.community?.name || '我的社区'}</span><span>邻里之间，让好物继续被需要。 <ArrowRight size={16} /></span></footer>
      <nav className="mobile-nav" aria-label="移动端导航"><NavLink to="/market" className={({ isActive }) => isActive || location.pathname === '/needs' ? 'active' : ''}><House size={20} />首页</NavLink><NavLink to="/map"><MapPin size={20} />地图</NavLink><button type="button" className="mobile-publish-trigger" onClick={() => setMobilePublishOpen(true)} data-tour="publish"><Plus size={23} /> 发布</button><NavLink to="/messages" data-tour="messages" onClick={event => guardLink(event, '/messages')}><MessageCircle size={20} />消息</NavLink><NavLink to="/mine" onClick={event => guardLink(event, '/mine')}><UserRound size={20} />我的</NavLink></nav>
      {mobilePublishOpen && <div className="modal-backdrop mobile-publish-backdrop" onClick={() => setMobilePublishOpen(false)}><div className="mobile-publish-sheet" role="dialog" aria-label="选择发布内容" onClick={event => event.stopPropagation()}><button className="mobile-sheet-close" aria-label="关闭发布菜单" onClick={() => setMobilePublishOpen(false)}><X size={20} /></button><h2>发布到社区</h2><p>让好物与需求在附近相遇</p><Link to="/publish" onClick={event => { setMobilePublishOpen(false); guardLink(event, '/publish') }}><Plus size={22} /><span><strong>发布闲置物品</strong><small>拍照、填写信息，分享给邻居</small></span><ArrowRight size={17} /></Link><Link to="/publish-need" onClick={event => { setMobilePublishOpen(false); guardLink(event, '/publish-need') }}><Search size={22} /><span><strong>发布我在找</strong><small>说出需求，加入邻里讨论</small></span><ArrowRight size={17} /></Link></div></div>}
      {authDialog && <AuthDialog onClose={() => setAuthDialog(false)} />}
      {communitySelectorOpen && <CommunitySelector onClose={() => setCommunitySelectorOpen(false)} />}
      {!showEntrySplash && location.pathname === '/market' && authUser?.onboarding_completed && !authUser.product_tour_completed && <ProductTour />}
      {toast && <div className="toast"><Check size={18} />{toast}<button aria-label="关闭提示" onClick={() => setToast('')}><X size={15} /></button></div>}
    </div>
  </AppContext.Provider>{showEntrySplash && <EntrySplash />}</>
}
