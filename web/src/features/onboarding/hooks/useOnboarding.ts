import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { useAuthStore } from "@/stores/auth"
import type { OnboardingQuestion, OnboardingStatus, OnboardingSubmitResponse } from "@/features/onboarding/types"
import type { OnboardingSubmitFormValue } from "@/features/onboarding/schemas/questionnaire"

export function useOnboardingQuestions() {
  const session = useAuthStore((state) => state.session)

  return useQuery({
    queryKey: ["onboarding", "questions"],
    queryFn: async () => {
      const questions = await apiClient<OnboardingQuestion[]>("/profile/onboarding")
      return questions.sort((a, b) => a.question_order - b.question_order)
    },
    staleTime: Infinity,
    cacheTime: Infinity,
    enabled: !!session, // Only run when session exists
  })
}

export function useOnboardingStatus() {
  const session = useAuthStore((state) => state.session)

  return useQuery({
    queryKey: ["onboarding", "status"],
    queryFn: () => apiClient<OnboardingStatus>("/profile/onboarding/status"),
    staleTime: 1000 * 60 * 5, // 5 minutes
    enabled: !!session, // Only run when session exists
  })
}

export function useSubmitOnboarding() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: OnboardingSubmitFormValue) =>
      apiClient<OnboardingSubmitResponse>("/profile/onboarding", {
        method: "POST",
        body: payload,
      }),
    onSuccess: async () => {
      // Invalidate status and profile queries so they refetch
      await queryClient.invalidateQueries({ queryKey: ["onboarding", "status"] })
      await queryClient.invalidateQueries({ queryKey: ["profile", "me"] })
    },
  })
}
