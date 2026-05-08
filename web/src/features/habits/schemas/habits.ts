import { z } from "zod"

export const HabitCreateSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().max(500).optional(),
  nature: z.enum(["healthy","harmful"]),
  frequency: z.enum(["daily","weekly"]).optional(),
  target_value: z.number().min(1).optional(),
  unit: z.string().max(32).optional(),
  color: z.string().regex(/^#[0-9A-Fa-f]{6}$/, "Color must be a hex code like #AABBCC").optional(),
  icon: z.string().max(64).optional(),
})

export const HabitLogSchema = z.object({
  habit_id: z.string(),
  date: z.string().optional(),
  amount: z.number().min(0).optional(),
  note: z.string().max(250).optional(),
})
