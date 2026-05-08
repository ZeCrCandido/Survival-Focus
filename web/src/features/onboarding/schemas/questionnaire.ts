import { z } from "zod"

export const onboardingAnswerSchema = z.object({
  question_id: z.string().uuid("Invalid question ID"),
  answer_index: z.number().int().nonnegative("Invalid answer index"),
})

export const onboardingSubmitSchema = z.object({
  answers: z.array(onboardingAnswerSchema).min(1, "Must answer at least one question"),
})

export type OnboardingAnswerFormValue = z.infer<typeof onboardingAnswerSchema>
export type OnboardingSubmitFormValue = z.infer<typeof onboardingSubmitSchema>
