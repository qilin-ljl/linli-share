import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Leaf, X } from 'lucide-react'

export function AuthDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return <div className="modal-backdrop auth-dialog-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="auth-dialog" role="dialog" aria-modal="true" aria-labelledby="auth-dialog-title">
      <button className="auth-dialog-close" aria-label="关闭登录提示" onClick={onClose}><X size={18} /></button>
      <span className="auth-dialog-icon"><Leaf size={28} /></span>
      <h2 id="auth-dialog-title">登录后继续</h2>
      <p>登录后可以发布闲置或需求，并在私聊里处理预约与交接。</p>
      <div><Link className="btn btn-primary" to="/login" onClick={onClose}>登录</Link><Link className="btn btn-outline" to="/register" onClick={onClose}>创建账号</Link></div>
    </div>
  </div>
}
