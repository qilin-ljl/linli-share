import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowRight, BarChart3, Camera, Check, Clock3, Images, Leaf, Plus, Send, Sparkles, Trash2 } from 'lucide-react'
import { api, jsonBody } from '../api'
import { useApp } from '../context'
import type { DisposalGoal, Item, ItemInput, TradeType } from '../types'
import { ProductImage } from '../ui'
import { VisualPublishPanel } from '../VisualPublishPanel'
import { BatchPublishPanel } from '../BatchPublishPanel'
import type { VisualEstimate } from '../types'

function futureSlot(hours: number) {
  const start = new Date(Date.now() + hours * 3600000)
  return { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 30 * 60000).toISOString() }
}
function localInput(value: string) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
function fromLocal(value: string) { return value ? new Date(value).toISOString() : '' }
type PriceOption = { price: number; reason: string }
type PriceAdvice = { quick_price: number; balanced_price: number; price_first: number; recommended_mode: DisposalGoal; reason: string; source: 'DEEPSEEK' | 'RULE_FALLBACK'; comparable_count: number; options: { quick: PriceOption; balanced: PriceOption; price_first: PriceOption }; factors: string[] }

export function PublishPage() {
  const { userId, bootstrap, notify } = useApp()
  const [params, setParams] = useSearchParams()
  const editId = params.get('edit')
  const relistId = params.get('relist')
  const mode = params.get('mode')
  const navigate = useNavigate()
  const [form, setForm] = useState<ItemInput>(() => {
    const buildingId = bootstrap.community?.member_building_id || bootstrap.buildings[0]?.id || 1
    return { title: '', description: '', category: '家居', condition: '九成新', trade_type: 'FREE',
      price: null, original_price: null, building_id: buildingId, image_key: 0,
      disposal_goal: 'BALANCED', handover_location: `${bootstrap.buildings.find(b => b.id === buildingId)?.name || '社区'}大厅`,
      handover_slots: [futureSlot(2), futureSlot(4), futureSlot(26)] }
  })
  const [aiDescription, setAiDescription] = useState('')
  const [customCategory, setCustomCategory] = useState(false)
  const [aiPrice, setAiPrice] = useState<PriceAdvice | null>(null)
  const [whyOpen, setWhyOpen] = useState(false)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [photoError, setPhotoError] = useState('')
  useEffect(() => { if (editId) api<Item>(`/api/items/${editId}`, userId).then(item => {
    if (item.owner.id !== userId) throw new Error('只能编辑自己的物品')
    setForm({ title: item.title, description: item.description, category: item.category, condition: item.condition,
      trade_type: item.trade_type, price: item.price, original_price: item.original_price,
      building_id: item.building_id, image_key: item.image_key,
      disposal_goal: item.disposal_goal, handover_location: item.handover_location || '',
      handover_slots: (item.handover_slots || []).map(slot => ({ starts_at: slot.starts_at, ends_at: slot.ends_at })),
      selected_price_strategy: null, selected_price_source: null })
    setCustomCategory(!bootstrap.categories.includes(item.category))
  }).catch(e => setError(e.message)) }, [editId, userId, bootstrap.categories])
  useEffect(() => { if (relistId) api<Item>(`/api/items/${relistId}`, userId).then(item => {
    if (!item.viewer_can_relist) throw new Error('只有当前拥有这件物品的邻居可以再次发布')
    const buildingId = bootstrap.community?.member_building_id || bootstrap.buildings[0]?.id || item.building_id
    setForm(previous => ({ ...previous, title: item.title, description: item.description,
      category: item.category, condition: item.condition, brand: item.brand, model_name: item.model_name,
      trade_type: item.trade_type, price: item.price, image_key: item.image_key,
      building_id: buildingId, handover_location: `${bootstrap.buildings.find(building => building.id === buildingId)?.name || '社区'}大厅`,
      handover_slots: [futureSlot(2), futureSlot(4), futureSlot(26)] }))
    setCustomCategory(!bootstrap.categories.includes(item.category))
  }).catch(e => setError(e.message)) }, [relistId, userId, bootstrap.community?.member_building_id, bootstrap.buildings, bootstrap.categories])
  const set = <K extends keyof ItemInput>(key: K, value: ItemInput[K]) => setForm(prev => ({ ...prev, [key]: value }))
  const uploadPhoto = async (file?: File) => {
    if (!file) return
    setPhotoError('')
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) { setPhotoError('请上传 JPG、PNG 或 WebP 照片。'); return }
    if (file.size > 12 * 1024 * 1024) { setPhotoError('照片不能超过 12 MB。'); return }
    setBusy('photo')
    try {
      const result = await api<{ image_key: number }>('/api/uploads/images', userId,
        { method: 'POST', headers: { 'Content-Type': file.type }, body: file })
      set('image_key', result.image_key)
      notify('照片已上传')
    } catch (e) { setPhotoError((e as Error).message) }
    finally { setBusy('') }
  }
  const aiCall = async (kind: 'description' | 'price') => {
    setBusy(kind); setError('')
    try {
      if (kind === 'description') {
        const result = await api<{ description: string }>('/api/ai/optimize-description', userId, { method: 'POST', body: jsonBody({ title: form.title, rough_description: form.description, condition: form.condition }) })
        setAiDescription(result.description)
      } else {
        const result = await api<PriceAdvice>('/api/ai/pricing-suggestion', userId, { method: 'POST', body: jsonBody({ title: form.title, description: form.description, category: form.category, condition: form.condition, original_price: form.original_price, disposal_goal: form.disposal_goal }) })
        setAiPrice(result)
      }
    } catch (e) { setError((e as Error).message) } finally { setBusy('') }
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault(); if (busy) return
    if (form.condition === '待确认') { setError('请先确认物品实际成色。'); return }
    if (relistId && form.image_key <= 35) { setError('再次发布请上传物品当前状态的实拍照片。'); return }
    setBusy('save'); setError('')
    try {
      const result = await api<Item>(relistId ? `/api/items/${relistId}/relist` : editId ? `/api/items/${editId}` : '/api/items', userId, { method: editId ? 'PATCH' : 'POST', body: jsonBody(form) })
      notify(relistId ? '再次发布成功，物品护照已延续' : editId ? '物品已更新' : result.matching_needs_count ? `发布成功，附近有 ${result.matching_needs_count} 条明确需求可能匹配` : '发布成功，邻居现在可以看到它了')
      navigate(`/item/${result.id}`)
    } catch (e) { setError((e as Error).message); window.scrollTo({ top: 0, behavior: 'smooth' }) } finally { setBusy('') }
  }
  const updateSlot = (index: number, field: 'starts_at' | 'ends_at', value: string) => {
    const next = form.handover_slots.map((slot, i) => i === index ? { ...slot, [field]: fromLocal(value) } : slot)
    set('handover_slots', next)
  }
  const applyVisual = (result: VisualEstimate, imageKey: number, price: number | null,
    functionalConfirmed: boolean, noHiddenDefectsConfirmed: boolean,
    goal: DisposalGoal) => {
    const analysis = result.analysis
    const description = [analysis.product_type ? `照片可见：${analysis.product_type}。` : '',
      analysis.visible_defects.length ? `可见瑕疵：${analysis.visible_defects.join('、')}。` : '',
      analysis.visible_accessories.length ? `可见配件：${analysis.visible_accessories.join('、')}。` : '',
      functionalConfirmed ? '发布者确认功能正常。' : '功能状态待发布者确认。',
      noHiddenDefectsConfirmed ? '发布者确认没有已知隐藏故障。' : '隐藏故障无法从照片判断。'].join('')
    const condition = { NEW: '全新未使用', GOOD: '九成新', FAIR: '有使用痕迹', WORN: '七成新', UNKNOWN: '待确认' }[analysis.condition]
    setForm(previous => ({ ...previous, title: analysis.product_type || '',
      description: analysis.product_type ? description : '', category: analysis.category || '',
      condition, brand: analysis.brand, model_name: analysis.model, image_key: imageKey,
      trade_type: price ? 'FIXED_PRICE' : 'FREE', price, disposal_goal: goal,
      selected_price_strategy: price ? goal : null,
      selected_price_source: price ? result.pricing?.source === 'DEEPSEEK' ? 'DEEPSEEK' : 'RULE_FALLBACK' : null }))
    setCustomCategory(!analysis.category || !bootstrap.categories.includes(analysis.category))
    const next = new URLSearchParams(params); next.delete('mode'); setParams(next)
  }
  const aiReady = form.title.trim().length >= 2 && form.description.trim().length >= 4
  const aiHint = '先填写物品名称（至少 2 字）和物品描述（至少 4 字）。'
  const mobileDescriptionAi = <section className="mobile-ai-inline" aria-label="AI 描述助手"><div className="ai-box-title"><Sparkles size={18} /><strong>AI 帮你把描述写得更生动</strong></div><p>先填写真实物品名称和现状，生成后由你核对。</p><button className="btn btn-outline" type="button" disabled={!!busy || !aiReady} onClick={() => aiCall('description')}>{busy === 'description' ? '生成中…' : '生成描述建议'}</button>{!aiReady && <small className="ai-form-hint">{aiHint}</small>}{aiDescription && <div className="ai-result"><p>{aiDescription}</p><button className="btn btn-primary" type="button" onClick={() => { set('description', aiDescription); setAiDescription('') }}>使用此描述 <ArrowRight size={15} /></button></div>}</section>
  const mobilePriceAi = <section className="mobile-ai-inline" aria-label="AI 定价助手"><div className="ai-box-title"><BarChart3 size={18} /><strong>AI 流转价格建议</strong></div><p>参考同社区历史标价，最终价格仍由你决定。</p><button className="btn btn-outline" type="button" disabled={!!busy || !aiReady} onClick={() => aiCall('price')}>{busy === 'price' ? '分析中…' : 'AI 帮我定价'}</button>{!aiReady && <small className="ai-form-hint">{aiHint}</small>}{aiPrice && <div className="ai-result"><div className="pricing-options">{([['FAST', '快速流转', aiPrice.options.quick], ['BALANCED', '均衡推荐', aiPrice.options.balanced], ['PRICE_FIRST', '价格优先', aiPrice.options.price_first]] as [DisposalGoal, string, PriceOption][]).map(([goal, title, option]) => <button key={goal} type="button" className={form.selected_price_strategy === goal ? 'recommended' : ''} onClick={() => setForm(prev => ({ ...prev, trade_type: 'FIXED_PRICE', price: option.price, disposal_goal: goal, selected_price_strategy: goal, selected_price_source: aiPrice.source }))}><span>{title}</span><strong>¥ {option.price}</strong></button>)}</div><p>{aiPrice.reason}</p><small>{aiPrice.source === 'DEEPSEEK' ? 'DeepSeek 建议' : '规则参考'} · 历史标价仅供参考，不代表实际成交价。</small></div>}</section>
  const modeNav = <div className="publish-mode-nav"><Link className={!mode ? 'active' : ''} to={relistId ? `/publish?relist=${relistId}` : editId ? `/publish?edit=${editId}` : '/publish'}>普通发布</Link><Link className={mode === 'photo' ? 'active' : ''} to={relistId ? `/publish?mode=photo&relist=${relistId}` : editId ? `/publish?mode=photo&edit=${editId}` : '/publish?mode=photo'}>AI 拍照发布</Link>{!relistId && !editId && <Link className={mode === 'batch' ? 'active' : ''} to="/publish?mode=batch">搬家清闲置</Link>}</div>
  if (!bootstrap.community?.joined) return <div className="container page auth-required"><h1>先加入一个社区</h1><p>发布闲置需要选择你所在的小区、楼栋或办公室。</p><Link className="btn btn-primary" to="/communities">选择社区</Link></div>
  if (mode === 'photo') return <div className="container page publish-page"><div className="page-intro"><div><span className="eyebrow"><Sparkles size={16} /> AI 辅助发布</span><h1>AI 拍照发布</h1><p>先从可见照片提取事实，再由独立定价服务给出流转建议。</p></div></div>{modeNav}<VisualPublishPanel onApply={applyVisual} /></div>
  if (mode === 'batch') return <div className="container page publish-page"><div className="page-intro"><div><span className="eyebrow"><Sparkles size={16} /> 搬家清闲置</span><h1>批量清闲置</h1><p>一次上传多张照片，逐件核对后才会真正发布。</p></div></div>{modeNav}<BatchPublishPanel /></div>
  return <div className="container page publish-page"><div className="page-intro"><div><span className="eyebrow"><Leaf size={16} /> 让好物找到下一个主人</span><h1>{relistId ? '再次发布' : editId ? '编辑闲置' : '发布闲置'}</h1><p>{relistId ? '请上传当前状态的实拍照片，重新确认成色，再延续它的社区流转护照。' : '把物品的信息说清楚，附近的邻居会更容易发现它。'}</p></div></div>{modeNav}<div className="publish-layout"><form className="publish-form panel" onSubmit={submit}>
    <div className="form-section"><div className="form-number">01</div><div className="form-content"><h2>选择物品照片</h2><p className="field-help">拍摄实物或从相册选择，让邻居看清物品的真实状态。</p><div className="photo-upload"><ProductImage imageKey={form.image_key} /><div className="photo-upload-info"><strong>{form.image_key > 35 ? '已选用你上传的照片' : '当前预览为示例照片'}</strong><p>支持 JPG、PNG、WebP，单张不超过 12 MB。</p><div className="photo-upload-buttons"><label><Camera size={17} /> 手机拍照<input type="file" accept="image/*" capture="environment" disabled={!!busy} onChange={e => { void uploadPhoto(e.target.files?.[0]); e.target.value = '' }} /></label><label><Images size={17} /> 从相册选择<input type="file" accept="image/jpeg,image/png,image/webp" disabled={!!busy} onChange={e => { void uploadPhoto(e.target.files?.[0]); e.target.value = '' }} /></label></div>{busy === 'photo' && <small>照片上传中…</small>}{photoError && <small className="photo-upload-error">{photoError}</small>}</div></div><details className="sample-photo-choices"><summary>暂时没有照片？选用示例照片</summary><div className="image-picker">{Array.from({ length: 36 }, (_, i) => <button type="button" key={i} className={form.image_key === i ? 'chosen' : ''} onClick={() => set('image_key', i)} aria-label={`选择示例照片 ${i + 1}`}><ProductImage imageKey={i} />{form.image_key === i && <span><Check size={16} /></span>}</button>)}</div></details></div></div>
    <div className="form-section"><div className="form-number">02</div><div className="form-content"><h2>介绍你的物品</h2><label>物品名称 <b>*</b><input required minLength={2} maxLength={60} value={form.title} onChange={e => set('title', e.target.value)} placeholder="例如：北欧风台灯" /></label><label>物品描述 <b>*</b><textarea required minLength={4} maxLength={1000} rows={5} value={form.description} onChange={e => set('description', e.target.value)} placeholder="成色、功能、使用痕迹、交接方式…" /></label><div className="form-two"><label>物品类别 <b>*</b><select value={customCategory ? '__custom__' : form.category} onChange={e => { const custom = e.target.value === '__custom__'; setCustomCategory(custom); set('category', custom ? '' : e.target.value) }}>{bootstrap.categories.map(c => <option key={c} value={c}>{c}</option>)}<option value="__custom__">自定义类别…</option></select>{customCategory && <input required maxLength={30} value={form.category} onChange={e => set('category', e.target.value)} placeholder="填写类别，例如：数码配件" aria-label="自定义物品类别" />}</label><label>物品成色 <select value={form.condition} onChange={e => set('condition', e.target.value)}><option value="待确认" disabled>请确认成色</option>{['全新未使用', '九成新', '八成新', '七成新', '长势良好', '有使用痕迹'].map(c => <option key={c}>{c}</option>)}</select></label></div></div></div>
    {mobileDescriptionAi}
    <div className="form-section"><div className="form-number">03</div><div className="form-content"><h2>选择流转方式</h2><div className="trade-options">{([['FREE', '免费送', '送给需要的邻居'], ['NEGOTIABLE', '随便给', '金额由双方商量'], ['FIXED_PRICE', '标价转让', '写下期望价格']] as [TradeType, string, string][]).map(([value, name, detail]) => <button type="button" key={value} className={form.trade_type === value ? 'selected' : ''} onClick={() => setForm(prev => ({ ...prev, trade_type: value, price: value === 'FIXED_PRICE' ? prev.price : null, selected_price_strategy: null, selected_price_source: null }))}><strong>{name}</strong><small>{detail}</small><span className="radio-dot" /></button>)}</div>{form.trade_type === 'FIXED_PRICE' && <div className="form-two"><label>标价（元） <b>*</b><input type="number" required min={1} value={form.price ?? ''} onChange={e => setForm(prev => ({ ...prev, price: e.target.value ? Number(e.target.value) : null, selected_price_strategy: null, selected_price_source: null }))} placeholder="例如 50" /></label><label>购入原价（选填）<input type="number" min={0} value={form.original_price ?? ''} onChange={e => set('original_price', e.target.value ? Number(e.target.value) : null)} placeholder="用于 AI 参考" /></label></div>}</div></div>
    <div className="form-section"><div className="form-number">04</div><div className="form-content"><h2>你更在意什么？</h2><p className="field-help">AI 会按处理目标给出三档流转价格。</p><div className="goal-options">{([
      ['FAST', '尽快处理', '希望今天或明天有人拿走'],
      ['BALANCED', '均衡推荐', '兼顾价格和流转速度'],
      ['PRICE_FIRST', '价格优先', '不着急，可以慢慢等'],
    ] as [DisposalGoal, string, string][]).map(([value, title, detail]) => <button key={value} type="button" className={form.disposal_goal === value ? 'selected' : ''} onClick={() => set('disposal_goal', value)}><strong>{title}</strong><small>{detail}</small></button>)}</div></div></div>
    {mobilePriceAi}
    <div className="form-section"><div className="form-number">05</div><div className="form-content"><h2>选择所在位置</h2><label>楼栋或区域 <b>*</b><select value={form.building_id} onChange={e => { const buildingId = Number(e.target.value); const building = bootstrap.buildings.find(b => b.id === buildingId); setForm(prev => ({ ...prev, building_id: buildingId, handover_location: `${building?.name || '社区'}大厅` })) }}>{bootstrap.buildings.map(b => <option value={b.id} key={b.id}>{b.name}</option>)}</select></label><label>交接地点 <b>*</b><input required maxLength={100} value={form.handover_location} onChange={e => set('handover_location', e.target.value)} placeholder="例如：3号楼大厅" /></label><p className="field-help">只填写邻居容易找到的公共交接地点。</p></div></div>
    <div className="form-section"><div className="form-number">06</div><div className="form-content"><h2>可领取时间</h2><p className="field-help">邻居可以直接选择时间预约，减少来回商量。</p><div className="slot-editor">{form.handover_slots.map((slot, index) => <div className="slot-row" key={index}><Clock3 size={18} /><label>开始<input required type="datetime-local" value={localInput(slot.starts_at)} onChange={e => updateSlot(index, 'starts_at', e.target.value)} /></label><label>结束<input required type="datetime-local" value={localInput(slot.ends_at)} onChange={e => updateSlot(index, 'ends_at', e.target.value)} /></label><button type="button" aria-label={`删除时间段 ${index + 1}`} disabled={form.handover_slots.length <= 1} onClick={() => set('handover_slots', form.handover_slots.filter((_, i) => i !== index))}><Trash2 size={17} /></button></div>)}</div><button type="button" className="text-link add-slot" disabled={form.handover_slots.length >= 5} onClick={() => set('handover_slots', [...form.handover_slots, futureSlot(2 + form.handover_slots.length * 2)])}><Plus size={17} /> 添加时间</button></div></div>
    {error && <div className="inline-error">{error}</div>}<div className="publish-submit"><span>发布后，物品会出现在市集与社区地图中。</span><button className="btn btn-primary btn-large" disabled={!!busy} type="submit"><Send size={18} /> {busy === 'save' ? '正在保存…' : editId ? '保存修改' : '发布到社区'}</button></div></form>
    <aside className="ai-panel">
      <div className="ai-head"><span className="ai-mark"><Sparkles size={27} /></span><div><h2>AI 邻里助手</h2><p>写清物品情况，让邻居更容易判断是否合适。</p></div></div>
      {!aiReady && <p className="ai-form-hint">{aiHint}</p>}
      <div className="ai-box">
        <div className="ai-box-title"><Sparkles size={18} /><strong>优化物品描述</strong></div>
        <p>基于你填写的事实，整理成清楚自然的转让说明。</p>
        <button className="btn btn-outline" type="button" disabled={!!busy || !aiReady} onClick={() => aiCall('description')}>{busy === 'description' ? '生成中…' : '生成描述建议'}</button>
        {aiDescription && <div className="ai-result"><p>{aiDescription}</p><button className="text-link" onClick={() => { set('description', aiDescription); setAiDescription('') }}>使用此描述 <ArrowRight size={15} /></button></div>}
      </div>
      <div className="ai-box">
        <div className="ai-box-title"><BarChart3 size={18} /><strong>AI 流转建议</strong></div>
        <p>按处理目标给出三档参考价格，供你自行决定。</p>
        <button className="btn btn-outline" type="button" disabled={!!busy || !aiReady} onClick={() => aiCall('price')}>{busy === 'price' ? '分析中…' : 'AI 帮我定价'}</button>
        {aiPrice && <div className="ai-result">
          <div className="pricing-options">{([
            ['FAST', '快速流转', aiPrice.options.quick],
            ['BALANCED', '均衡推荐', aiPrice.options.balanced],
            ['PRICE_FIRST', '价格优先', aiPrice.options.price_first],
          ] as [DisposalGoal, string, PriceOption][]).map(([goal, title, option]) => <button key={goal} type="button" className={aiPrice.recommended_mode === goal ? 'recommended' : ''} onClick={() => setForm(prev => ({ ...prev, trade_type: 'FIXED_PRICE', price: option.price, disposal_goal: goal, selected_price_strategy: goal, selected_price_source: aiPrice.source }))}><span>{title}{aiPrice.recommended_mode === goal && <em>推荐</em>}</span><strong>¥ {option.price}</strong><small>{option.reason}</small></button>)}</div>
          <p>{aiPrice.reason}</p>
          <button className="text-link why-toggle" type="button" aria-expanded={whyOpen} onClick={() => setWhyOpen(!whyOpen)}>{whyOpen ? '收起建议依据' : '为什么这样建议？'} <ArrowRight size={15} /></button>
          {whyOpen && <ul className="pricing-factors">{aiPrice.factors.map(factor => <li key={factor}><Check size={14} />{factor}</li>)}</ul>}
          <small>{aiPrice.source === 'DEEPSEEK' ? 'DeepSeek 建议' : '演示规则参考（非 AI 实时结果）'} · 参考 {aiPrice.comparable_count} 件同类物品的历史标价；这不是市场鉴定。</small>
        </div>}
      </div>
      <div className="ai-disclaimer">建议仅供参考，实际价格由发布者确认。DeepSeek 不可用时会明确标注规则参考。</div>
    </aside></div></div>
}

