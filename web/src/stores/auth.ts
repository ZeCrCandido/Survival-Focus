import { create } from "zustand"
import type { Session } from "@supabase/supabase-js"
import type { AuthProfile } from "@/features/auth/types"
import type { AvatarType } from "@/features/onboarding/types"

interface AuthState {
  session: Session | null
  profile: AuthProfile | null
  character: AvatarType | null
  onboardingCompleted: boolean
  setSession: (session: Session | null) => void
  setProfile: (profile: AuthProfile | null) => void
  setCharacter: (character: AvatarType | null) => void
  setOnboardingCompleted: (completed: boolean) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  session: null,
  profile: null,
  character: null,
  onboardingCompleted: false,
  setSession: (session) => set({ session }),
  setProfile: (profile) => set({ profile }),
  setCharacter: (character) => set({ character }),
  setOnboardingCompleted: (completed) => set({ onboardingCompleted: completed }),
  clearAuth: () => set({ session: null, profile: null, character: null, onboardingCompleted: false }),
}))
