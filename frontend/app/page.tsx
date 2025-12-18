'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import FileUpload from '@/components/FileUpload'
import FileManager from '@/components/FileManager'

export default function Home() {
  const [uploadKey, setUploadKey] = useState(0)

  const handleUploadSuccess = () => {
    // 通过改变 key 来触发 FileManager 刷新
    setUploadKey(prev => prev + 1)
  }

  return (
    <main className="flex min-h-screen flex-col items-center p-8 md:p-24 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
      <div className="z-10 max-w-5xl w-full relative">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center mb-12"
        >
          <h1 className="text-4xl md:text-5xl font-bold mb-4 text-slate-900 dark:text-slate-100">
            📚 AI 计算机教材习题生成器
          </h1>
          <p className="text-lg md:text-xl text-slate-700 dark:text-slate-300 font-medium">
            上传 Markdown 教材，自动生成高质量习题
          </p>
        </motion.div>
        
        <div className="space-y-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <FileUpload onUploadSuccess={handleUploadSuccess} />
          </motion.div>
          
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="mt-12"
          >
            <FileManager key={uploadKey} />
          </motion.div>
        </div>
      </div>
    </main>
  )
}

