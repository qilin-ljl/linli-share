import { ArrowUpRight, Clock3, Heart, MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Item, User } from './types'
import { distanceLabel, priceLabel, slotLabel, statusLabel, timeAgo } from './format'
import { API_BASE, DEMO_MODE } from './api'

function UploadedProductImage({ imageKey, className }: { imageKey: number; className: string }) {
  const [imageUrl, setImageUrl] = useState('')
  useEffect(() => {
    let active = true
    let objectUrl = ''
    const demoId = DEMO_MODE ? Number(localStorage.getItem('neighloop-demo-user-id')) : 0
    fetch(`${API_BASE}/api/uploads/images/${imageKey}`, {
      credentials: 'include', headers: demoId ? { 'X-Demo-User-Id': String(demoId) } : {},
    }).then(response => { if (!response.ok) throw new Error('image unavailable'); return response.blob() })
      .then(blob => { objectUrl = URL.createObjectURL(blob); if (active) setImageUrl(objectUrl); else URL.revokeObjectURL(objectUrl) })
      .catch(() => {})
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [imageKey])
  return <div className={`product-image ${className}`} role="img" aria-label="发布者上传的物品照片"
    style={{ backgroundImage: imageUrl ? `url('${imageUrl}')` : 'none', backgroundPosition: 'center', backgroundSize: 'cover' }} />
}

export function ProductImage({ imageKey, className = '' }: { imageKey: number; className?: string }) {
  if (imageKey > 35) return <UploadedProductImage imageKey={imageKey} className={className} />
  const key = Math.max(0, Math.min(35, imageKey))
  const col = (key % 4) / 3 * 100
  const row = Math.floor((key % 12) / 4) / 2 * 100
  const sheet = Math.floor(key / 12)
  const file = sheet === 0 ? 'products-sprite.png' : `products-sprite-${sheet + 1}.png`
  return <div className={`product-image ${className}`} role="img" aria-label="物品示例照片" style={{ backgroundImage: `url('/images/${file}')`, backgroundPosition: `${col}% ${row}%` }} />
}

export function Avatar({ user, size = 'normal' }: { user: User; size?: 'normal' | 'small' | 'large' }) {
  return <span className={`avatar avatar-${size}`} style={{ background: user.avatar_color }} aria-label={user.display_name}>{user.display_name.slice(0, 1)}</span>
}

export function ItemCard({ item }: { item: Item }) {
  return <Link to={`/item/${item.id}`} className="item-card">
    <div className="card-image-wrap">
      <ProductImage imageKey={item.image_key} />
      <span className={`fresh-pill status-${item.status.toLowerCase()}`}>{statusLabel(item)}</span>
      <span className="heart-count"><Heart size={16} /> {item.interest_count}</span>
    </div>
    <div className="item-card-body">
      <div className="card-title-row"><h3>{item.title}</h3><ArrowUpRight size={17} /></div>
      <strong className={`price notranslate ${item.trade_type === 'FIXED_PRICE' ? 'priced' : ''}`} translate="no">{priceLabel(item)}</strong>
      <p>{item.description}</p>
      {item.recommendation_reason && <span className="recommend-reason">{item.recommendation_reason}</span>}
      {item.next_slot_at && item.status === 'AVAILABLE' && <span className="next-slot"><Clock3 size={13} /> {slotLabel({ starts_at: item.next_slot_at, ends_at: item.next_slot_at }).split('–')[0]} 可取</span>}
      <div className="card-meta"><span><MapPin size={14} /> {item.building_name} · {distanceLabel(item.distance_meters) || '社区内自提'}</span><span>{timeAgo(item.created_at)}</span></div>
    </div>
  </Link>
}

export function Loading({ label = '正在加载社区内容…' }: { label?: string }) {
  return <div className="loading-state"><div className="loader" /><p>{label}</p></div>
}

export function Empty({ title, detail }: { title: string; detail?: string }) {
  return <div className="empty-state"><span className="empty-leaf">✳</span><h3>{title}</h3>{detail && <p>{detail}</p>}</div>
}
