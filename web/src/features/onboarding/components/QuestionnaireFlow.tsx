import { useEffect, useState } from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm, Controller } from "react-hook-form"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  useOnboardingQuestions,
  useSubmitOnboarding,
} from "@/features/onboarding/hooks/useOnboarding"
import {
  onboardingSubmitSchema,
  type OnboardingSubmitFormValue,
} from "@/features/onboarding/schemas/questionnaire"
import type { OnboardingQuestion } from "@/features/onboarding/types"

interface QuestionnaireFlowProps {
  onComplete?: () => void
}

export function QuestionnaireFlow({ onComplete }: QuestionnaireFlowProps) {
  const questionsQuery = useOnboardingQuestions()
  const submitMutation = useSubmitOnboarding()
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0)

  const {
    control,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<OnboardingSubmitFormValue>({
    resolver: zodResolver(onboardingSubmitSchema),
    defaultValues: {
      answers: [],
    },
  })

  const answers = watch("answers")

  useEffect(() => {
    if (submitMutation.isSuccess) {
      onComplete?.()
    }
  }, [submitMutation.isSuccess, onComplete])

  if (questionsQuery.isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 animate-pulse rounded-full bg-[#4a7c59]/50" />
          <p className="text-sm text-[#d4c5a9]">Loading personality questionnaire...</p>
        </div>
      </div>
    )
  }

  if (questionsQuery.isError) {
    return (
      <div className="rounded-2xl border border-[#c0392b]/30 bg-[#8b1a1a]/10 p-6 text-center text-[#e8dcc8]">
        <p className="font-medium">Unable to load questionnaire</p>
        <p className="mt-2 text-sm text-[#d4c5a9]/80">
          {questionsQuery.error instanceof Error
            ? questionsQuery.error.message
            : "An unexpected error occurred"}
        </p>
      </div>
    )
  }

  const questions = questionsQuery.data || []
  if (questions.length === 0) {
    return (
      <div className="rounded-2xl border border-[#4a7c59]/30 bg-[#4a7c59]/10 p-6 text-center text-[#e8dcc8]">
        <p>No questions available at this time.</p>
      </div>
    )
  }

  const currentQuestion: OnboardingQuestion = questions[currentQuestionIndex]
  const isLastQuestion = currentQuestionIndex === questions.length - 1
  const progress = ((currentQuestionIndex + 1) / questions.length) * 100

  // Check if current question is answered
  const currentAnswer = answers.find((a) => a.question_id === currentQuestion.id)

  return (
    <div className="w-full space-y-8">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm uppercase tracking-[0.3em] text-[#c17f24]/70">Character origin</p>
          <p className="text-xs text-[#d4c5a9]/60">
            {currentQuestionIndex + 1} of {questions.length}
          </p>
        </div>
        <div className="h-2 w-full rounded-full bg-[#2a2a2a] overflow-hidden">
          <div
            className="h-full bg-[#4a7c59] transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <form
        onSubmit={handleSubmit((data) => submitMutation.mutate(data))}
        className="space-y-8"
      >
        <Card className="rounded-[1.75rem] border border-[#4a7c59]/20 bg-[#111111]/95 shadow-[0_24px_80px_-36px_rgba(0,0,0,0.8)]">
          <CardHeader className="px-8 pt-8 sm:px-10">
            <CardTitle className="text-2xl font-semibold text-[#e8dcc8]">
              {currentQuestion.question_text}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 px-8 pb-8 sm:px-10">
            <Controller
              name="answers"
              control={control}
              render={({ field }) => (
                <div className="space-y-3">
                  {currentQuestion.answers.map((answer, answerIndex) => {
                    const isSelected =
                      currentAnswer?.answer_index === answerIndex
                    return (
                      <button
                        key={answerIndex}
                        type="button"
                        onClick={() => {
                          const newAnswers = field.value.filter(
                            (a) => a.question_id !== currentQuestion.id
                          )
                          newAnswers.push({
                            question_id: currentQuestion.id,
                            answer_index: answerIndex,
                          })
                          field.onChange(newAnswers)
                        }}
                        className={`w-full rounded-2xl border-2 px-6 py-4 text-left transition-all ${
                          isSelected
                            ? "border-[#4a7c59] bg-[#4a7c59]/10 text-[#e8dcc8] shadow-[0_0_24px_rgba(74,124,89,0.3)]"
                            : "border-[#2a2a2a] bg-[#141414]/50 text-[#d4c5a9] hover:border-[#4a7c59]/50 hover:bg-[#1a1a1a]"
                        }`}
                      >
                        {answer.label}
                      </button>
                    )
                  })}
                </div>
              )}
            />
            {errors.answers && (
              <p className="text-sm text-[#c0392b]">{errors.answers.message}</p>
            )}
          </CardContent>
        </Card>

        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => setCurrentQuestionIndex(Math.max(0, currentQuestionIndex - 1))}
            disabled={currentQuestionIndex === 0}
            className="flex-1 rounded-xl border border-[#2a2a2a] bg-[#141414]/50 px-4 py-3 text-sm font-medium text-[#d4c5a9] transition-all hover:border-[#4a7c59]/50 hover:bg-[#1a1a1a] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>

          {isLastQuestion ? (
            <button
              type="submit"
              disabled={
                submitMutation.isLoading ||
                answers.length !== questions.length
              }
              className="flex-1 rounded-xl bg-[#4a7c59] px-4 py-3 text-sm font-medium text-[#e8dcc8] transition-all hover:bg-[#6aab7e] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitMutation.isLoading ? "Assigning archetype..." : "Complete onboarding"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() =>
                setCurrentQuestionIndex(Math.min(questions.length - 1, currentQuestionIndex + 1))
              }
              disabled={!currentAnswer}
              className="flex-1 rounded-xl bg-[#4a7c59] px-4 py-3 text-sm font-medium text-[#e8dcc8] transition-all hover:bg-[#6aab7e] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          )}
        </div>

        {submitMutation.isError && (
          <div className="rounded-2xl border border-[#c0392b]/30 bg-[#8b1a1a]/10 px-4 py-3 text-sm text-[#e8dcc8]">
            {submitMutation.error instanceof Error
              ? submitMutation.error.message
              : "Failed to submit onboarding"}
          </div>
        )}
      </form>
    </div>
  )
}
