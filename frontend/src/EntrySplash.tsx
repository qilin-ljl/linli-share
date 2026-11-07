import { Leaf } from 'lucide-react'

export function EntrySplash() {
  return <div className="entry-splash" role="status" aria-label="NeighLoop 启动画面">
    <div className="entry-splash-content"><span className="entry-splash-brand"><Leaf size={23} /> NeighLoop</span><p>邻里之间，让好物继续流转</p><h1>让闲置，在附近<br /><em>重新被需要</em></h1><small>发现附近 · 连接邻居</small></div>
    <div className="entry-splash-scene" aria-hidden="true"><img src="/images/community-map.png" alt="" /><span className="entry-splash-orbit orbit-one" /><span className="entry-splash-orbit orbit-two" /><span className="entry-splash-orbit orbit-three" /></div>
    <div className="entry-splash-progress" aria-hidden="true"><i /></div>
  </div>
}
