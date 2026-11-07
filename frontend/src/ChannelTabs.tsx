import { NavLink } from 'react-router-dom'
import { Search, ShoppingBag } from 'lucide-react'

export function ChannelTabs() {
  return <nav className="home-channel-tabs" aria-label="首页频道" data-tour="channels">
    <NavLink to="/market" className={({ isActive }) => isActive ? 'active' : ''}><ShoppingBag size={18} /><span>闲置市集</span></NavLink>
    <NavLink to="/needs" className={({ isActive }) => isActive ? 'active' : ''}><Search size={18} /><span>邻里需求</span></NavLink>
  </nav>
}
