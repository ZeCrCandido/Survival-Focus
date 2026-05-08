export type UUID = string

export type HabitNature = "healthy" | "harmful"

export interface HabitResponse {
  id: UUID
  user_id: UUID
  name: string
  description?: string | null
  nature: HabitNature
  frequency: string
  goal?: number | null
  streak?: number
  last_logged_at?: string | null
  created_at: string
  updated_at: string
}

export interface HabitCreateRequest {
  name: string
  description?: string
  nature: HabitNature
  frequency?: string
  goal?: number
}

export interface HabitUpdateRequest {
  name?: string | null
  description?: string | null
  nature?: HabitNature | null
  frequency?: string | null
  goal?: number | null
}

export interface HabitLogRequest {
  habit_id: UUID
  logged_at?: string // local date YYYY-MM-DD
  was_completed?: boolean
  value?: number
  notes?: string
}
