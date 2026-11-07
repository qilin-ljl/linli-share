export type TradeType = 'FREE' | 'NEGOTIABLE' | 'FIXED_PRICE'
export type ItemStatus = 'AVAILABLE' | 'UNCONFIRMED' | 'RESERVED' | 'COMPLETED' | 'ARCHIVED'
export type DisposalGoal = 'FAST' | 'BALANCED' | 'PRICE_FIRST'
export type ReservationStatus = 'PENDING' | 'CONFIRMED' | 'CANCELLED' | 'COMPLETED' | 'EXPIRED'

export interface User {
  id: number
  display_name: string
  building_id: number | null
  avatar_color: string
  location_name?: string
}

export interface Building {
  id: number
  name: string
  map_key: string
  map_x: number | null
  map_y: number | null
}

export interface Community {
  id: number
  name: string
  kind: 'NEIGHBORHOOD' | 'BUILDING' | 'OFFICE'
  city: string
  district: string
  address: string | null
  is_public: boolean
  joined: boolean
  role: string | null
  join_code: string | null
  member_building_id: number | null
  buildings: Building[]
}

export interface AuthUser extends User {
  email: string | null
  nickname: string
  avatar_url: string | null
  community_id: number | null
  onboarding_completed: boolean
  product_tour_completed: boolean
}

export interface UserPreference {
  goals: string[]
  categories: string[]
  trade_preferences: string[]
  use_distance: boolean
}

export interface AuthResponse {
  user: AuthUser
  preferences: UserPreference
}

export interface Bootstrap {
  community: Community | null
  communities: Community[]
  buildings: Building[]
  users: User[]
  categories: string[]
  need_categories: string[]
}

export interface Comment {
  id: number
  body: string
  created_at: string
  user: User
}

export interface PrivateMessage {
  id: number
  item_id: number
  sender_id: number
  recipient_id: number
  body: string
  message_type?: string
  is_ai?: boolean
  read_at?: string | null
  created_at: string
}

export interface MessageThread {
  item: { id: number; title: string; image_key: number; owner_id: number; status: string }
  other_user: User
  last_message: PrivateMessage
  unread_count: number
  reservation_status: string | null
}

export interface NeedReply {
  id: number
  need_id: number
  body: string
  user: User
  item: { id: number; title: string; image_key: number; status: string } | null
  created_at: string
}

export interface ItemConversation {
  user: User
  last_message: PrivateMessage | null
}

export interface HandoverSlot {
  id: number
  starts_at: string
  ends_at: string
}

export interface Reservation {
  id: number
  item_id: number
  buyer: User
  seller_id: number
  slot: HandoverSlot
  status: ReservationStatus
  pickup_code: string | null
  created_at: string
  confirmed_at: string | null
  completed_at: string | null
  handover_status: 'WAITING' | 'DEPARTED' | 'ARRIVED' | 'DELAYED'
  arrived_at: string | null
  delay_minutes: number
  wait_until: string | null
  overdue: boolean
  minutes_past_slot: number
}

export interface ItemEvent {
  id: number
  item_id: number
  type: string
  text: string
  created_at: string
}

export interface ItemEventResponse {
  events: ItemEvent[]
  total_minutes: number | null
}

export interface ActivityEvent {
  id: number
  type: string
  text: string
  created_at: string
  item_id: number
}

export interface Item {
  id: number
  owner: User
  building_id: number
  building_name: string
  title: string
  description: string
  category: string
  condition: string
  brand?: string | null
  model_name?: string | null
  trade_type: TradeType
  price: number | null
  original_price: number | null
  image_key: number
  status: ItemStatus
  stored_status: string
  disposal_goal: DisposalGoal
  last_confirmed_at: string
  handover_location: string | null
  public_location: string
  visible_location: string
  distance_meters: number | null
  passport_code: string | null
  viewer_can_relist?: boolean
  next_slot_at: string | null
  scheduled_handover_at: string | null
  created_at: string
  completed_at: string | null
  interest_count: number
  viewer_interested: boolean
  comments?: Comment[]
  interested_users?: User[]
  recipient_id?: number | null
  handover_slots?: HandoverSlot[]
  reservations?: Reservation[]
  my_reservation?: Reservation | null
  hours_to_complete?: number
  recommendation_reason?: string
  matching_needs_count?: number
}

