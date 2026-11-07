import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowRight, Leaf, Repeat2, Users } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import type { Item, Passport } from '../types'
import { Empty, Loading, ProductImage } from '../ui'

export function PassportPage() {
  const { code } = useParams()
  const { userId, isAuthenticated, requestAuth } = useApp()
  const [passport, setPassport] = useState<Passport | null>(null)
  const [item, setItem] = useState<Item | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    api<Passport>(`/api/passports/${encodeURIComponent(code || '')}`, userId).then(result => {
      if (!active) return
      setPassport(result)
      api<Item>(`/api/items/${result.current_item_id}`, userId).then(latest => { if (active) setItem(latest) }).catch(() => {})
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [code, userId])
  if (error) return <Empty title="无法打开物品护照" detail={error} />
  if (!passport) return <Loading />
  return <div className="container page passport-page"><div className="passport-hero panel"><ProductImage imageKey={passport.image_key} /><div><span className="eyebrow"><Leaf size={17} /> NeighLoop Item Passport</span><h1>{passport.title}</h1><strong>{passport.passport_code}</strong><p>这件物品在社区中的每次发布和交接都留下真实记录。时间线不公开住宅门牌或精确位置。</p><div className="passport-actions"><Link className="btn btn-outline" to={`/item/${passport.current_item_id}`}>查看当前物品 <ArrowRight size={16} /></Link>{item?.viewer_can_relist && (isAuthenticated ? <Link className="btn btn-primary" to={`/publish?relist=${item.id}`}><Repeat2 size={17} /> 再次发布</Link> : <button className="btn btn-primary" onClick={() => requestAuth(`/publish?relist=${item.id}`)}>登录后再次发布</button>)}</div></div></div>
    <div className="passport-metrics"><div className="panel"><Repeat2 size={22} /><strong>{passport.completed_count}</strong><span>完成流转</span></div><div className="panel"><Users size={22} /><strong>{passport.neighbor_count}</strong><span>经历邻居</span></div><div className="panel"><Leaf size={22} /><strong>{passport.days_in_community}</strong><span>在社区的天数</span></div></div>
    <section className="panel passport-history"><h2>流转时间线</h2><ol>{passport.timeline.map(event => <li key={event.id}><span className="passport-history-dot" /><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</time><strong>{event.text}</strong></li>)}</ol></section>
  </div>
}
