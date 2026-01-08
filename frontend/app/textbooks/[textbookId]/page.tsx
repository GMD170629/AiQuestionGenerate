'use client'

import { useParams } from 'next/navigation'
import TextbookFiles from '@/components/TextbookFiles'

export default function TextbookDetailPage() {
  const params = useParams()
  const textbookId = params?.textbookId as string

  if (!textbookId) {
    return (
      <main className="flex min-h-screen flex-col items-center p-8 md:p-24 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
        <div className="z-10 max-w-7xl w-full relative">
          <div className="text-center py-16">
            <p className="text-lg text-slate-600 dark:text-slate-400">教材 ID 无效</p>
          </div>
        </div>
      </main>
    )
  }

  return (
    <main className="flex min-h-screen flex-col items-center p-8 md:p-24 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-7xl w-full relative">
        <TextbookFiles textbookId={textbookId} />
      </div>
    </main>
  )
}

