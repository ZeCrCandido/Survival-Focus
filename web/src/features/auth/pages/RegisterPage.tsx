import { useEffect } from "react"
import { Link, Navigate, useNavigate } from "react-router-dom"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { registerSchema, type RegisterFormValues } from "@/features/auth/schemas/auth"
import { useRegister } from "@/features/auth/hooks/useAuth"
import { useAuthStore } from "@/stores/auth"

export function RegisterPage() {
  const navigate = useNavigate()
  const session = useAuthStore((state) => state.session)
  const registerMutation = useRegister()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      fullName: "",
      email: "",
      password: "",
      confirmPassword: "",
    },
  })

  useEffect(() => {
    if (registerMutation.isSuccess && registerMutation.data?.session) {
      navigate("/dashboard", { replace: true })
    }
  }, [navigate, registerMutation.data, registerMutation.isSuccess])

  if (session) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <div className="grid gap-10 sm:grid-cols-[1.05fr_0.95fr]">
      <section className="space-y-6 rounded-[1.75rem] border border-[#4a7c59]/20 bg-[#181818]/90 p-8 text-[#d4c5a9] shadow-[0_18px_80px_-44px_rgba(0,0,0,0.85)] sm:p-10">
        <span className="inline-flex items-center gap-2 rounded-full bg-[#4a7c59]/10 px-4 py-2 text-xs uppercase tracking-[0.3em] text-[#e8dcc8]/80">
          New recruit
        </span>
        <div className="space-y-3">
          <h2 className="text-3xl font-semibold text-[#e8dcc8]">Forge your identity</h2>
          <p className="max-w-xl text-sm leading-7 text-[#d4c5a9]/80">
            Register with your email and a strong password. Your display name will be saved in your profile and synced automatically.
          </p>
        </div>
        <div className="rounded-3xl border border-[#8b1a1a]/20 bg-[#111111]/90 p-6">
          <div className="space-y-4 text-sm text-[#d4c5a9]/80">
            <p>Already have a bunker account? <Link to="/login" className="text-[#c17f24] hover:text-[#e6a817]">Sign in here</Link>.</p>
            <p>Supabase will create your profile record automatically on signup.</p>
          </div>
        </div>
      </section>

      <Card className="rounded-[1.75rem] border border-[#4a7c59]/20 bg-[#111111]/95 text-[#e8dcc8] shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
        <CardHeader className="px-8 pt-8 text-left sm:px-10">
          <CardTitle className="text-2xl font-semibold">Register</CardTitle>
        </CardHeader>
        <CardContent className="px-8 pb-8 sm:px-10">
          <form className="space-y-5" onSubmit={handleSubmit((values) => registerMutation.mutate(values))}>
            <div className="space-y-3">
              <label htmlFor="fullName" className="block text-sm font-medium text-[#d4c5a9]">
                Display name
              </label>
              <Input
                id="fullName"
                type="text"
                placeholder="Avery Rogue"
                autoComplete="name"
                {...register("fullName")}
                aria-invalid={errors.fullName ? "true" : "false"}
              />
              {errors.fullName && <p className="text-sm text-[#c0392b]">{errors.fullName.message}</p>}
            </div>

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

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-3">
                <label htmlFor="password" className="block text-sm font-medium text-[#d4c5a9]">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  {...register("password")}
                  aria-invalid={errors.password ? "true" : "false"}
                />
                {errors.password && <p className="text-sm text-[#c0392b]">{errors.password.message}</p>}
              </div>
              <div className="space-y-3">
                <label htmlFor="confirmPassword" className="block text-sm font-medium text-[#d4c5a9]">
                  Confirm password
                </label>
                <Input
                  id="confirmPassword"
                  type="password"
                  placeholder="••••••••"
                  autoComplete="new-password"
                  {...register("confirmPassword")}
                  aria-invalid={errors.confirmPassword ? "true" : "false"}
                />
                {errors.confirmPassword && (
                  <p className="text-sm text-[#c0392b]">{errors.confirmPassword.message}</p>
                )}
              </div>
            </div>

            <div className="space-y-4">
              <Button
                type="submit"
                className="w-full bg-[#6aab7e] text-[#111111] hover:bg-[#4a7c59] focus-visible:ring-ring/70"
                disabled={registerMutation.isLoading}
              >
                {registerMutation.isLoading ? "Preparing your kit..." : "Create account"}
              </Button>
              {registerMutation.isSuccess && !registerMutation.data?.session && (
                <div className="rounded-2xl border border-[#4a7c59]/30 bg-[#4a7c59]/10 px-4 py-3 text-sm text-[#e8dcc8]">
                  Registration succeeded. Check your inbox for a confirmation link before signing in.
                </div>
              )}
              {registerMutation.isError && (
                <div className="rounded-2xl border border-[#c0392b]/30 bg-[#8b1a1a]/10 px-4 py-3 text-sm text-[#e8dcc8]">
                  {registerMutation.error instanceof Error ? registerMutation.error.message : "Unable to register"}
                </div>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
