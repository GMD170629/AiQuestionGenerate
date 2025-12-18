'use client'

import TextbookManager from '@/components/TextbookManager'

export default function TextbooksPage() {
  return (
    <main className="flex min-h-screen flex-col items-center p-8 md:p-24 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-7xl w-full relative">
        <TextbookManager />
      </div>
    </main>
  )
}

