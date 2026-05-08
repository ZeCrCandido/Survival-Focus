import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useListTasks, useCreateTask, useCompleteTask } from "@/features/tasks/hooks/useTasks"
import type { TaskResponse } from "@/features/tasks/types"
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogFooter, DialogTitle } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { TaskCreateSchema } from "@/features/tasks/schemas/tasks"
import { z } from "zod"

type CreateForm = z.infer<typeof TaskCreateSchema>

function TaskRow({ t }: { t: TaskResponse }) {
  const complete = useCompleteTask(t.id)
  const [rewardOpen, setRewardOpen] = useState(false)
  const [rewards, setRewards] = useState<any[] | null>(null)
  const [isCompleting, setIsCompleting] = useState(false)

  async function handleComplete() {
    try {
      setIsCompleting(true)
      const res: any = await complete.mutateAsync()
      // If backend returned rewards, show them in a popup
      if (res?.rewards && Array.isArray(res.rewards) && res.rewards.length > 0) {
        setRewards(res.rewards)
        setRewardOpen(true)
      }
    } catch (err) {
      // error will be surfaced by react-query; could add toast here
      console.error("Complete task failed", err)
    } finally {
      setIsCompleting(false)
    }
  }

  return (
    <>
      <div className="flex items-start justify-between gap-4 rounded-md border border-[#2a2a2a] bg-[#0f0f0f]/80 p-3">
        <div>
          <div className="text-sm font-semibold text-[#e8dcc8]">{t.title}</div>
          <div className="text-xs text-[#d4c5a9]/80">{t.description}</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-[#d4c5a9]">{t.priority}</div>
          <Button size="sm" variant="outline" onClick={handleComplete} disabled={isCompleting || complete.isLoading}>
            {isCompleting || complete.isLoading ? "Completing..." : "Complete"}
          </Button>
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

export function TasksPage() {
  const [q, setQ] = useState("")
  const list = useListTasks()
  const create = useCreateTask()
  const [open, setOpen] = useState(false)

  const form = useForm<CreateForm>({
    resolver: zodResolver(TaskCreateSchema),
    defaultValues: { title: "", description: "", priority: "medium", focus_type: "none", tag_ids: [] },
  })

  function onSubmit(values: CreateForm) {
    const payload = {
      title: values.title,
      description: values.description || undefined,
      priority: (values.priority as any) || undefined,
      focus_type: (values.focus_type as any) || undefined,
      due_date: values.due_date ? new Date(values.due_date).toISOString() : undefined,
      tag_ids: Array.isArray(values.tag_ids)
        ? values.tag_ids
        : typeof values.tag_ids === "string"
        ? values.tag_ids.split(",").map((s) => s.trim()).filter(Boolean)
        : [],
    }

    create.mutate(payload, {
      onSuccess: () => {
        form.reset()
        setOpen(false)
      },
    })
  }

  return (
    <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <Card className="rounded-[1.5rem] border border-[#4a7c59]/20 bg-[#111111]/95">
          <CardHeader className="px-6 pt-6 flex items-center justify-between">
            <CardTitle className="text-lg text-[#e8dcc8]">Tasks</CardTitle>
            <div className="flex items-center gap-2">
              <Input value={q} onChange={(e) => setQ(e.target.value)} className="w-48" placeholder="Search..." />
              {/* show New Task dialog instead of inline Add */}
              <Button onClick={() => setOpen(true)}>
                New Task
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-3">
              {list.isLoading && <div className="text-sm text-[#d4c5a9]">Loading tasks...</div>}
              {list.isError && <div className="text-sm text-[#d4c5a9]">Error loading tasks</div>}
              {/* filter out completed tasks so they disappear from the list */}
              {(!list.isLoading && list.data?.filter((x) => x.status !== "completed").length === 0) && (
                <div className="text-sm text-[#d4c5a9]">No tasks yet.</div>
              )}
              {list.data?.filter((x) => x.status !== "completed").map((t) => (
                <TaskRow key={t.id} t={t} />
              ))}
            </div>
          </CardContent>
        </Card>
        
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="text-[#e8dcc8]">Create task</DialogTitle>
            </DialogHeader>

            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
              <div>
                <input
                  {...form.register("title")}
                  placeholder="Title"
                  className="w-full rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]"
                />
              </div>
              <div>
                <Textarea {...form.register("description")} placeholder="Description (optional)" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <select {...form.register("priority")} className="rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]">
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
                <select {...form.register("focus_type")} className="rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]">
                  <option value="none">None</option>
                  <option value="pomodoro">Pomodoro</option>
                  <option value="stopwatch">Stopwatch</option>
                </select>
              </div>
              <div>
                <input type="datetime-local" {...form.register("due_date" as any)} className="w-full rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]" />
              </div>
              <div>
                <input placeholder="Tag IDs (comma-separated)" {...form.register("tag_ids" as any)} className="w-full rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]" />
                <p className="text-xs text-[#d4c5a9]/70 mt-1">Enter comma-separated tag UUIDs if available.</p>
              </div>
              <DialogFooter>
                <div className="flex gap-2">
                  <Button type="submit">Create</Button>
                  <Button variant="outline" type="button" onClick={() => form.reset()}>Reset</Button>
                </div>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
