import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useSignOut, useProfile } from "@/features/auth/hooks/useAuth"
import { QuestionnaireFlow } from "@/features/onboarding/components/QuestionnaireFlow"
import { DashboardLayout } from "@/features/dashboard/components/DashboardLayout"
import { useAuthStore } from "@/stores/auth"

export function DashboardPage() {
  const navigate = useNavigate()
  const profile = useAuthStore((state) => state.profile)
  const character = useAuthStore((state) => state.character)
  const onboardingCompleted = useAuthStore((state) => state.onboardingCompleted)
  const session = useAuthStore((state) => state.session)
  const signOutMutation = useSignOut()
  const profileQuery = useProfile()

  useEffect(() => {
    if (signOutMutation.isSuccess) {
      navigate("/login", { replace: true })
    }
  }, [navigate, signOutMutation.isSuccess])

  if (profileQuery.isLoading) {
    return (
      <div className="min-h-screen bg-[#090909] flex items-center justify-center px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
        <div className="flex flex-col items-center gap-3">
          <div className="h-12 w-12 animate-pulse rounded-full bg-[#4a7c59]/50" />
          <p className="text-sm text-[#d4c5a9]">Loading your profile...</p>
        </div>
      </div>
    )
  }

  // Show questionnaire if not completed
  if (!onboardingCompleted) {
    return (
      <div className="min-h-screen bg-[#090909] px-4 py-12 text-[#e8dcc8] sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl space-y-8">
          <div className="rounded-[2rem] border border-[#4a7c59]/20 bg-[#111111]/95 p-8 shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
            <p className="text-sm uppercase tracking-[0.3em] text-[#c17f24]/70">Character origin</p>
            <h1 className="mt-3 text-4xl font-semibold text-[#e8dcc8]">Who are you?</h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-[#d4c5a9]/80">
              Answer a few questions to determine which survival archetype best represents you.
              Your answers will unlock your unique character with special abilities and traits.
            </p>
          </div>

          <Card className="rounded-[1.75rem] border border-[#4a7c59]/20 bg-[#141414]/95 shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
            <CardContent className="px-8 py-10 sm:px-10">
              <QuestionnaireFlow
                onComplete={() => {
                  profileQuery.refetch()
                }}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  // Show main dashboard if onboarding completed
  // Render the full aggregated dashboard layout which fetches data from /dashboard/me
  // The layout handles loading/error states and composes shared widgets.
  return <DashboardLayout />
}
