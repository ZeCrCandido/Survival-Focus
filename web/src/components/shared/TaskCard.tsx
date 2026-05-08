import type { DashboardInProgressTask } from "@/features/dashboard/types"
import { useCompleteTask } from "@/features/tasks/hooks/useTasks"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useState } from "react"

export function TaskCard({ task }: { task: DashboardInProgressTask }) {
  const complete = useCompleteTask(task.id)
  const [rewardOpen, setRewardOpen] = useState(false)
  const [rewards, setRewards] = useState<any[] | null>(null)
  const [isCompleting, setIsCompleting] = useState(false)

  async function handleComplete() {
    try {
      setIsCompleting(true)
      const res: any = await complete.mutateAsync()
      if (res?.rewards && Array.isArray(res.rewards) && res.rewards.length > 0) {
        setRewards(res.rewards)
        setRewardOpen(true)
      }
    } catch (err) {
      console.error("Complete task failed", err)
    } finally {
      setIsCompleting(false)
    }
  }

  return (
    <>
      <div className="rounded-2xl border border-[#2a2a2a] bg-[#0f0f0f]/90 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-[#e8dcc8]">{task.title}</p>
            <p className="text-xs text-[#d4c5a9]/80">{task.priority} • {task.focus_type}</p>
          </div>
          <div className="text-xs text-[#d4c5a9]">{task.due_date ? new Date(task.due_date).toLocaleDateString() : "No due"}</div>
        </div>
        <p className="mt-3 text-sm text-[#d4c5a9]/80">{task.description}</p>
        <div className="mt-3 flex items-center justify-between">
          <div className="flex gap-2">
            {task.tags.map((t) => (
              <span key={t.id} className="inline-flex rounded-full bg-[#c17f24]/20 px-2 py-1 text-xs text-[#e6a817]">{t.name}</span>
            ))}
          </div>
          <div>
            <Button
              size="sm"
              variant="outline"
              className="text-[#e8dcc8] border-[#6aab7e]/20"
              onClick={handleComplete}
              disabled={isCompleting || complete.isLoading}
            >
              {isCompleting || complete.isLoading ? "Completing..." : "Complete"}
            </Button>
          </div>
        </div>
      </div>

      <Dialog open={rewardOpen} onOpenChange={setRewardOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-[#e8dcc8]">Rewards</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-sm text-[#d4c5a9]">You scavenged the following:</p>
            <div className="grid gap-2">
              {rewards?.map((r, idx) => (
                <div key={idx} className="flex items-center justify-between rounded-md border border-[#2a2a2a] bg-[#0f0f0f]/80 p-3">
                  <div>
                    <div className="text-sm text-[#e8dcc8]">{r.name || r.type || 'Item'}</div>
                    <div className="text-xs text-[#d4c5a9]/80">{r.description || ''}</div>
                  </div>
                  <div className="text-sm text-[#e6a817]">x{r.qty ?? r.amount ?? 1}</div>
                </div>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
