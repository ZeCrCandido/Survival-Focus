import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import type { HabitResponse, HabitCreateRequest, HabitUpdateRequest, HabitLogRequest } from "../types"

export function useHabitsList() {
  return useQuery<HabitResponse[]>({
    queryKey: ["habits"],
    queryFn: async () => apiClient<HabitResponse[]>("/habits"),
    staleTime: 1000 * 30,
  })
}

export function useHabitsToday() {
  return useQuery<{ pending_today: HabitResponse[]; total_active_habits: number; completed_today: number; completion_rate_today: number; logged_today: number }, Error>({
    queryKey: ["habits","today"],
    queryFn: async () => {
      // If backend /habits/today is not available or returns 422, compute today's view client-side
      const all = await apiClient<HabitResponse[]>(`/habits`)
      const todayIso = new Date().toISOString().split("T")[0]

      function daysSince(dateStr?: string | null) {
        if (!dateStr) return Infinity
        const d = new Date(dateStr)
        const diff = Date.now() - d.getTime()
        return Math.floor(diff / (1000 * 60 * 60 * 24))
      }

      const active = all.filter((h) => (h as any).is_active !== false)

      const pending_today = active.filter((h) => {
        const freq = (h.frequency || "daily").toLowerCase()
        if (freq === "daily") {
          // pending if never logged today
          if (!h.last_logged_at) return true
          const loggedDate = new Date(h.last_logged_at).toISOString().split("T")[0]
          return loggedDate !== todayIso
        }
        if (freq === "weekly") {
          // pending if not logged within last 7 days
          return daysSince(h.last_logged_at) > 7
        }
        // default: treat as daily
        if (!h.last_logged_at) return true
        const loggedDate = new Date(h.last_logged_at).toISOString().split("T")[0]
        return loggedDate !== todayIso
      })

      const completed_today = active.filter((h) => {
        if (!h.last_logged_at) return false
        const loggedDate = new Date(h.last_logged_at).toISOString().split("T")[0]
        return loggedDate === todayIso
      }).length

      const total_active_habits = active.length
      const logged_today = completed_today
      const completion_rate_today = total_active_habits === 0 ? 0 : Math.round((completed_today / total_active_habits) * 100)

      return { pending_today, total_active_habits, completed_today, completion_rate_today, logged_today }
    },
    staleTime: 1000 * 10,
    retry: 0,
  })
}

export function useCreateHabit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: HabitCreateRequest) => apiClient<HabitResponse>("/habits", { method: "POST", body: payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["habits"], exact: false })
    },
  })
}

export function useUpdateHabit(habitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: HabitUpdateRequest) => apiClient<HabitResponse>(`/habits/${habitId}`, { method: "PATCH", body: payload }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["habits"], exact: false }),
  })
}

export function useDeleteHabit(habitId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => apiClient(`/habits/${habitId}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["habits"], exact: false }),
  })
}

export function useLogHabit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: HabitLogRequest) => {
      // backend route is POST /{habit_id}/logs according to router
      const body: any = {
        was_completed: payload.was_completed ?? true,
        value: payload.value ?? undefined,
        notes: payload.notes ?? undefined,
        logged_at: payload.logged_at ?? new Date().toISOString().split("T")[0],
      }
      return apiClient(`/habits/${payload.habit_id}/logs`, { method: "POST", body })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["habits","today"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}
