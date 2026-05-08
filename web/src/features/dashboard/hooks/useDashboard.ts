import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { useAuthStore } from "@/stores/auth"
import type { DashboardResponse } from "@/features/dashboard/types"

export function useDashboard() {
  const session = useAuthStore((s) => s.session)

  return useQuery<DashboardResponse>({
    queryKey: ["dashboard", "me"],
    queryFn: async () => {
      // Backend router exposes GET /dashboard (no '/me' suffix)
      return apiClient<DashboardResponse>("/dashboard")
    },
    staleTime: 1000 * 60 * 1, // 1 minute
    refetchInterval: false,
    retry: 1,
    enabled: !!session,
  })
}
