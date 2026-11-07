import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Leaf } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import type { AuthResponse } from '../types'

export function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const { onAuthenticated } = useApp()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const register = mode === 'register'

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (register && password !== confirm) { setError('两次输入的密码不一致'); return }
    setBusy(true); setError('')
    try {
      const result = await api<AuthResponse>(register ? '/api/auth/register' : '/api/auth/login', 0,
        { method: 'POST', body: jsonBody({ email: email.trim(), password }) })
      onAuthenticated(result)
      if (!result.user.onboarding_completed) navigate('/onboarding')
      else if (!result.user.product_tour_completed) navigate('/market')
      else {
        const destination = sessionStorage.getItem('neighloop-return-to') || '/'
        sessionStorage.removeItem('neighloop-return-to')
        navigate(destination)
      }
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  return <div className="auth-page">
    <div className="auth-visual"><div><span className="eyebrow"><Leaf size={18} /> NeighLoop</span><h1>让闲置，在附近<br />重新被需要。</h1><p>从你的社区开始，让每件好物遇见下一个需要它的人。</p></div><img src="/images/community-map.png" alt="绿色社区示意图" /></div>
    <div className="auth-form-wrap"><form className="auth-form panel" onSubmit={submit}><span className="eyebrow"><Leaf size={17} /> 邻里分享从这里开始</span><h1>{register ? '加入 NeighLoop' : '欢迎回来'}</h1><p>{register ? '创建账号后先选社区与兴趣，再看看闲置市集和邻里需求两个频道。' : '登录后进入你所在社区；首次使用会带你认识新的首页。'}</p>
      {error && <div className="inline-error" role="alert">{error}</div>}
      <label>邮箱<input type="email" required autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="name@example.com" /></label>
      <label>密码<input type="password" required minLength={register ? 8 : undefined} autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={event => setPassword(event.target.value)} placeholder={register ? '至少 8 位' : '输入密码'} /></label>
      {register && <label>确认密码<input type="password" required minLength={8} autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} placeholder="再次输入密码" /></label>}
      <button className="btn btn-primary btn-wide" disabled={busy} type="submit">{busy ? '请稍候…' : register ? '创建账号' : '登录'} <ArrowRight size={18} /></button>
      <div className="auth-switch">{register ? '已有账号？' : '还没有账号？'} <Link to={register ? '/login' : '/register'}>{register ? '登录' : '创建账号'}</Link></div>
    </form></div>
  </div>
}
