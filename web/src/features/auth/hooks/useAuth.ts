import { useMutation, useQuery } from "@tanstack/react-query"
import { supabase } from "@/lib/supabase"
import { apiClient } from "@/lib/api"
import { useAuthStore } from "@/stores/auth"
import type { LoginFormValues, RegisterFormValues } from "@/features/auth/schemas/auth"
import type { Session } from "@supabase/supabase-js"
import type { AuthProfile } from "@/features/auth/types"

async function getCurrentSession(): Promise<Session | null> {
  const { data, error } = await supabase.auth.getSession()
  if (error) {
    throw error
  }
  return data.session
}

export function useLogin() {
  const setSession = useAuthStore((state) => state.setSession)

  return useMutation({
    mutationFn: async (payload: LoginFormValues) => {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: payload.email,
        password: payload.password,
      })

      if (error) {
        throw error
      }

      const session = data.session ?? (await getCurrentSession())
      if (!session) {
        throw new Error("Unable to establish session")
      }

      console.log("[Auth] Login successful", {
        userId: session.user.id,
        hasAccessToken: !!session.access_token,
      })

      setSession(session)
      return session
    },
  })
}

export function useRegister() {
  const setSession = useAuthStore((state) => state.setSession)

  return useMutation({
    mutationFn: async (payload: RegisterFormValues) => {
      const { data, error } = await supabase.auth.signUp(
        {
          email: payload.email,
          password: payload.password,
        },
        {
          data: {
            display_name: payload.fullName,
          },
        }
      )

      if (error) {
        throw error
      }

      const session = data.session ?? (await getCurrentSession())
      if (session) {
        setSession(session)
      }

      return data
    },
  })
}

export function useSignOut() {
  const clearAuth = useAuthStore((state) => state.clearAuth)

  return useMutation({
    mutationFn: async () => {
      const { error } = await supabase.auth.signOut()
      if (error) {
        throw error
      }
      clearAuth()
    },
  })
}

export function useOAuthSignIn() {
  return async function signInWithGoogle(redirectTo?: string) {
    const opts: any = {}
    if (redirectTo) opts.redirectTo = redirectTo

    const { data, error } = await supabase.auth.signInWithOAuth({ provider: "google", options: opts })
    if (error) throw error
    return data
  }
}

export function useProfile() {
  const session = useAuthStore((state) => state.session)
  const setProfile = useAuthStore((state) => state.setProfile)
  const setCharacter = useAuthStore((state) => state.setCharacter)
  const setOnboardingCompleted = useAuthStore((state) => state.setOnboardingCompleted)

  return useQuery({
    queryKey: ["profile", "me"],
    queryFn: async () => {
      const profile = await apiClient<AuthProfile>("/profile/me")
      setProfile(profile)
      setOnboardingCompleted(profile.onboarding_completed)
      return profile
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    enabled: !!session, // Only run when session exists
  })
}
