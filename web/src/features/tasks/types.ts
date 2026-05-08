export type UUID = string

export type TaskPriority = "low" | "medium" | "high" | "critical"
export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled"
export type TaskFocusType = "pomodoro" | "stopwatch" | "none"

export interface TaskTagResponse {
  id: UUID
  name: string
  color: string
}

export interface TaskResponse {
  id: UUID
  user_id: UUID
  category_id?: UUID | null
  title: string
  description?: string | null
  priority: TaskPriority
  status: TaskStatus
  focus_type: TaskFocusType
  due_date?: string | null
  completed_at?: string | null
  estimated_adventure_impact?: number | null
  tags: TaskTagResponse[]
  created_at: string
  updated_at: string
}

export interface TaskCreateRequest {
  title: string
  description?: string
  priority?: TaskPriority
  focus_type?: TaskFocusType
  category_id?: UUID | null
  due_date?: string | null
  tag_ids?: UUID[]
}

export interface TaskUpdateRequest {
  title?: string | null
  description?: string | null
  priority?: TaskPriority | null
  status?: TaskStatus | null
  focus_type?: TaskFocusType | null
  category_id?: UUID | null
  due_date?: string | null
}
