import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Check, X } from 'lucide-react'
import { api } from './api'
import { useApp } from './context'

const steps = [
  { selector: '[data-tour="channels"]', title: '首页有两个频道', body: '闲置市集找物品，邻里需求看大家在找什么；两个频道都可以筛选。' },
  { selector: '[data-tour="market-search"]', title: '从附近找到合适的物品', body: '搜索名称或打开高级筛选。推荐会参考你主动选择的偏好和已完成的领取记录。' },
  { selector: '[data-tour="publish"]', title: '分开发布闲置与需求', body: '发布入口可选择分享物品或写下“我在找”；AI 建议会先交给你核对。' },
  { selector: '[data-tour="messages"]', title: '预约在私聊里处理', body: '打开物品详情选时间预约，之后在消息里与发布者确认交接。' },
]
type Rect = { top: number; left: number; width: number; height: number }

export function ProductTour() {
  const { userId, refreshSession } = useApp()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const target = Array.from(document.querySelectorAll(steps[step].selector)).find(element => element.getBoundingClientRect().width > 0)
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    const update = () => {
      const bounds = target.getBoundingClientRect()
      setRect({ top: Math.max(0, bounds.top - 7), left: Math.max(0, bounds.left - 7),
        width: bounds.width + 14, height: bounds.height + 14 })
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, { passive: true })
    return () => { window.removeEventListener('resize', update); window.removeEventListener('scroll', update) }
  }, [step])

  const finish = async () => {
    setBusy(true)
    try {
      await api('/api/me/product-tour/complete', userId, { method: 'POST' })
      await refreshSession()
      const destination = sessionStorage.getItem('neighloop-return-to')
      sessionStorage.removeItem('neighloop-return-to')
      if (destination && destination !== '/') navigate(destination)
    } finally { setBusy(false) }
  }
  const next = () => { if (step === steps.length - 1) void finish(); else setStep(step + 1) }
  if (!rect) return null
  const right = rect.left + rect.width
  const bottom = rect.top + rect.height
  const popoverHeight = 210
  const popoverTop = bottom + popoverHeight + 20 < window.innerHeight
    ? bottom + 15 : Math.max(12, rect.top - popoverHeight - 14)
  const popoverLeft = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - 326))
  return <div className="tour-layer" role="dialog" aria-modal="true" aria-label="新手引导">
    <div className="tour-mask" style={{ top: 0, left: 0, right: 0, height: rect.top }} />
    <div className="tour-mask" style={{ top: rect.top, left: 0, width: rect.left, height: rect.height }} />
    <div className="tour-mask" style={{ top: rect.top, left: right, right: 0, height: rect.height }} />
    <div className="tour-mask" style={{ top: bottom, left: 0, right: 0, bottom: 0 }} />
    <div className="tour-highlight" style={rect} />
    <div className="tour-popover" style={{ top: popoverTop, left: popoverLeft }}><div className="tour-popover-top"><span>{step + 1} / {steps.length}</span><button aria-label="跳过引导" onClick={() => { void finish() }}><X size={17} /></button></div><h2>{steps[step].title}</h2><p>{steps[step].body}</p><button className="btn btn-primary" disabled={busy} onClick={next}>{step === steps.length - 1 ? <Check size={17} /> : null}{step === steps.length - 1 ? '开始浏览' : '下一步'} {step < steps.length - 1 && <ArrowRight size={17} />}</button></div>
  </div>
}
