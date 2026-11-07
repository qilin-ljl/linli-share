import type { UserPreference } from './types'

export const GOAL_OPTIONS = [
  ['CLEAR', '📦', '清理闲置', '让家里的东西更快找到新主人'],
  ['FIND', '🛍', '淘附近好物', '看看邻居有什么正好用得上'],
  ['GIVE', '🎁', '免费分享', '把不用的东西送给真正需要的人'],
  ['NEED', '🔍', '我在找东西', '先看看附近有没有需要的物品'],
  ['MOVE', '🏠', '正在搬家', '一次整理多件闲置，快速处理'],
  ['BROWSE', '🌱', '逛逛社区', '看看附近最近在发生什么'],
] as const

export const CATEGORY_OPTIONS = [
  ['家居', '🏠', '家居'], ['家电', '🍳', '厨房家电'], ['数码', '💻', '数码'],
  ['图书', '📚', '图书学习'], ['绿植', '🌱', '绿植'], ['运动', '🏸', '运动'],
  ['母婴', '👶', '母婴'], ['衣物', '👕', '衣物'], ['生活用品', '📦', '生活日用'], ['其他', '🎨', '其他'],
] as const

export const TRADE_OPTIONS = [['FREE', '免费送'], ['LOW_PRICE', '邻里低价'], ['NEGOTIABLE', '随便给'], ['ANY', '都可以']] as const

export function getHomeLayout(preferences: UserPreference | null) {
  const goals = preferences?.goals || []
  if (goals.includes('MOVE')) return { priority: 'MOVE' as const, defaultFeed: 'FOR_YOU' as const }
  if (goals.includes('NEED')) return { priority: 'NEED' as const, defaultFeed: 'NEW' as const }
  if (goals.includes('GIVE')) return { priority: 'GIVE' as const, defaultFeed: 'FREE' as const }
  if (goals.includes('FIND')) return { priority: 'FIND' as const, defaultFeed: 'FOR_YOU' as const }
  return { priority: 'BROWSE' as const, defaultFeed: 'NEW' as const }
}
