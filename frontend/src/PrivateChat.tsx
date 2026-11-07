import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { MessageCircle, Send } from 'lucide-react'
import { api, jsonBody } from './api'
import { timeAgo } from './format'
import type { PrivateMessage, User } from './types'
import { Avatar } from './ui'

export function PrivateChat({ itemId, userId, otherUser, showFaq = true }: { itemId: number; userId: number; otherUser: User; showFaq?: boolean }) {
  const [messages, setMessages] = useState<PrivateMessage[] | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [faq, setFaq] = useState<string[]>([])
  const messageList = useRef<HTMLDivElement>(null)
  const lastMessageId = messages?.at(-1)?.id
  const path = `/api/items/${itemId}/messages?other_user_id=${otherUser.id}`

  useEffect(() => {
    let active = true
    const refresh = () => api<PrivateMessage[]>(path, userId)
      .then(data => { if (active) { setMessages(data); setError(''); if (data.some(message => message.recipient_id === userId && !message.read_at)) void api(`/api/items/${itemId}/messages/read?other_user_id=${otherUser.id}`, userId, { method: 'POST' }).catch(() => {}) } })
      .catch(e => { if (active) setError(e.message) })
    refresh()
    const timer = window.setInterval(refresh, 5_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [path, userId, itemId, otherUser.id])
  useEffect(() => {
    if (showFaq) api<{ questions: string[] }>(`/api/items/${itemId}/faq`, userId).then(data => setFaq(data.questions)).catch(() => {})
  }, [itemId, userId, showFaq])
  useEffect(() => {
    if (messageList.current) messageList.current.scrollTop = messageList.current.scrollHeight
  }, [lastMessageId])
  const refresh = () => api<PrivateMessage[]>(path, userId).then(data => {
    setMessages(data)
    void api(`/api/items/${itemId}/messages/read?other_user_id=${otherUser.id}`, userId, { method: 'POST' }).catch(() => {})
  })
  const ask = async (question: string) => {
    setSending(true); setError('')
    try {
      await api(`/api/items/${itemId}/faq`, userId, { method: 'POST', body: jsonBody({ other_user_id: otherUser.id, question }) })
      await refresh()
    } catch (e) { setError((e as Error).message) }
    finally { setSending(false) }
  }

  const send = async (event: FormEvent) => {
    event.preventDefault()
    const body = draft.trim()
    if (!body || sending) return
    setSending(true); setError('')
    try {
      const message = await api<PrivateMessage>(`/api/items/${itemId}/messages`, userId,
        { method: 'POST', body: jsonBody({ other_user_id: otherUser.id, body }) })
      setMessages(current => current ? [...current, message] : [message])
      setDraft('')
      await refresh()
    } catch (e) { setError((e as Error).message) }
    finally { setSending(false) }
  }

  return <section className="panel private-chat" id="private-chat" aria-label={`与${otherUser.display_name}的私聊`}>
    <div className="panel-heading"><MessageCircle size={21} /><h2>私聊 · {otherUser.display_name}</h2></div>
    <p className="private-chat-note">仅你和 {otherUser.display_name} 可以看到这段对话；公开留言仍会显示给社区邻居。</p>
    <div className="private-message-list" ref={messageList} aria-live="polite">{messages === null ? <p className="muted">正在加载对话…</p>
      : messages.length ? messages.map(message => <div className={`private-message ${message.sender_id === userId ? 'mine' : ''}`} key={message.id}>
        {message.sender_id !== userId && <Avatar user={otherUser} size="small" />}
        <div>{message.is_ai && <strong className="ai-reply-label">AI 邻里助手 · 信息仅供参考</strong>}<p>{message.body}</p><small>{timeAgo(message.created_at)}</small></div>
      </div>) : <p className="muted">还没有私聊消息，可以先问问物品情况或约定交接细节。</p>}</div>
    {faq.length > 0 && <div className="chat-faq" aria-label="快捷提问">{faq.map(question => <button type="button" key={question} disabled={sending} onClick={() => ask(question)}>{question}</button>)}</div>}
    {error && <p className="inline-error">{error}</p>}
    <form className="private-chat-form" onSubmit={send}><input aria-label="私聊消息" maxLength={500} placeholder="发送仅对方可见的消息…" value={draft} onChange={event => setDraft(event.target.value)} /><button className="btn btn-primary" disabled={sending || !draft.trim()} type="submit"><Send size={17} /> 发送</button></form>
  </section>
}
