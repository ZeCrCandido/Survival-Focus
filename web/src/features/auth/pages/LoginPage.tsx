import { useEffect, useState } from "react"
import { Link, Navigate, useNavigate } from "react-router-dom"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { loginSchema, type LoginFormValues } from "@/features/auth/schemas/auth"
import { useLogin } from "@/features/auth/hooks/useAuth"
import { useAuthStore } from "@/stores/auth"
import { supabase } from "@/lib/supabase"

export function LoginPage() {
  const navigate = useNavigate()
  const session = useAuthStore((state) => state.session)
  const loginMutation = useLogin()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  })

  useEffect(() => {
    if (loginMutation.isSuccess) {
      navigate("/dashboard", { replace: true })
    }
  }, [loginMutation.isSuccess, navigate])

  const [oauthLoading, setOauthLoading] = useState(false)
  const [oauthError, setOauthError] = useState<string | null>(null)

  async function handleGoogleSignIn() {
    try {
      setOauthError(null)
      setOauthLoading(true)
      const { data, error } = await supabase.auth.signInWithOAuth({ provider: "google", options: { redirectTo: window.location.origin } })
      if (error) throw error
      // For hosted redirect flow, Supabase will redirect the browser; data may be present for popup flows
      console.log("OAuth initiated", data)
    } catch (err: any) {
      setOauthError(err?.message || String(err))
    } finally {
      setOauthLoading(false)
    }
  }

  if (session) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <div className="grid gap-10 sm:grid-cols-[1.05fr_0.95fr]">
      <section className="space-y-6 rounded-[1.75rem] border border-[#8b1a1a]/20 bg-[#181818]/90 p-8 text-[#d4c5a9] shadow-[0_18px_80px_-44px_rgba(0,0,0,0.85)] sm:p-10">
        <span className="inline-flex items-center gap-2 rounded-full bg-[#8b1a1a]/10 px-4 py-2 text-xs uppercase tracking-[0.3em] text-[#e8dcc8]/80">
          Survivor access
        </span>
        <div className="space-y-3">
          <h2 className="text-3xl font-semibold text-[#e8dcc8]">Return to the bunker</h2>
          <p className="max-w-xl text-sm leading-7 text-[#d4c5a9]/80">
            Enter your credentials to rejoin your squad, continue your mission, and keep your progress safe.
          </p>
        </div>
        <div className="rounded-3xl border border-[#4a7c59]/20 bg-[#111111]/90 p-6">
          <div className="space-y-4 text-sm text-[#d4c5a9]/80">
            <p>Need an account? <Link to="/register" className="text-[#c17f24] hover:text-[#e6a817]">Create one now</Link>.</p>
            <p>Your Supabase login lets the backend validate every request with a secure JWT token.</p>
          </div>
        </div>
      </section>

      <Card className="rounded-[1.75rem] border border-[#4a7c59]/20 bg-[#111111]/95 text-[#e8dcc8] shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
        <CardHeader className="px-8 pt-8 text-left sm:px-10">
          <CardTitle className="text-2xl font-semibold">Sign in</CardTitle>
        </CardHeader>
        <CardContent className="px-8 pb-8 sm:px-10">
          <div className="mb-4">
            <Button variant="outline" className="w-full mb-2" onClick={handleGoogleSignIn} disabled={oauthLoading}>
              {oauthLoading ? "Opening..." : "Continue with Google"}
            </Button>
            {oauthError && <div className="text-sm text-[#c0392b]">{oauthError}</div>}
          </div>
          <form className="space-y-5" onSubmit={handleSubmit((values) => loginMutation.mutate(values))}>
            <div className="space-y-3">
              <label htmlFor="email" className="block text-sm font-medium text-[#d4c5a9]">
                Email
              </label>
              <Input
                id="email"
                type="email"
                placeholder="hunter@example.com"
                autoComplete="email"
                {...register("email")}
                aria-invalid={errors.email ? "true" : "false"}
              />
              {errors.email && <p className="text-sm text-[#c0392b]">{errors.email.message}</p>}
            </div>

            <div className="space-y-3">
              <label htmlFor="password" className="flex items-center justify-between text-sm font-medium text-[#d4c5a9]">
                <span>Password</span>
                <span className="text-sm text-[#c17f24]/90">Forgot password?</span>
              </label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                autoComplete="current-password"
                {...register("password")}
                aria-invalid={errors.password ? "true" : "false"}
              />
              {errors.password && <p className="text-sm text-[#c0392b]">{errors.password.message}</p>}
            </div>

            <div className="space-y-4">
              <Button
                type="submit"
                className="w-full bg-[#4a7c59] text-[#e8dcc8] hover:bg-[#6aab7e] focus-visible:ring-ring/70"
                disabled={loginMutation.isLoading}
              >
                {loginMutation.isLoading ? "Reestablishing..." : "Enter the bunker"}
              </Button>
              {loginMutation.isError && (
                <div className="rounded-2xl border border-[#c0392b]/30 bg-[#8b1a1a]/10 px-4 py-3 text-sm text-[#e8dcc8]">
                  {loginMutation.error instanceof Error ? loginMutation.error.message : "Unable to sign in"}
                </div>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
