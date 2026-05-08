import { z } from "zod"

export const TaskTagResponseSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  color: z.string(),
})

export const TaskResponseSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  category_id: z.string().uuid().nullable().optional(),
  title: z.string(),
  description: z.string().nullable().optional(),
  priority: z.enum(["low", "medium", "high", "critical"]),
  status: z.enum(["pending", "in_progress", "completed", "cancelled"]),
  focus_type: z.enum(["pomodoro", "stopwatch", "none"]),
  due_date: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  estimated_adventure_impact: z.number().nullable().optional(),
  tags: z.array(TaskTagResponseSchema),
  created_at: z.string(),
  updated_at: z.string(),
})

export const TaskCreateSchema = z.object({
  title: z.string().min(1).max(255),
  description: z.string().nullable().optional(),
  priority: z.enum(["low", "medium", "high", "critical"]).optional(),
  focus_type: z.enum(["pomodoro", "stopwatch", "none"]).optional(),
  category_id: z.string().uuid().nullable().optional(),
  due_date: z.string().nullable().optional(),
  // Accept either an array of UUIDs or a comma-separated string (frontend convenience)
  tag_ids: z.union([z.array(z.string().uuid()), z.string()]).nullable().optional(),
})

export const TaskUpdateSchema = TaskCreateSchema.extend({
  status: z.enum(["pending", "in_progress"]).nullable().optional(),
})

export type TaskResponseType = z.infer<typeof TaskResponseSchema>
export type TaskCreateType = z.infer<typeof TaskCreateSchema>
export type TaskUpdateType = z.infer<typeof TaskUpdateSchema>
