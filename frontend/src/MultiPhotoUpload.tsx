import { useState } from 'react'
import { Camera, Images, X } from 'lucide-react'
import { api } from './api'
import { useApp } from './context'
import { ProductImage } from './ui'

export function MultiPhotoUpload({ imageKeys, onChange, max }: {
  imageKeys: number[]; onChange: (keys: number[]) => void; max: number
}) {
  const { userId } = useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const upload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true); setError('')
    const next = [...imageKeys]
    try {
      for (const file of Array.from(files).slice(0, max - next.length)) {
        if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('仅支持 JPG、PNG、WebP 图片。')
        if (file.size > 12 * 1024 * 1024) throw new Error('单张照片不能超过 12 MB。')
        const result = await api<{ image_key: number }>('/api/uploads/images', userId,
          { method: 'POST', headers: { 'Content-Type': file.type }, body: file })
        next.push(result.image_key)
        onChange([...next])
      }
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  return <div className="multi-photo-upload"><div className="multi-photo-actions"><label><Camera size={18} /> 拍照<input type="file" accept="image/*" capture="environment" disabled={busy || imageKeys.length >= max} onChange={event => { void upload(event.target.files); event.target.value = '' }} /></label><label><Images size={18} /> 从相册选择<input type="file" accept="image/jpeg,image/png,image/webp" multiple disabled={busy || imageKeys.length >= max} onChange={event => { void upload(event.target.files); event.target.value = '' }} /></label><small>{busy ? '照片上传中…' : `${imageKeys.length} / ${max} 张`}</small></div><div className="multi-photo-grid">{imageKeys.map((key, index) => <div key={key}><ProductImage imageKey={key} /><small>照片 {index + 1}</small><button type="button" aria-label={`移除照片 ${index + 1}`} onClick={() => onChange(imageKeys.filter(value => value !== key))}><X size={15} /></button></div>)}</div>{error && <p className="inline-error">{error}</p>}</div>
}
