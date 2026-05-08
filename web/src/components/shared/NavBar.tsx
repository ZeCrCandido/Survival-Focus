import { NavLink, useNavigate } from "react-router-dom"
import { useAuthStore } from "@/stores/auth"
import { Button } from "@/components/ui/button"

const links = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/tasks", label: "Tasks" },
  { to: "/habits", label: "Habits" },
  { to: "/focus", label: "Focus" },
  { to: "/exploration", label: "Exploration" },
  { to: "/inventory", label: "Inventory" },
  { to: "/profile", label: "Profile" },
]

export function NavBar() {
  const session = useAuthStore((s) => s.session)
  const profile = useAuthStore((s) => s.profile)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const navigate = useNavigate()

  function signOut() {
    clearAuth()
    navigate("/login", { replace: true })
  }

  return (
    <header className="w-full border-b border-[#2a2a2a] bg-[#0f0f0f]/80">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center gap-4">
          <div className="text-lg font-semibold text-[#e8dcc8]">Survival Focus</div>
          <nav className="hidden gap-2 md:flex">
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                className={({ isActive }) =>
                  `inline-flex items-center rounded-md px-3 py-2 text-sm font-medium ${isActive ? 'bg-[#1a1a1a] text-[#e6a817] border border-[#4a7c59]/20' : 'text-[#d4c5a9] hover:text-[#e8dcc8]'}`
                }
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          
          <Button variant="ghost" className="text-[#e8dcc8] border border-transparent hover:bg-[#111111]" onClick={signOut}>
            Sign out
          </Button>
        </div>
      </div>
    </header>
  )
}
