export type UUID = string

export interface DashboardCharacter {
  id: UUID
  name?: string | null
  level: number
  experience_points: number
  experience_to_next_level: number
  xp_progress_pct: number
  is_alive: boolean
  death_count: number
  health: number
  max_health: number
  energy: number
  max_energy: number
  hunger: number
  hydration: number
  last_fed_at?: string | null
  last_hydrated_at?: string | null
  hunger_critical: boolean
  hydration_critical: boolean
  health_critical: boolean
  energy_low: boolean
}

export interface DashboardTagSummary {
  id: UUID
  name: string
  color: string
}

export interface DashboardInProgressTask {
  id: UUID
  user_id: UUID
  category_id?: UUID | null
  title: string
  description?: string | null
  priority: string
  status: string
  focus_type: string
  due_date?: string | null
  completed_at?: string | null
  estimated_adventure_impact?: number | null
  tags: DashboardTagSummary[]
  created_at: string
  updated_at: string
}

export interface DashboardActiveFocusSession {
  id: UUID
  task_id?: UUID | null
  type: string
  started_at: string
}

export interface DashboardCriticalTask {
  id: UUID
  title: string
  priority: string
  due_date?: string | null
  estimated_adventure_impact?: number | null
}

export interface DashboardTasksToday {
  total_pending: number
  completed_today: number
  overdue_count: number
  in_progress?: DashboardInProgressTask | null
  critical_pending: DashboardCriticalTask[]
  active_focus_session?: DashboardActiveFocusSession | null
}

export interface DashboardPendingHabit {
  id: UUID
  name: string
  nature: string
  color?: string | null
  icon?: string | null
}

export interface DashboardHabitsToday {
  total_active_habits: number
  logged_today: number
  completed_today: number
  pending_today: DashboardPendingHabit[]
  completion_rate_today: number
}

export interface DashboardFocusResources {
  water: number
  food: number
  materials: number
}

export interface DashboardFocusToday {
  sessions_today: number
  total_minutes_today: number
  completed_sessions_today: number
  resources_earned_today: DashboardFocusResources
}

export interface DashboardSleepLast {
  external_date: string
  total_sleep_hours?: number | null
  total_sleep_minutes?: number | null
  rem_hours?: number | null
  deep_hours?: number | null
  core_hours?: number | null
  awake_hours?: number | null
  sleep_quality?: string | null
  sleep_start?: string | null
  sleep_end?: string | null
  days_since: number
}

export interface DashboardWorkoutLast {
  name?: string | null
  started_at: string
  duration_seconds?: number | null
  distance_km?: number | null
  active_energy_kcal?: number | null
  avg_heart_rate?: number | null
  effort_level?: string | null
  days_since: number
}

export interface DashboardRewardsBreakdown {
  focus_session: number
  habit_log: number
  workout_session: number
  sleep_session: number
}

export interface DashboardPendingRewards {
  total_pending: number
  has_unprocessed: boolean
  breakdown: DashboardRewardsBreakdown
  estimated_health_delta: number
  estimated_energy_delta: number
}

export interface DashboardNextArea {
  area_name: string
  difficulty: string
  success_chance: number
}

export interface DashboardExploration {
  is_active: boolean
  area_name?: string | null
  started_at?: string | null
  current_impact_score?: number | null
  was_successful?: boolean | null
  ended_at?: string | null
  resources_found?: Record<string, unknown> | null
  next_area_estimate?: DashboardNextArea | null
}

export interface DashboardOnboarding {
  is_completed: boolean
  avatar_assigned: boolean
  character_created: boolean
}

export interface DashboardResponse {
  character?: DashboardCharacter | null
  tasks_today: DashboardTasksToday
  habits_today: DashboardHabitsToday
  focus_today: DashboardFocusToday
  sleep_last?: DashboardSleepLast | null
  workout_last?: DashboardWorkoutLast | null
  pending_rewards: DashboardPendingRewards
  exploration: DashboardExploration
  onboarding: DashboardOnboarding
}
