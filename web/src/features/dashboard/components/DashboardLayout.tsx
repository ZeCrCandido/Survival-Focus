import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDashboard } from "@/features/dashboard/hooks/useDashboard"
import { useHabitsToday } from "@/features/habits/hooks/useHabits"
import { StatBar } from "@/components/shared/StatBar"
import { TaskCard } from "@/components/shared/TaskCard"
import { CharacterWidget } from "@/components/shared/CharacterWidget"
import type { DashboardResponse } from "@/features/dashboard/types"

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-6 w-1/3 animate-pulse rounded bg-[#4a7c59]/20" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="h-40 animate-pulse rounded bg-[#111111]/80" />
        <div className="h-40 animate-pulse rounded bg-[#111111]/80" />
      </div>
    </div>
  )
}

export function DashboardLayout() {
  const query = useDashboard()
  const habitsTodayQuery = useHabitsToday()

  if (query.isLoading) {
    return (
      <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
        <div className="mx-auto max-w-5xl">
          <Card className="rounded-[1.5rem] border border-[#4a7c59]/20 bg-[#141414]/95">
            <CardContent className="p-8">
              <LoadingSkeleton />
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl">
          <Card className="rounded-[1.5rem] border border-[#8b1a1a]/30 bg-[#141414]/95 p-6">
            <CardHeader>
              <CardTitle className="text-lg text-[#e8dcc8]">Dashboard error</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[#d4c5a9]">{String(query.error)}</p>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  const data = query.data as DashboardResponse
  // fallback: if the aggregated dashboard does not include habits_today (backend error),
  // use the client-side computed habits today from useHabitsToday
  const habitsTodayFromFallback = habitsTodayQuery.data
  const habitsToday = data?.habits_today ?? (habitsTodayFromFallback as any)

  return (
    <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <div className="rounded-[2rem] border border-[#4a7c59]/20 bg-[#111111]/95 p-6 shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-[#c17f24]/70">Mission control</p>
              <h1 className="mt-3 text-3xl font-semibold text-[#e8dcc8]">Mission dashboard</h1>
              <p className="mt-2 text-sm text-[#d4c5a9]/80">Overview of tasks, habits, focus sessions, rewards and exploration.</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card className="rounded-[1.5rem] border border-[#2a2a2a] bg-[#141414]/95">
              <CardHeader className="px-6 pt-6">
                <CardTitle className="text-lg text-[#e8dcc8]">Tasks & Focus</CardTitle>
              </CardHeader>
              <CardContent className="p-6">
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="rounded-2xl border border-[#2a2a2a] bg-[#111111]/90 p-4">
                      <p className="text-xs uppercase text-[#c17f24]/60">Pending</p>
                      <p className="mt-2 text-2xl font-semibold text-[#e8dcc8]">{data.tasks_today.total_pending}</p>
                      <p className="text-sm text-[#d4c5a9]/80">Critical: {data.tasks_today.critical_pending.length}</p>
                    </div>
                    <div className="rounded-2xl border border-[#2a2a2a] bg-[#111111]/90 p-4">
                      <p className="text-xs uppercase text-[#c17f24]/60">Completed today</p>
                      <p className="mt-2 text-2xl font-semibold text-[#e8dcc8]">{data.tasks_today.completed_today}</p>
                      <p className="text-sm text-[#d4c5a9]/80">Overdue: {data.tasks_today.overdue_count}</p>
                    </div>
                  </div>

                  {data.tasks_today.in_progress ? (
                    <TaskCard task={data.tasks_today.in_progress} />
                  ) : (
                    <div className="rounded-2xl border border-[#2a2a2a] bg-[#111111]/90 p-6 text-center">
                      <p className="text-sm text-[#d4c5a9]">No active task in progress.</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-[1.5rem] border border-[#2a2a2a] bg-[#141414]/95">
              <CardHeader className="px-6 pt-6">
                <CardTitle className="text-lg text-[#e8dcc8]">Habits</CardTitle>
              </CardHeader>
              <CardContent className="p-6">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="rounded-2xl border border-[#2a2a2a] bg-[#111111]/90 p-4">
                    <p className="text-xs uppercase text-[#c17f24]/60">Active</p>
                    <p className="mt-2 text-2xl font-semibold text-[#e8dcc8]">{habitsToday?.total_active_habits ?? data.habits_today.total_active_habits}</p>
                    <p className="text-sm text-[#d4c5a9]/80">Completed today: {habitsToday?.completed_today ?? data.habits_today.completed_today}</p>
                  </div>
                  <div className="rounded-2xl border border-[#2a2a2a] bg-[#111111]/90 p-4">
                    <p className="text-xs uppercase text-[#c17f24]/60">Completion</p>
                    <p className="mt-2 text-2xl font-semibold text-[#e8dcc8]">{habitsToday?.completion_rate_today ?? data.habits_today.completion_rate_today}%</p>
                    <p className="text-sm text-[#d4c5a9]/80">Logged: {habitsToday?.logged_today ?? data.habits_today.logged_today}</p>
                  </div>
                </div>
                {data.habits_today.pending_today.length === 0 ? (
                  <div className="mt-4 rounded-2xl border border-[#2a2a2a] bg-[#111111]/90 p-4 text-center">
                    <p className="text-sm text-[#d4c5a9]">No pending habit logs for today.</p>
                  </div>
                ) : (
                  <div className="mt-4 grid gap-3">
                    {data.habits_today.pending_today.map((h) => (
                      <div key={h.id} className="flex items-center justify-between rounded-lg border border-[#2a2a2a] bg-[#0f0f0f]/80 p-3">
                        <div>
                          <p className="text-sm text-[#e8dcc8]">{h.name}</p>
                          <p className="text-xs text-[#d4c5a9]/80">{h.nature}</p>
                        </div>
                        <div className="text-sm text-[#e6a817]">Log</div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <CharacterWidget character={data.character} />

            <Card className="rounded-[1.25rem] border border-[#2a2a2a] bg-[#141414]/95">
              <CardHeader className="px-4 pt-4">
                <CardTitle className="text-sm text-[#e8dcc8]">Focus today</CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <div className="space-y-2">
                  <StatBar label="Sessions" value={String(data.focus_today.sessions_today)} />
                  <StatBar label="Minutes" value={String(data.focus_today.total_minutes_today)} />
                  <StatBar label="Materials" value={String(data.focus_today.resources_earned_today.materials)} />
                </div>
              </CardContent>
            </Card>

            <Card className="rounded-[1.25rem] border border-[#2a2a2a] bg-[#141414]/95">
              <CardHeader className="px-4 pt-4">
                <CardTitle className="text-sm text-[#e8dcc8]">Pending rewards</CardTitle>
              </CardHeader>
              <CardContent className="p-4">
                <p className="text-sm text-[#d4c5a9]">{data.pending_rewards.total_pending} pending rewards</p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-[#d4c5a9]">
                  <div>Health: {data.pending_rewards.estimated_health_delta}</div>
                  <div>Energy: {data.pending_rewards.estimated_energy_delta}</div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
