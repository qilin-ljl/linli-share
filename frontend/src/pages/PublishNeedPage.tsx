import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Search, Sparkles } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import { timeAgo } from '../format'
import type { Need } from '../types'

type NeedSuggestion = { category: string | null; keywords: string[]; budget_min: number | null; budget_max: number | null; reason: string; inferred: boolean }
type ParsedNeed = { category: string | null; keywords: string[]; budget_min: number | null; budget_max: number | null; source: string; inferred: boolean; suggestions: NeedSuggestion[]; needs_clarification: boolean; message: string; next_action: 'BROWSE' | 'CLARIFY' | null }

export function PublishNeedPage() {
  const { userId, bootstrap, notify } = useApp()
  const navigate = useNavigate()
  const [rawText, setRawText] = useState('')
  const [category, setCategory] = useState('')
  const [keywords, setKeywords] = useState('')
  const [budgetMax, setBudgetMax] = useState('')
  const [buildingId, setBuildingId] = useState<number | ''>(bootstrap.community?.member_building_id || '')
  const [source, setSource] = useState('')
  const [feedback, setFeedback] = useState<ParsedNeed | null>(null)
  const [selectedSuggestion, setSelectedSuggestion] = useState(0)
  const [mine, setMine] = useState<Need[]>([])
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const loadMine = useCallback(() => api<Need[]>('/api/needs?status=ALL&limit=100', userId)
    .then(rows => setMine(rows.filter(row => row.viewer_owned))), [userId])
  useEffect(() => { void loadMine().catch(() => {}) }, [loadMine])

  const chooseSuggestion = (suggestion: NeedSuggestion, index: number) => {
    setSelectedSuggestion(index)
    setCategory(suggestion.category || '')
    setKeywords(suggestion.keywords.join('、'))
    setBudgetMax(suggestion.budget_max === null ? '' : String(suggestion.budget_max))
  }
  const parse = async () => {
    setBusy('parse'); setError('')
    try {
      const result = await api<ParsedNeed>('/api/ai/parse-need', userId,
        { method: 'POST', body: jsonBody({ raw_text: rawText }) })
      setCategory(result.category || ''); setKeywords(result.keywords.join('、'))
      setBudgetMax(result.budget_max === null ? '' : String(result.budget_max)); setSource(result.source)
      setFeedback(result); setSelectedSuggestion(0)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!category.trim() && !keywords.split(/[、,，]+/).some(word => word.trim().length >= 2)) {
      setError('请先点 AI 整理需求，或填写具体物品类别／关键词；笼统描述无法匹配邻居物品。')
      return
    }
    setBusy('save'); setError('')
    try {
      const created = await api<Need>('/api/needs', userId, { method: 'POST', body: jsonBody({ raw_text: rawText.trim(),
        category: category.trim() || null, keywords: keywords.split(/[、,，]+/).map(word => word.trim()).filter(Boolean),
        budget_max: budgetMax ? Number(budgetMax) : null, building_id: buildingId || null }) })
      notify('需求已发布到当前社区')
      navigate(`/needs?focus=${created.id}`)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy('') }
  }
  const closeNeed = async (id: number) => {
    setError('')
    try { await api(`/api/needs/${id}`, userId, { method: 'PATCH', body: jsonBody({ status: 'CLOSED' }) }); await loadMine(); notify('这条需求已关闭') }
    catch (e) { setError((e as Error).message) }
  }

  return <div className="container page publish-need-page">
    <div className="page-intro"><div><span className="eyebrow"><Sparkles size={16} /> 告诉附近的邻居</span><h1>发布我在找</h1><p>用自己的话描述需求，核对 AI 整理结果后再发布。</p></div><Link className="btn btn-outline" to="/needs"><ArrowLeft size={16} /> 返回邻里需求</Link></div>
    {!bootstrap.community?.joined ? <section className="panel need-form"><h2>先加入这个社区</h2><p>发布需求需要先加入 {bootstrap.community?.name}。</p><Link className="btn btn-primary" to="/communities">选择社区</Link></section> : <form className="panel need-form" onSubmit={submit}>
      <h2>你在找什么？</h2><p>例如：刚搬家，想找电磁炉或电饭锅，100 元以内。</p>
      <textarea required minLength={2} maxLength={500} value={rawText} onChange={event => { setRawText(event.target.value); setFeedback(null); if (source) { setCategory(''); setKeywords(''); setBudgetMax('') }; setSource('') }} placeholder="用自己的话说说你在找什么…" rows={4} />
      <div className="need-parse-line"><button className="btn btn-outline" type="button" disabled={!!busy || rawText.trim().length < 2} onClick={parse}><Sparkles size={17} /> {busy === 'parse' ? '解析中…' : 'AI 帮我整理需求'}</button>{source && <span>{source === 'DEEPSEEK' ? feedback?.suggestions.some(suggestion => suggestion.inferred) ? 'DeepSeek 推测草稿，发布前请确认' : 'DeepSeek 已整理，请核对结果' : 'AI 暂不可用，已按明确词汇做规则整理'}</span>}</div>
      {feedback && <div className={`need-ai-feedback ${feedback.needs_clarification ? 'clarify' : ''}`} role="status"><Sparkles size={19} /><div><strong>{feedback.needs_clarification ? '还需要一点具体线索' : feedback.suggestions.some(suggestion => suggestion.inferred) ? 'AI 推测了几种可能需求' : '已整理出可匹配的线索'}</strong><p>{feedback.message}</p>{feedback.next_action === 'BROWSE' && <Link className="text-link" to="/market">去闲置市集看看 <ArrowRight size={15} /></Link>}{feedback.suggestions.length > 0 && <div className="need-suggestion-list" role="radiogroup" aria-label="AI 推测的需求">{feedback.suggestions.map((suggestion, index) => <button type="button" role="radio" key={`${suggestion.category}-${index}`} className={selectedSuggestion === index ? 'selected' : ''} aria-checked={selectedSuggestion === index} onClick={() => chooseSuggestion(suggestion, index)}><span>{suggestion.inferred ? 'AI 推测' : '原话明确'}</span><strong>{suggestion.keywords.join('、') || suggestion.category}</strong><small>{suggestion.reason}</small></button>)}</div>}</div></div>}
      <div className="need-fields"><label>类别<input value={category} maxLength={30} onChange={event => { setCategory(event.target.value); setFeedback(null) }} placeholder="例如：家电" /></label><label>关键词<input value={keywords} onChange={event => { setKeywords(event.target.value); setFeedback(null) }} placeholder="用顿号分隔，例如：电磁炉、电饭锅" /></label><label>最高预算（元）<input type="number" min="0" max="100000" value={budgetMax} onChange={event => setBudgetMax(event.target.value)} placeholder="可选" /></label><label>所在楼栋<select value={buildingId} onChange={event => setBuildingId(event.target.value ? Number(event.target.value) : '')}><option value="">整个社区</option>{bootstrap.buildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}</select></label></div>
      {error && <div className="inline-error">{error}</div>}<div className="need-form-footer"><small>需求公开可见，请不要填写门牌、电话等私人信息。</small><button className="btn btn-primary" disabled={!!busy} type="submit">{busy === 'save' ? '发布中…' : '发布到邻里需求'} <ArrowRight size={16} /></button></div>
    </form>}
    {mine.length > 0 && <section className="panel published-needs"><div className="panel-heading"><Search size={20} /><h2>我发布的需求</h2></div>{mine.map(need => <div className="published-need-row" key={need.id}><div><strong>{need.raw_text}</strong><small>{need.status === 'ACTIVE' ? '正在寻找' : need.status === 'CLOSED' ? '已关闭' : need.status} · {timeAgo(need.created_at)}</small></div>{need.status === 'ACTIVE' && <button className="text-link" onClick={() => closeNeed(need.id)}>关闭需求</button>}</div>)}</section>}
  </div>
}
