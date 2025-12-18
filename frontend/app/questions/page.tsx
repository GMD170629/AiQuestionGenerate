'use client'

import QuestionLibrary from '@/components/QuestionLibrary'

export default function QuestionsPage() {
  return (
    <main className="flex min-h-screen flex-col items-center relative overflow-hidden bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-7xl w-full relative">
        <QuestionLibrary />
      </div>
    </main>
  )
}

