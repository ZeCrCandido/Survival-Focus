import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import type { TaskResponse, TaskCreateRequest, TaskUpdateRequest } from "@/features/tasks/types"

export function useListTasks(filters?: Record<string, string | undefined>) {
  const qk = ["tasks", "list", filters]
  return useQuery<TaskResponse[]>({
    queryKey: qk,
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters) {
        Object.entries(filters).forEach(([k, v]) => v && params.append(k, v))
      }
      const path = `/tasks${params.toString() ? `?${params.toString()}` : ""}`
      return apiClient<TaskResponse[]>(path)
    },
    staleTime: 1000 * 30,
  })
}

export function useGetTask(taskId: string) {
  return useQuery<TaskResponse>({
    queryKey: ["tasks", taskId],
    queryFn: async () => apiClient<TaskResponse>(`/tasks/${taskId}`),
    enabled: !!taskId,
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TaskCreateRequest) => apiClient<TaskResponse>("/tasks", { method: "POST", body: payload }),
    onSuccess: () => {
      // Invalidate all tasks-related queries (list, single task) and dashboard
      qc.invalidateQueries({ queryKey: ["tasks"], exact: false })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}

export function useUpdateTask(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (payload: TaskUpdateRequest) => apiClient<TaskResponse>(`/tasks/${taskId}`, { method: "PUT", body: payload }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["tasks"], exact: false })
      qc.invalidateQueries({ queryKey: ["tasks", taskId] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}

export function useCompleteTask(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => apiClient<TaskResponse>(`/tasks/${taskId}/complete`, { method: "PATCH" }),
    onSuccess: () => {
      // Ensure task lists and dashboard are refreshed
      qc.invalidateQueries({ queryKey: ["tasks"], exact: false })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
    },
  })
}

export function useCancelTask(taskId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => apiClient<TaskResponse>(`/tasks/${taskId}/cancel`, { method: "PATCH" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"], exact: false }),
  })
}
