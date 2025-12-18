'use client'

import { motion } from 'framer-motion'
import { Question } from '@/types/question'
import QuestionCard from './QuestionCard'

interface QuestionListProps {
  questions: Question[]
  title?: string
  emptyMessage?: string
}

export default function QuestionList({ 
  questions, 
  title = '题目列表',
  emptyMessage = '暂无题目'
}: QuestionListProps) {
  if (questions.length === 0) {
    return (
      <div className="w-full max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-16 card"
        >
          <p className="text-lg text-slate-600 dark:text-slate-400 font-medium">{emptyMessage}</p>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-5xl mx-auto">
      {title && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <h2 className="text-2xl md:text-3xl font-bold mb-2 text-slate-900 dark:text-slate-100">
            {title}
          </h2>
          <p className="text-slate-600 dark:text-slate-400 text-base font-medium">
            共 <span className="font-bold text-indigo-600 dark:text-indigo-400">{questions.length}</span> 道题目
          </p>
        </motion.div>
      )}
      
      <div className="space-y-6">
        {questions.map((question, index) => (
          <QuestionCard 
            key={index} 
            question={question} 
            index={index}
          />
        ))}
      </div>
    </div>
  )
}

