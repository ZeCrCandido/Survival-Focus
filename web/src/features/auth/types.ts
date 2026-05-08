export type AuthProfile = {
  id: string
  username: string | null
  display_name: string
  avatar_type_id: string | null
  onboarding_completed: boolean
  bio: string | null
  avatar_url: string | null
  created_at: string
  updated_at: string
}

export type AuthUser = {
  id: string
  email: string | null
  phone: string | null
  app_metadata: Record<string, unknown>
  user_metadata: {
    display_name?: string
    [key: string]: unknown
  }
  created_at: string
  role: string
}
