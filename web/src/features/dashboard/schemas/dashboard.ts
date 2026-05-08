import { z } from "zod"

export const DashboardTagSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  color: z.string(),
})

export const DashboardInProgressTaskSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  category_id: z.string().uuid().nullable().optional(),
  title: z.string(),
  description: z.string().nullable().optional(),
  priority: z.string(),
  status: z.string(),
  focus_type: z.string(),
  due_date: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  estimated_adventure_impact: z.number().nullable().optional(),
  tags: z.array(DashboardTagSummarySchema),
  created_at: z.string(),
  updated_at: z.string(),
})

export const DashboardActiveFocusSessionSchema = z.object({
  id: z.string().uuid(),
  task_id: z.string().uuid().nullable().optional(),
  type: z.string(),
  started_at: z.string(),
})

export const DashboardCriticalTaskSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  priority: z.string(),
  due_date: z.string().nullable().optional(),
  estimated_adventure_impact: z.number().nullable().optional(),
})

export const DashboardTasksTodaySchema = z.object({
  total_pending: z.number(),
  completed_today: z.number(),
  overdue_count: z.number(),
  in_progress: DashboardInProgressTaskSchema.nullable().optional(),
  critical_pending: z.array(DashboardCriticalTaskSchema),
  active_focus_session: DashboardActiveFocusSessionSchema.nullable().optional(),
})

export const DashboardPendingHabitSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  nature: z.string(),
  color: z.string().nullable().optional(),
  icon: z.string().nullable().optional(),
})

export const DashboardHabitsTodaySchema = z.object({
  total_active_habits: z.number(),
  logged_today: z.number(),
  completed_today: z.number(),
  pending_today: z.array(DashboardPendingHabitSchema),
  completion_rate_today: z.number(),
})

export const DashboardFocusResourcesSchema = z.object({
  water: z.number(),
  food: z.number(),
  materials: z.number(),
})

export const DashboardFocusTodaySchema = z.object({
  sessions_today: z.number(),
  total_minutes_today: z.number(),
  completed_sessions_today: z.number(),
  resources_earned_today: DashboardFocusResourcesSchema,
})

export const DashboardSleepLastSchema = z.object({
  external_date: z.string(),
  total_sleep_hours: z.number().nullable().optional(),
  total_sleep_minutes: z.number().nullable().optional(),
  rem_hours: z.number().nullable().optional(),
  deep_hours: z.number().nullable().optional(),
  core_hours: z.number().nullable().optional(),
  awake_hours: z.number().nullable().optional(),
  sleep_quality: z.string().nullable().optional(),
  sleep_start: z.string().nullable().optional(),
  sleep_end: z.string().nullable().optional(),
  days_since: z.number(),
})

export const DashboardWorkoutLastSchema = z.object({
  name: z.string().nullable().optional(),
  started_at: z.string(),
  duration_seconds: z.number().nullable().optional(),
  distance_km: z.number().nullable().optional(),
  active_energy_kcal: z.number().nullable().optional(),
  avg_heart_rate: z.number().nullable().optional(),
  effort_level: z.string().nullable().optional(),
  days_since: z.number(),
})

export const DashboardRewardsBreakdownSchema = z.object({
  focus_session: z.number(),
  habit_log: z.number(),
  workout_session: z.number(),
  sleep_session: z.number(),
})

export const DashboardPendingRewardsSchema = z.object({
  total_pending: z.number(),
  has_unprocessed: z.boolean(),
  breakdown: DashboardRewardsBreakdownSchema,
  estimated_health_delta: z.number(),
  estimated_energy_delta: z.number(),
})

export const DashboardNextAreaSchema = z.object({
  area_name: z.string(),
  difficulty: z.string(),
  success_chance: z.number(),
})

export const DashboardExplorationSchema = z.object({
  is_active: z.boolean(),
  area_name: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  current_impact_score: z.number().nullable().optional(),
  was_successful: z.boolean().nullable().optional(),
  ended_at: z.string().nullable().optional(),
  resources_found: z.record(z.unknown()).nullable().optional(),
  next_area_estimate: DashboardNextAreaSchema.nullable().optional(),
})

export const DashboardOnboardingSchema = z.object({
  is_completed: z.boolean(),
  avatar_assigned: z.boolean(),
  character_created: z.boolean(),
})

export const DashboardResponseSchema = z.object({
  character: z.any().nullable().optional(),
  tasks_today: DashboardTasksTodaySchema,
  habits_today: DashboardHabitsTodaySchema,
  focus_today: DashboardFocusTodaySchema,
  sleep_last: DashboardSleepLastSchema.nullable().optional(),
  workout_last: DashboardWorkoutLastSchema.nullable().optional(),
  pending_rewards: DashboardPendingRewardsSchema,
  exploration: DashboardExplorationSchema,
  onboarding: DashboardOnboardingSchema,
})

export type DashboardResponseType = z.infer<typeof DashboardResponseSchema>
