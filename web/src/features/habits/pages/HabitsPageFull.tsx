import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Dialog, DialogContent, DialogHeader, DialogFooter, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { HabitCreateSchema } from "@/features/habits/schemas/habits"
import { useHabitsList, useCreateHabit, useHabitsToday } from "@/features/habits/hooks/useHabits"
import type { HabitResponse } from "@/features/habits/types"
import { HabitRow } from "@/features/habits/components/HabitRow"
import { useQueryClient } from "@tanstack/react-query"

export function HabitsPageFull() {
  const [q, setQ] = useState("")
  const list = useHabitsList()
  const today = useHabitsToday()
  const create = useCreateHabit()
  const qc = useQueryClient()

  const [open, setOpen] = useState(false)

  const form = useForm<Partial<HabitResponse>>({
    resolver: zodResolver(HabitCreateSchema),
    defaultValues: { name: "", description: "", nature: "healthy", frequency: "daily", target_value: 1, unit: "", color: "#6AAB7E" },
  })
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  async function onSubmit(values: any) {
    setErrorMessage(null)
    const payload: any = {
      name: values.name,
      description: values.description || undefined,
      nature: values.nature,
      frequency: values.frequency || undefined,
      // map frontend names to backend column names
      target_value: values.target_value ? Number(values.target_value) : undefined,
      unit: values.unit || undefined,
      color: values.color || "#6AAB7E",
      icon: values.icon || undefined,
      is_active: values.is_active === undefined ? true : Boolean(values.is_active),
    }

    try {
      await create.mutateAsync(payload)
      form.reset()
      setOpen(false)
      qc.invalidateQueries({ queryKey: ["habits"], exact: false })
    } catch (err: any) {
      // Show server validation message if available
      setErrorMessage(err?.message || String(err))
    }
  }

  return (
    <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <Card className="rounded-[1.5rem] border border-[#4a7c59]/20 bg-[#111111]/95">
          <CardHeader className="px-6 pt-6 flex items-center justify-between">
            <CardTitle className="text-lg text-[#e8dcc8]">Habits</CardTitle>
            <div className="flex items-center gap-2">
              <Input value={q} onChange={(e) => setQ(e.target.value)} className="w-48" placeholder="Search..." />
              <Button onClick={() => setOpen(true)}>New habit</Button>
            </div>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-3">
              <div className="text-sm text-[#d4c5a9]">Today's habits</div>
              {today.isLoading && <div className="text-sm text-[#d4c5a9]">Loading...</div>}
              {today.data && today.data.pending_today.length === 0 && <div className="text-sm text-[#d4c5a9]">No habits pending today.</div>}
              {today.isError && (
                <div className="text-sm text-[#8b1a1a]">
                  <div className="font-semibold">Error loading today's habits:</div>
                  <div>{String((today.error as any)?.message ?? today.error)}</div>
                  { (today.error as any)?.payload && (
                    <pre className="mt-2 max-h-40 overflow-auto text-xs text-[#d4c5a9]">{JSON.stringify((today.error as any).payload, null, 2)}</pre>
                  )}
                </div>
              )}
              {today.data?.pending_today.map((h) => (
                <HabitRow key={h.id} habit={h} />
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-[1.5rem] border border-[#2a2a2a] bg-[#141414]/95">
          <CardHeader className="px-6 pt-6">
            <CardTitle className="text-lg text-[#e8dcc8]">All habits</CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <div className="space-y-3">
              {list.isLoading && <div className="text-sm text-[#d4c5a9]">Loading habits...</div>}
              {list.isError && <div className="text-sm text-[#d4c5a9]">Error loading habits</div>}
              {list.data?.length === 0 && <div className="text-sm text-[#d4c5a9]">No habits yet.</div>}
              {list.data?.map((h) => (
                <div key={h.id} className="rounded-lg border border-[#2a2a2a] bg-[#0f0f0f]/80 p-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-[#e8dcc8]">{h.name}</p>
                      <p className="text-xs text-[#d4c5a9]/80">{h.nature} • Streak: {h.streak ?? 0}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" onClick={() => qc.setQueryData(["habits"], (old: any) => old.filter((x: any) => x.id !== h.id))}>Remove</Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="text-[#e8dcc8]">Create habit</DialogTitle>
            </DialogHeader>
              <DialogDescription className="text-[#d4c5a9]">Create a habit and choose a color/icon to ensure it is accepted by the server.</DialogDescription>

            {errorMessage && (
              <div className="rounded-md border border-[#8b1a1a]/40 bg-[#2a0f0f]/40 p-3 text-sm text-[#e8dcc8]">
                <strong className="text-[#e6a817]">Server:</strong> {errorMessage}
              </div>
            )}

            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
              <div>
                <input
                  {...form.register("name")}
                  placeholder="Name"
                  className="w-full rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]"
                />
              </div>
              <div>
                <Textarea {...form.register("description")} placeholder="Description (optional)" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <select {...form.register("nature")} className="rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]">
                  <option value="healthy">Healthy</option>
                  <option value="harmful">Harmful</option>
                </select>
                <input type="number" {...form.register("target_value" as any)} className="rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]" placeholder="Target" />
              </div>
              <div>
                <input placeholder="Frequency (daily or weekly)" {...form.register("frequency" as any)} className="w-full rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]" />
              </div>
              <div className="grid grid-cols-2 gap-2 mt-2">
                <input placeholder="Unit (glasses, km)" {...form.register("unit" as any)} className="rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]" />
                <input placeholder="Color (#AABBCC)" {...form.register("color" as any)} className="rounded-md bg-[#0f0f0f]/80 px-3 py-2 text-[#e8dcc8]" />
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
