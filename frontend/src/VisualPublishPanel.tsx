import { useEffect, useState } from 'react'
import { ArrowRight, Check, Sparkles } from 'lucide-react'
import { api, jsonBody } from './api'
import { useApp } from './context'
import { MultiPhotoUpload } from './MultiPhotoUpload'
import type { VisualEstimate } from './types'

const stages = ['正在识别物品…', '正在整理照片中可见的外观与配件…', '正在生成流转建议…']

export function VisualPublishPanel({ onApply }: {
  onApply: (result: VisualEstimate, imageKey: number, price: number | null,
    functionalConfirmed: boolean, noHiddenDefectsConfirmed: boolean,
    goal: 'FAST' | 'BALANCED' | 'PRICE_FIRST') => void
}) {
  const { userId } = useApp()
  const [imageKeys, setImageKeys] = useState<number[]>([])
  const [result, setResult] = useState<VisualEstimate | null>(null)
  const [stage, setStage] = useState(0)
  const [analyzing, setAnalyzing] = useState(false)
  const [functionalConfirmed, setFunctionalConfirmed] = useState(false)
  const [noHiddenDefectsConfirmed, setNoHiddenDefectsConfirmed] = useState(false)
  const [selectedPrice, setSelectedPrice] = useState<'quick_price' | 'balanced_price' | 'price_first'>('balanced_price')
  const [showFactors, setShowFactors] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!analyzing) return
    const timer = window.setInterval(() => setStage(current => Math.min(current + 1, 2)), 1700)
    return () => window.clearInterval(timer)
  }, [analyzing])
  const analyze = async () => {
    setAnalyzing(true); setStage(0); setError(''); setResult(null)
    try {
      const response = await api<VisualEstimate>('/api/ai/visual-estimate', userId, {
        method: 'POST', body: jsonBody({ image_keys: imageKeys, disposal_goal: 'BALANCED',
          functional_confirmed: functionalConfirmed, no_hidden_defects_confirmed: noHiddenDefectsConfirmed }),
      })
      setResult(response)
    } catch (e) { setError((e as Error).message) }
    finally { setAnalyzing(false) }
  }
  return <section className="panel visual-publish-panel"><span className="eyebrow"><Sparkles size={17} /> AI 拍照识别</span><h2>拍几张照片，先看看可见信息</h2><p>建议上传同一件物品的正面、侧面、使用痕迹和配件，共 2–5 张。点击分析后，照片会由后端发送给已配置的视觉服务。</p><MultiPhotoUpload imageKeys={imageKeys} onChange={setImageKeys} max={5} />
    <div className="visual-confirm"><strong>照片看不出来的事情，需要你确认</strong><label><input type="checkbox" checked={functionalConfirmed} onChange={event => setFunctionalConfirmed(event.target.checked)} /> 我确认功能正常</label><label><input type="checkbox" checked={noHiddenDefectsConfirmed} onChange={event => setNoHiddenDefectsConfirmed(event.target.checked)} /> 我确认没有已知的隐藏故障</label></div>
    <button className="btn btn-primary" disabled={analyzing || imageKeys.length < 2} onClick={() => { void analyze() }}><Sparkles size={17} /> {analyzing ? stages[stage] : 'AI 看看值多少'}</button>{error && <p className="inline-error">{error}</p>}
    {result && <div className="visual-result"><h3>{result.analysis.source === 'VISION_API' ? '照片分析草稿' : '视觉服务不可用，需要人工确认'}</h3><p className="visual-source">{result.analysis.source === 'VISION_API' ? '由已配置的视觉模型分析可见事实。' : '未获得可靠的照片识别结果；不会自动填入物品类型或虚构估价。'}</p><div className="visual-facts"><div><span>物品</span><strong>{result.analysis.product_type || '待你填写'}</strong></div><div><span>类别</span><strong>{result.analysis.category || '待你选择'}</strong></div><div><span>品牌 / 型号</span><strong>{[result.analysis.brand, result.analysis.model].filter(Boolean).join(' · ') || '照片未能判断'}</strong></div><div><span>外观</span><strong>{result.analysis.condition === 'UNKNOWN' ? '待确认' : result.analysis.condition}</strong></div></div>
      {result.analysis.visible_defects.length > 0 && <p>可见瑕疵：{result.analysis.visible_defects.join('、')}</p>}{result.analysis.visible_accessories.length > 0 && <p>可见配件：{result.analysis.visible_accessories.join('、')}</p>}{result.analysis.unknowns.length > 0 && <p>仍需确认：{result.analysis.unknowns.join('、')}</p>}
      {result.pricing && <><h3>三档流转建议</h3><div className="visual-price-options">{([['quick_price', '快速流转'], ['balanced_price', '均衡推荐'], ['price_first', '价格优先']] as const).map(([key, label]) => <button key={key} className={selectedPrice === key ? 'selected' : ''} onClick={() => setSelectedPrice(key)}><span>{label}</span><strong>¥ {result.pricing?.[key]}</strong>{selectedPrice === key && <Check size={16} />}</button>)}</div><small>{result.pricing.source === 'DEEPSEEK' ? 'AI 价格建议' : '演示规则参考，非视觉模型直接猜价'}</small><button className="text-link" onClick={() => setShowFactors(!showFactors)}>{showFactors ? '收起依据' : '为什么这样建议？'} <ArrowRight size={15} /></button>{showFactors && <ul>{result.pricing.factors.map(factor => <li key={factor}>{factor}</li>)}</ul>}</>}
      <button className="btn btn-primary" onClick={() => onApply(result, imageKeys[0], result.pricing?.[selectedPrice] ?? null, functionalConfirmed, noHiddenDefectsConfirmed, selectedPrice === 'quick_price' ? 'FAST' : selectedPrice === 'price_first' ? 'PRICE_FIRST' : 'BALANCED')}>带入可编辑的发布表单 <ArrowRight size={17} /></button></div>}
  </section>
}
