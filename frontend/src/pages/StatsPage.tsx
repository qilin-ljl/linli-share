import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowRight, BarChart3, Clock3, Gift, Heart, Leaf, Package, ShieldCheck, Timer, Users } from 'lucide-react'
import { api } from '../api'
import { useApp } from '../context'
import { durationFromHours, timeAgo } from '../format'
import type { ActivityEvent, Stats } from '../types'
import { Empty, Loading, ProductImage } from '../ui'

type TrendMetric = 'published' | 'completed' | 'views'
const metricNames: Record<TrendMetric, string> = { published: '发布数', completed: '成交数', views: '独立浏览' }
const categoryColors = ['#55add7', '#8886d9', '#e5c94e', '#eaa760', '#7abf88', '#aeb6b5', '#547d66']

function TrendChart({ data, metric }: { data: Stats['daily_trend']; metric: TrendMetric }) {
  const values = data.map(point => point[metric])
  const maximum = Math.max(1, ...values)
  const width = 700, height = 260, left = 34, right = 14, top = 20, bottom = 33
  const base = height - bottom
  const x = (index: number) => left + index * (width - left - right) / Math.max(1, data.length - 1)
  const y = (value: number) => top + (maximum - value) / maximum * (base - top)
  const line = values.map((value, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(' ')
  const area = `${line} L${x(values.length - 1)},${base} L${left},${base} Z`
  return <svg className="daily-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`近30天${metricNames[metric]}趋势`}>
    <defs><linearGradient id="trend-area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#4baf75" stopOpacity=".28" /><stop offset="100%" stopColor="#4baf75" stopOpacity=".02" /></linearGradient></defs>
    {[0, 1, 2, 3, 4].map(level => { const gy = top + level * (base - top) / 4; return <g key={level}><line x1={left} x2={width - right} y1={gy} y2={gy} stroke="#e3ece3" strokeDasharray="4 4" /><text x={left - 11} y={gy + 4} textAnchor="end" fill="#809082" fontSize="11">{Math.round(maximum * (4 - level) / 4)}</text></g> })}
    <path d={area} fill="url(#trend-area)" /><path d={line} fill="none" stroke="#22854f" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    {values.map((value, index) => <circle key={data[index].date} cx={x(index)} cy={y(value)} r="4" fill="#22854f" opacity={index % 3 === 0 || index === values.length - 1 ? 1 : 0}><title>{data[index].date} · {metricNames[metric]} {value}</title></circle>)}
    {[0, 7, 14, 21, 29].map(index => data[index] && <text key={index} x={x(index)} y={height - 8} textAnchor="middle" fill="#819082" fontSize="11">{data[index].label}</text>)}
  </svg>
}

function categoryGradient(categories: Stats['category_distribution']) {
  if (!categories.length) return '#e9efea'
  let start = 0
  const stops = categories.map((entry, index) => {
    const end = index === categories.length - 1 ? 100 : start + entry.percentage
    const stop = `${categoryColors[index % categoryColors.length]} ${start}% ${end}%`
    start = end
    return stop
  })
  return `conic-gradient(${stops.join(',')})`
}

export function StatsPage({ embedded = false }: { embedded?: boolean }) {
  const { userId, bootstrap } = useApp()
  const [stats, setStats] = useState<Stats | null>(null)
  const [activity, setActivity] = useState<ActivityEvent[]>([])
  const [metric, setMetric] = useState<TrendMetric>('completed')
  const [error, setError] = useState('')
  useEffect(() => { api<Stats>('/api/community/stats', userId).then(setStats).catch(e => setError(e.message)) }, [userId])
  useEffect(() => {
    let active = true
    const refresh = () => api<ActivityEvent[]>('/api/activity?limit=5', userId).then(events => { if (active) setActivity(events) }).catch(() => {})
    refresh()
    const timer = window.setInterval(refresh, 30_000)
    return () => { active = false; window.clearInterval(timer) }
  }, [userId])
  if (error) return <Empty title="社区数据加载失败" detail={error} />
  if (!stats) return <Loading />
  const heatMax = Math.max(1, ...stats.building_heat.map(building => building.last30_activity))
  return <div className={`container page stats-dashboard ${embedded ? 'stats-embedded' : ''}`}>
    <section className="stats-banner"><div><span className="eyebrow"><Leaf size={16} /> {bootstrap.community?.name}</span><h1>社区数据面板</h1><p>看看这个社区的闲置如何流动。每一次完成交接，都留下一条真实记录。</p></div><div className="stats-banner-image" aria-hidden="true" /></section>
    <div className="dashboard-kpis">
      <div className="dashboard-kpi"><span className="kpi-icon"><Package size={27} /></span><div><small>本月发布数</small><strong>{stats.month_published}</strong><em>件新闲置</em></div></div>
      <div className="dashboard-kpi"><span className="kpi-icon kpi-orange"><Gift size={27} /></span><div><small>本月成交数</small><strong>{stats.month_completed}</strong><em>件完成流转</em></div></div>
      <div className="dashboard-kpi"><span className="kpi-icon kpi-blue"><BarChart3 size={27} /></span><div><small>当前流转中</small><strong>{stats.active_count}</strong><em>件等待新主人</em></div></div>
      <div className="dashboard-kpi"><span className="kpi-icon"><Timer size={27} /></span><div><small>平均流转时间</small><strong>{stats.avg_transfer_hours}<b> h</b></strong><em>仅统计已完成物品</em></div></div>
      <div className="dashboard-kpi"><span className="kpi-icon"><Leaf size={27} /></span><div><small>累计完成流转</small><strong>{stats.total_completed}</strong><em>件好物找到新主人</em></div></div>
    </div>
    <div className="dashboard-extension"><Link to="/needs"><strong>{stats.week_need_count}</strong><span>本周明确需求</span></Link><Link to="/needs"><strong>{stats.week_matched_need_count}</strong><span>本周需求找到候选物品</span></Link><Link to="/publish?mode=batch"><strong>{stats.month_batch_items}</strong><span>本月批量整理物品</span></Link><div><strong>{stats.relisted_completed_count}</strong><span>再次流转并完成</span></div></div>
    <div className="dashboard-main-grid">
      <section className="panel dashboard-trend"><div className="dashboard-card-head"><h2><BarChart3 size={22} /> 近30天流转趋势</h2><div className="chart-tabs">{(['published', 'completed', 'views'] as TrendMetric[]).map(value => <button key={value} className={metric === value ? 'selected' : ''} onClick={() => setMetric(value)}>{metricNames[value]}</button>)}</div></div><TrendChart data={stats.daily_trend} metric={metric} /><div className="trend-note"><span><Clock3 size={17} /> 过去30天</span><strong>完成 {stats.last30_completed} 次交接</strong></div></section>
      <section className="panel dashboard-activity"><div className="dashboard-card-head"><h2><Activity size={22} /> 社区正在发生</h2><Link to="/market" className="text-link">查看物品 <ArrowRight size={16} /></Link></div>{activity.length ? <div className="dashboard-activity-list">{activity.map(event => <Link key={event.id} to={`/item/${event.item_id}`}><span className={`activity-bullet event-${event.type.toLowerCase()}`} /> <strong>{event.text}</strong><small>{timeAgo(event.created_at)}</small></Link>)}</div> : <p className="muted">还没有新的社区动态。</p>}</section>
      <section className="panel dashboard-heat"><div className="dashboard-card-head"><h2><Users size={22} /> 楼栋流转热度</h2></div><p className="dashboard-subtitle">近30天发布与完成次数</p>{stats.building_heat.length ? <div className="heat-list">{stats.building_heat.map(building => <div className="heat-row" key={building.building_id}><strong>{building.name}</strong><span className="heat-track"><i style={{ width: `${building.last30_activity / heatMax * 100}%` }} /></span><b>{building.last30_activity}</b></div>)}</div> : <p className="muted">暂无楼栋数据。</p>}</section>
    </div>
    <div className="dashboard-bottom-grid">
      <section className="panel dashboard-wanted"><div className="dashboard-card-head"><h2><Heart size={22} /> 最多人想要</h2><Link className="text-link" to="/market?sort_by=MOST_WANTED">查看更多 <ArrowRight size={16} /></Link></div><div className="dashboard-product-list">{stats.most_wanted.map(item => <Link to={`/item/${item.id}`} key={item.id}><ProductImage imageKey={item.image_key} /><div><strong>{item.title}</strong><small>{item.building_name} · {item.category}</small><em>{item.interest_count} 人想要</em></div></Link>)}</div></section>
      <section className="panel dashboard-fastest"><div className="dashboard-card-head"><h2><Clock3 size={22} /> 最快被领走</h2></div><div className="dashboard-product-list">{stats.fastest.map(item => <Link to={`/item/${item.id}`} key={item.id}><ProductImage imageKey={item.image_key} /><div><strong>{item.title}</strong><small>{item.building_name} · {item.category}</small><em>{durationFromHours(item.hours_to_complete || 0)}完成</em></div></Link>)}</div></section>
      <section className="panel dashboard-categories"><div className="dashboard-card-head"><h2><Leaf size={22} /> 分类分布</h2></div><div className="category-layout"><div className="category-donut" style={{ background: categoryGradient(stats.category_distribution) }}><span><strong>{stats.month_published}</strong><small>本月发布</small></span></div><div className="category-legend">{stats.category_distribution.map((entry, index) => <div key={entry.category}><i style={{ background: categoryColors[index % categoryColors.length] }} /><span>{entry.category}</span><b>{entry.percentage}%</b></div>)}</div></div></section>
      <section className="panel dashboard-share"><div className="dashboard-card-head"><h2><ShieldCheck size={22} /> 累计完成占比</h2></div><div className="share-ring" style={{ background: `conic-gradient(#2d8251 ${stats.completion_share}%, #e9efea ${stats.completion_share}% 100%)` }}><span><strong>{stats.completion_share}%</strong><small>已完成</small></span></div><p><b>{stats.total_completed}</b> 件已完成，<b>{stats.active_count}</b> 件仍在流转</p><small>已完成 /（已完成 + 正在流转）</small></section>
    </div>
  </div>
}
