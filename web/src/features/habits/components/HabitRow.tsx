import { Button } from "@/components/ui/button"
import { useLogHabit } from "@/features/habits/hooks/useHabits"
import type { HabitResponse } from "@/features/habits/types"
import { useState } from "react"

export function HabitRow({ habit }: { habit: HabitResponse }) {
  const log = useLogHabit()
  const [loading, setLoading] = useState(false)

  async function handleLog() {
    try {
      setLoading(true)
      await log.mutateAsync({ habit_id: habit.id, was_completed: true })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center justify-between rounded-lg border border-[#2a2a2a] bg-[#0f0f0f]/80 p-3">
      <div>
        <p className="text-sm text-[#e8dcc8]">{habit.name}</p>
        <p className="text-xs text-[#d4c5a9]/80">{habit.nature} • Streak: {habit.streak ?? 0}</p>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" onClick={handleLog} disabled={loading || log.isLoading}>
          {loading || log.isLoading ? "Logging..." : "Log"}
        </Button>
      </div>
    </div>
  )
}