export interface MapBuilding extends Building {
  active_count: number
  items: Item[]
}

export interface Need {
  id: number
  user: User
  community_id: number
  building_id: number | null
  building_name: string
  raw_text: string
  category: string | null
  keywords: string[]
  budget_min: number | null
  budget_max: number | null
  status: 'ACTIVE' | 'MATCHED' | 'CLOSED' | 'EXPIRED'
  created_at: string
  expires_at: string | null
  viewer_owned?: boolean
  reply_count: number
  has_listing_reply: boolean
}

export interface NeedSummary {
  community_id: number
  total: number
  buildings: { building_id: number; name: string; count: number; categories: { category: string; count: number }[] }[]
}

export interface MatchingNeeds {
  count: number
  budget_count: number
  matches: { need_id: number; summary: string; reasons: string[]; budget_max: number | null }[]
}

export interface Passport {
  passport_code: string
  title: string
  category: string
  image_key: number
  status: ItemStatus
  current_item_id: number
  completed_count: number
  neighbor_count: number
  days_in_community: number
  timeline: ItemEvent[]
}

export interface VisualAnalysis {
  product_type: string | null
  category: string | null
  brand: string | null
  model: string | null
  condition: 'NEW' | 'GOOD' | 'FAIR' | 'WORN' | 'UNKNOWN'
  condition_score: number | null
  visible_defects: string[]
  visible_accessories: string[]
  unknowns: string[]
  source?: 'VISION_API' | 'MANUAL_REVIEW_REQUIRED'
}

export interface VisualEstimate {
  analysis: VisualAnalysis
  pricing: { quick_price: number; balanced_price: number; price_first: number; factors: string[]; source: string; reason: string } | null
  note: string
}

export interface BatchDraft {
  temp_id: number
  image_keys: number[]
  analysis: VisualAnalysis & { photo_indices: number[] }
  pricing: VisualEstimate['pricing']
  title: string
  category: string
  condition: string
  suggested_price: number | null
}

export interface BatchRecognition { items: BatchDraft[]; source: string; note: string }

export interface Stats {
  month_published: number
  month_completed: number
  active_count: number
  total_completed: number
  avg_transfer_hours: number
  no_chat_completion_rate: number
  fastest: Item[]
  most_wanted: Item[]
  trend: { month: string; published: number; completed: number }[]
  daily_trend: { date: string; label: string; published: number; completed: number; views: number }[]
  category_distribution: { category: string; count: number; percentage: number }[]
  building_heat: { building_id: number; name: string; active_count: number; completed_count: number; last30_activity: number }[]
  last30_completed: number
  completion_share: number
  week_need_count: number
  week_matched_need_count: number
  month_batch_items: number
  relisted_completed_count: number
}

export interface MySummary {
  published_count: number
  active_count: number
  reserved_count: number
  unconfirmed_count: number
  completed_count: number
  received_interests: number
  helped_neighbors: number
  my_reservation_count: number
  activity_count: number
}

export interface MyReservation extends Reservation { item: Item }
export interface MyActivityEvent extends ItemEvent { item_title: string; image_key: number }

export interface ItemInput {
  title: string
  description: string
  category: string
  condition: string
  trade_type: TradeType
  price: number | null
  original_price: number | null
  building_id: number
  image_key: number
  brand?: string | null
  model_name?: string | null
  disposal_goal: DisposalGoal
  handover_location: string
  handover_slots: { starts_at: string; ends_at: string }[]
  selected_price_strategy?: DisposalGoal | null
  selected_price_source?: 'DEEPSEEK' | 'RULE_FALLBACK' | null
}
