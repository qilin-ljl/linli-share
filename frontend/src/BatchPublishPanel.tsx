import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Check, Package, Sparkles } from 'lucide-react'
import { api, jsonBody } from './api'
import { useApp } from './context'
import { MultiPhotoUpload } from './MultiPhotoUpload'
import type { BatchDraft, BatchRecognition, ItemInput, TradeType } from './types'
import { ProductImage } from './ui'

type EditableDraft = BatchDraft & { description: string; trade_type: TradeType; price: number | null; reviewed: boolean; selected: boolean }
const stages = ['正在识别独立物品…', '正在整理可见成色与配件…', '正在准备逐件发布草稿…']
function localTime(hours: number) {
  const date = new Date(Date.now() + hours * 3600000)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export function BatchPublishPanel() {
  const { userId, bootstrap, notify } = useApp()
  const navigate = useNavigate()
  const [imageKeys, setImageKeys] = useState<number[]>([])
  const [drafts, setDrafts] = useState<EditableDraft[]>([])
  const [source, setSource] = useState('')
  const [buildingId, setBuildingId] = useState(bootstrap.community?.member_building_id || bootstrap.buildings[0]?.id || 0)
  const [handoverLocation, setHandoverLocation] = useState(`${bootstrap.buildings.find(building => building.id === buildingId)?.name || '社区'}大厅`)
  const [start, setStart] = useState(localTime(2))
  const [end, setEnd] = useState(localTime(4))
  const [analyzing, setAnalyzing] = useState(false)
  const [stage, setStage] = useState(0)
  const [publishing, setPublishing] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!analyzing) return
    const timer = window.setInterval(() => setStage(current => Math.min(current + 1, 2)), 1800)
    return () => window.clearInterval(timer)
  }, [analyzing])
  const update = (id: number, values: Partial<EditableDraft>) => setDrafts(current => current.map(draft => draft.temp_id === id ? { ...draft, ...values } : draft))
  const recognize = async () => {
    setAnalyzing(true); setStage(0); setError('')
    try {
      const response = await api<BatchRecognition>('/api/ai/batch-recognize', userId,
        { method: 'POST', body: jsonBody({ image_keys: imageKeys, disposal_goal: 'BALANCED' }) })
      setSource(response.source)
      setDrafts(response.items.map(draft => ({ ...draft,
        description: draft.analysis.product_type ? `照片可见：${draft.analysis.product_type}。${draft.analysis.visible_defects.length ? `可见瑕疵：${draft.analysis.visible_defects.join('、')}。` : ''}功能与隐藏故障待发布者确认。` : '',
        trade_type: draft.suggested_price ? 'FIXED_PRICE' : 'FREE',
        price: draft.suggested_price, reviewed: false, selected: true })))
    } catch (e) { setError((e as Error).message) }
    finally { setAnalyzing(false) }
  }
  const publish = async () => {
    const chosen = drafts.filter(draft => draft.selected)
    if (!chosen.length) { setError('请至少选择一件物品。'); return }
    if (chosen.some(draft => !draft.reviewed || draft.title.trim().length < 2 || draft.description.trim().length < 4 || !draft.category.trim() || draft.condition === '待确认' || (draft.trade_type === 'FIXED_PRICE' && (!draft.price || draft.price <= 0)))) {
      setError('请逐件核对名称、类别、成色、描述和价格，并勾选“已核对”。'); return
    }
    if (new Date(start) <= new Date() || new Date(end) <= new Date(start)) { setError('请选择未来的有效领取时段。'); return }
    setPublishing(true); setError('')
    try {
      const items: ItemInput[] = chosen.map(draft => ({ title: draft.title.trim(), description: draft.description.trim(),
        category: draft.category.trim(), condition: draft.condition.trim(),
        trade_type: draft.trade_type, price: draft.trade_type === 'FIXED_PRICE' ? draft.price : null,
        original_price: null, building_id: buildingId, image_key: draft.image_keys[0],
        brand: draft.analysis.brand, model_name: draft.analysis.model, disposal_goal: 'BALANCED',
        handover_location: handoverLocation.trim(),
        handover_slots: [{ starts_at: new Date(start).toISOString(), ends_at: new Date(end).toISOString() }] }))
      const response = await api<{ count: number; matching_needs_count: number }>('/api/items/batch', userId,
        { method: 'POST', body: jsonBody({ items, confirmed: true }) })
      notify(`已发布 ${response.count} 件闲置${response.matching_needs_count ? `，产生 ${response.matching_needs_count} 条物品需求匹配记录` : ''}`)
      navigate('/map')
    } catch (e) { setError((e as Error).message) }
    finally { setPublishing(false) }
  }
  const selectedCount = drafts.filter(draft => draft.selected).length
  return <section className="panel batch-publish-panel"><span className="eyebrow"><Package size={17} /> 搬家清闲置</span><h2>一次拍下来，逐件确认后一起发布</h2><p>上传多张照片。点击整理后照片会由后端发送给已配置的视觉服务；服务不可用时显示人工核对草稿，不冒充自动识别。</p><MultiPhotoUpload imageKeys={imageKeys} onChange={setImageKeys} max={20} /><button className="btn btn-primary" disabled={analyzing || imageKeys.length < 2} onClick={() => { void recognize() }}><Sparkles size={17} /> {analyzing ? stages[stage] : '整理这些照片'}</button>
    {source && <p className="batch-source">{source === 'VISION_API' ? `发现 ${drafts.length} 件可以流转的物品，请逐件核对。` : `视觉服务不可用，已生成 ${drafts.length} 条人工整理草稿；请自行填写事实。`}</p>}
    {drafts.length > 0 && <><div className="batch-draft-grid">{drafts.map(draft => <article className="batch-draft" key={draft.temp_id}><div className="batch-draft-top"><label><input type="checkbox" checked={draft.selected} onChange={event => update(draft.temp_id, { selected: event.target.checked })} /> 选择发布</label><span>物品 {draft.temp_id}</span></div><ProductImage imageKey={draft.image_keys[0]} /><label>名称<input value={draft.title} onChange={event => update(draft.temp_id, { title: event.target.value })} /></label><label>类别<input value={draft.category} onChange={event => update(draft.temp_id, { category: event.target.value })} /></label><label>成色<input value={draft.condition} onChange={event => update(draft.temp_id, { condition: event.target.value })} /></label><label>描述<textarea rows={2} value={draft.description} onChange={event => update(draft.temp_id, { description: event.target.value })} placeholder="填写照片看不出的功能和使用情况" /></label><div className="batch-price-row"><select value={draft.trade_type} onChange={event => update(draft.temp_id, { trade_type: event.target.value as TradeType })}><option value="FREE">免费送</option><option value="NEGOTIABLE">随便给</option><option value="FIXED_PRICE">标价</option></select>{draft.trade_type === 'FIXED_PRICE' && <input type="number" min="1" value={draft.price ?? ''} onChange={event => update(draft.temp_id, { price: event.target.value ? Number(event.target.value) : null })} placeholder="价格" />}</div>{draft.pricing && <small>{draft.pricing.source === 'DEEPSEEK' ? 'AI 均衡建议' : '演示规则参考'}：¥{draft.pricing.balanced_price}</small>}<label className="batch-reviewed"><input type="checkbox" checked={draft.reviewed} onChange={event => update(draft.temp_id, { reviewed: event.target.checked })} /> 我已核对照片和描述</label></article>)}</div>
      <div className="batch-common"><h3>批量应用交接信息</h3><div className="batch-common-grid"><label>楼栋<select value={buildingId} onChange={event => { const id = Number(event.target.value); setBuildingId(id); setHandoverLocation(`${bootstrap.buildings.find(building => building.id === id)?.name || '社区'}大厅`) }}>{bootstrap.buildings.map(building => <option key={building.id} value={building.id}>{building.name}</option>)}</select></label><label>公共交接点<input value={handoverLocation} onChange={event => setHandoverLocation(event.target.value)} /></label><label>领取开始<input type="datetime-local" value={start} onChange={event => setStart(event.target.value)} /></label><label>领取结束<input type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} /></label></div><small>建议选择大厅、门口或物业等公共区域，不填写住宅门牌。</small></div><button className="btn btn-primary btn-large" disabled={publishing || selectedCount === 0} onClick={() => { void publish() }}><Check size={18} /> {publishing ? '发布中…' : `发布选中的 ${selectedCount} 件`}</button></>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </section>
}
