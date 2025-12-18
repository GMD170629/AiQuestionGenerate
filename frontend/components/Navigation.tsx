'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Home, BookOpen, Settings, Library, ClipboardList } from 'lucide-react'
import { motion } from 'framer-motion'

export default function Navigation() {
  const pathname = usePathname()
  
  return (
    <nav className="w-full border-b border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-800/80 backdrop-blur-md shadow-sm sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <Link href="/">
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all duration-200 ${
                  pathname === '/'
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/50'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <Home className="h-5 w-5" />
                <span>首页</span>
              </motion.div>
            </Link>
            
            <Link href="/questions">
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all duration-200 ${
                  pathname === '/questions'
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/50'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <BookOpen className="h-5 w-5" />
                <span>题目库</span>
              </motion.div>
            </Link>
            
            <Link href="/textbooks">
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all duration-200 ${
                  pathname === '/textbooks'
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/50'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <Library className="h-5 w-5" />
                <span>教材管理</span>
              </motion.div>
            </Link>
            
            <Link href="/tasks">
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all duration-200 ${
                  pathname === '/tasks'
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/50'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <ClipboardList className="h-5 w-5" />
                <span>任务中心</span>
              </motion.div>
            </Link>
            
            <Link href="/settings">
              <motion.div
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-all duration-200 ${
                  pathname === '/settings'
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/50'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                }`}
              >
                <Settings className="h-5 w-5" />
                <span>设置</span>
              </motion.div>
            </Link>
          </div>
        </div>
      </div>
    </nav>
  )
}

