import { UUID } from "crypto"

export type AvatarType = {
  id: string
  name: string
  description: string
  image_url: string | null
  traits: string[]
}

export type OnboardingQuestion = {
  id: string
  question_order: number
  question_text: string
  answers: OnboardingAnswer[]
}

export type OnboardingAnswer = {
  label: string
}

export type OnboardingStatus = {
  completed: boolean
  avatar_type: AvatarType | null
}

export type OnboardingSubmitResponse = {
  message: string
  avatar_type: AvatarType
}
