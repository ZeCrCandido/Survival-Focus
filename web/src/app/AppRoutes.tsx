import { useEffect } from "react"
import { Navigate, Route, Routes } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/stores/auth"
import { AuthShell } from "@/components/shared/AuthShell"
import { LoginPage } from "@/features/auth/pages/LoginPage"
import { RegisterPage } from "@/features/auth/pages/RegisterPage"
import { DashboardPage } from "@/features/auth/pages/DashboardPage"
import { TasksPage } from "@/features/tasks/pages/TasksPage"
import { HabitsPage } from "@/features/habits/pages/HabitsPage"
import { FocusPage } from "@/features/focus/pages/FocusPage"
import { ExplorationPage } from "@/features/exploration/pages/ExplorationPage"
import { InventoryPage } from "@/features/inventory/pages/InventoryPage"
import { ProfilePage } from "@/features/profile/pages/ProfilePage"
import { NavBar } from "@/components/shared/NavBar"
import { ProtectedRoute } from "@/app/ProtectedRoute"

function SessionLoader() {
  const setSession = useAuthStore((state) => state.setSession)

  useEffect(() => {
    const { data: authListener } = supabase.auth.onAuthStateChange((_, session) => {
      setSession(session)
    })

    return () => {
      authListener.subscription.unsubscribe()
    }
  }, [setSession])

  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: async () => {
      const { data, error } = await supabase.auth.getSession()
      if (error) {
        throw error
      }
      setSession(data.session)
      return data.session
    },
    staleTime: Infinity,
    cacheTime: Infinity,
    refetchOnWindowFocus: false,
  })

  if (sessionQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#090909] text-[#e8dcc8]">
        <div className="flex flex-col items-center gap-3 rounded-3xl border border-[#4a7c59]/20 bg-[#141414]/90 p-8 text-center shadow-[0_0_60px_rgba(0,0,0,0.45)]">
          <div className="h-12 w-12 animate-pulse rounded-full bg-[#4a7c59]/50" />
          <p className="text-base text-[#d4c5a9]">Reestablishing the signal...</p>
        </div>
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<NavBar />}></Route>
      <Route
        path="/login"
        element={
          <AuthShell>
            <LoginPage />
          </AuthShell>
        }
      />
      <Route
        path="/register"
        element={
          <AuthShell>
            <RegisterPage />
          </AuthShell>
        }
      />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <DashboardPage />
            </>
          </ProtectedRoute>
        }
      />

      <Route
        path="/tasks"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <TasksPage />
            </>
          </ProtectedRoute>
        }
      />

      <Route
        path="/habits"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <HabitsPage />
            </>
          </ProtectedRoute>
        }
      />

      <Route
        path="/focus"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <FocusPage />
            </>
          </ProtectedRoute>
        }
      />

      <Route
        path="/exploration"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <ExplorationPage />
            </>
          </ProtectedRoute>
        }
      />

      <Route
        path="/inventory"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <InventoryPage />
            </>
          </ProtectedRoute>
        }
      />

      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <>
              <NavBar />
              <ProfilePage />
            </>
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<Navigate replace to="/dashboard" />} />
      <Route path="*" element={<Navigate replace to="/login" />} />
    </Routes>
  )
}

export function AppRoutes() {
  return <SessionLoader />
}
