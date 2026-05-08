import { type PropsWithChildren } from "react"
import { cn } from "@/lib/utils"

export function AuthShell({ children, className }: PropsWithChildren<{ className?: string }>) {
  return (
    <div className={cn("relative min-h-screen overflow-hidden bg-[#090909] text-[#e8dcc8]", className)}>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(193,127,36,0.18),transparent_20%),radial-gradient(circle_at_bottom_right,_rgba(139,26,26,0.18),transparent_18%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-4 py-12 sm:px-6 lg:px-8">
        <div className="mb-10 flex flex-col gap-3 text-center">
          <p className="text-sm uppercase tracking-[0.32em] text-[#c17f24]/70">Survival focus</p>
          <h1 className="text-4xl font-heading font-semibold tracking-tight text-[#e8dcc8] sm:text-5xl">
            Focus, survive, and rise again.
          </h1>
          <p className="mx-auto max-w-2xl text-sm leading-7 text-[#d4c5a9]/85 sm:text-base">
            Log in or register to keep your progress safe, unlock your profile, and build your character in the post-apocalyptic hub.
          </p>
        </div>

        <div className="relative overflow-hidden rounded-[2rem] border border-[#4a7c59]/20 bg-[#141414]/95 p-6 shadow-[0_32px_80px_-40px_rgba(0,0,0,0.8)] backdrop-blur-sm sm:p-10">
          <div className="pointer-events-none absolute -left-12 top-10 h-44 w-44 rounded-full bg-[#4a7c59]/10 blur-3xl" />
          <div className="pointer-events-none absolute -right-10 bottom-12 h-52 w-52 rounded-full bg-[#c0392b]/10 blur-3xl" />
          <div className="relative">{children}</div>
        </div>
      </div>
    </div>
  )
}
