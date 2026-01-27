/**
 * 导出工具函数
 * 用于将题目导出为 Markdown 格式
 */

import { Question } from '@/types/question'
import { getApiUrl } from '@/lib/api'

/**
 * 格式化答案/解析内容，避免 Markdown 列表格式冲突
 * 当内容以数字或符号开头时，添加转义或格式化处理
 * 
 * @param text 原始文本
 * @returns 格式化后的文本
 */
function formatAnswerForMarkdown(text: string): string {
  if (!text) return text
  
  // 按行处理
  const lines = text.split('\n')
  const formattedLines: string[] = []
  
  lines.forEach((line) => {
    const trimmedLine = line.trim()
    
    if (trimmedLine.length === 0) {
      // 空行
      formattedLines.push('')
      return
    }
    
    // 检测是否可能是 Markdown 列表格式
    // 匹配：数字 + 点/括号/顿号 + 空格 + 内容
    const listPattern = /^(\d+)([\.\)、])\s+(.+)$/
    const match = trimmedLine.match(listPattern)
    
    if (match) {
      // 如果匹配到列表格式，在行首添加转义字符或缩进，避免被识别为 Markdown 列表
      // 使用反斜杠转义数字和点，或者使用缩进
      // 这里使用缩进方式，更易读
      formattedLines.push(`  ${trimmedLine}`)
    } else if (/^[-*+]\s/.test(trimmedLine)) {
      // 如果以 Markdown 无序列表符号开头，也添加缩进
      formattedLines.push(`  ${trimmedLine}`)
    } else {
      // 普通文本行
      formattedLines.push(trimmedLine)
    }
  })
  
  return formattedLines.join('\n')
}

/**
 * 将难度转换为数字
 * @param difficulty 难度等级
 * @returns 难度数字（1=简单，2=中等，3=困难）
 */
function difficultyToNumber(difficulty: string): number {
  switch (difficulty) {
    case '简单':
      return 1
    case '中等':
      return 2
    case '困难':
      return 3
    default:
      return 2 // 默认中等
  }
}

/**
 * 章节信息接口
 */
interface ChapterInfo {
  chapter_id: string
  file_id: string
  name: string
  level: number
  display_order: number
  chunk_ids: number[]
}

/**
 * 按照图书章节顺序对题目列表进行排序
 * 根据章节的display_order和chunk顺序排序
 * @param questions 题目列表
 * @returns 排序后的题目列表（Promise）
 */
async function sortQuestionsByChapterOrder(questions: Question[]): Promise<Question[]> {
  if (questions.length === 0) {
    return questions
  }
  
  // 按file_id分组题目
  const questionsByFile = new Map<string, Question[]>()
  for (const question of questions) {
    const fileId = question.file_id || ''
    if (!questionsByFile.has(fileId)) {
      questionsByFile.set(fileId, [])
    }
    questionsByFile.get(fileId)!.push(question)
  }
  
  // 为每个文件获取章节信息
  const chapterMap = new Map<string, Map<string, ChapterInfo>>() // fileId -> (chapterName -> ChapterInfo)
  
  for (const fileId of questionsByFile.keys()) {
    if (!fileId) continue
    
    try {
      // 获取文件的章节列表
      const response = await fetch(getApiUrl(`/files/${fileId}/chapters/flat`))
      if (response.ok) {
        const data = await response.json()
        const chapters: ChapterInfo[] = data.chapters || []
        
        // 建立章节名称到章节信息的映射
        const fileChapterMap = new Map<string, ChapterInfo>()
        for (const chapter of chapters) {
          fileChapterMap.set(chapter.name, chapter)
        }
        chapterMap.set(fileId, fileChapterMap)
      }
    } catch (error) {
      console.warn(`获取文件 ${fileId} 的章节信息失败:`, error)
    }
  }
  
  // 为每个题目计算排序键
  const questionsWithSortKey = questions.map(question => {
    const fileId = question.file_id || ''
    const chapterName = question.chapter || ''
    const fileChapterMap = chapterMap.get(fileId)
    
    let sortKey: number[] = [999999] // 默认放在最后
    
    if (fileChapterMap && chapterName) {
      const chapterInfo = fileChapterMap.get(chapterName)
      if (chapterInfo) {
        // 使用章节的level和display_order作为排序键
        // level越小越靠前，display_order越小越靠前
        sortKey = [chapterInfo.level, chapterInfo.display_order]
      }
    }
    
    return { question, sortKey }
  })
  
  // 排序
  questionsWithSortKey.sort((a, b) => {
    // 先按file_id排序（不同文件的题目分开）
    const fileIdA = a.question.file_id || ''
    const fileIdB = b.question.file_id || ''
    if (fileIdA !== fileIdB) {
      return fileIdA.localeCompare(fileIdB)
    }
    
    // 再按章节排序键排序
    const minLength = Math.min(a.sortKey.length, b.sortKey.length)
    for (let i = 0; i < minLength; i++) {
      if (a.sortKey[i] !== b.sortKey[i]) {
        return a.sortKey[i] - b.sortKey[i]
      }
    }
    
    // 如果排序键相同，保持原有顺序
    return 0
  })
  
  return questionsWithSortKey.map(item => item.question)
}

/**
 * 将题目列表导出为 Markdown 格式（按照试题上传模板格式）
 * 
 * @param questions 题目列表
 * @param options 导出选项
 * @returns Markdown 格式的字符串
 */
export function exportQuestionsToMarkdown(
  questions: Question[],
  options?: {
    title?: string
    sourceFile?: string
    chapter?: string
    includeAnswer?: boolean
    includeExplanation?: boolean
  }
): string {
  let content = ''

  // 导出题目
  questions.forEach((q) => {
    // 获取难度数字
    const difficultyNum = difficultyToNumber(q.difficulty)
    
    // 获取章节信息（优先使用题目的chapter字段，否则使用传入的chapter参数）
    const chapter = q.chapter || options?.chapter || ''
    
    // 编程题特殊处理：需要提取题目名称
    if (q.type === '编程题') {
      // 从题干中提取题目名称（取到第一个句号或前30个字符）
      let titleName = q.stem
      const firstPeriod = q.stem.indexOf('。')
      const firstDot = q.stem.indexOf('.')
      const firstBreak = Math.min(
        firstPeriod > 0 ? firstPeriod : q.stem.length,
        firstDot > 0 ? firstDot : q.stem.length
      )
      if (firstBreak < q.stem.length && firstBreak <= 30) {
        titleName = q.stem.substring(0, firstBreak + 1)
      } else if (q.stem.length > 30) {
        titleName = q.stem.substring(0, 30) + '...'
      }
      
      // 题目头部：[题型][难度:数字][分数:5.0]题目名称
      content += `[${q.type}][难度:${difficultyNum}][分数:5.0]${titleName}\n`
      content += '\n'
      
      // 题目描述（使用完整题干）
      content += `[题目描述]${q.stem}\n`
      content += '\n'
    } else {
      // 其他题型：题目头部：[题型][难度:数字][分数:5.0]题目内容
      content += `[${q.type}][难度:${difficultyNum}][分数:5.0]${q.stem}\n`
      content += '\n'
    }

    // 选项（仅选择题）
    if (q.options && q.options.length > 0) {
      q.options.forEach((option, idx) => {
        const label = String.fromCharCode(65 + idx) // A, B, C, D...
        content += `[${label}]${option}\n`
        content += '\n'
      })
    }

    // 编程题特殊处理：输入输出说明和样例（需要在答案之前）
    if (q.type === '编程题' && q.test_cases) {
      const tc = q.test_cases
      
      // 输入说明
      if (tc.input_description) {
        content += `[输入说明]${tc.input_description}\n`
        content += '\n'
      }
      
      // 输出说明
      if (tc.output_description) {
        content += `[输出说明]${tc.output_description}\n`
        content += '\n'
      }
      
      // 输入样例和输出样例（支持多个样例）
      if (tc.input_cases && tc.input_cases.length > 0) {
        tc.input_cases.forEach((inputCase, idx) => {
          const sampleNum = tc.input_cases!.length > 1 ? `${idx + 1}` : ''
          content += `[输入样例${sampleNum}]${inputCase}\n`
          content += '\n'
          if (tc.output_cases && tc.output_cases[idx]) {
            content += `[输出样例${sampleNum}]${tc.output_cases[idx]}\n`
            content += '\n'
          }
        })
      }
    }

    // 答案
    if (q.type === '单选题' || q.type === '多选题') {
      // 选择题：答案格式为选项字母，如 "A" 或 "A,B" 或 "CD"
      const answerLabels = q.answer.split(/[,，;；\s]/).map(a => a.trim().toUpperCase()).filter(a => a)
      // 去除重复并排序
      const uniqueAnswers = Array.from(new Set(answerLabels))
      content += `[答案]${uniqueAnswers.join('')}\n`
    } else if (q.type === '判断题') {
      // 判断题：答案格式为 "正确" 或 "错误"
      content += `[答案]${q.answer}\n`
    } else if (q.type === '填空题') {
      // 填空题：多空答案用 | 分隔，需要转换为【1】【2】格式
      const answers = q.answer.split('|').map(a => a.trim()).filter(a => a)
      if (answers.length > 1) {
        // 多空题：格式为【1】答案1 【2】答案2
        const formattedAnswers = answers.map((ans, idx) => `【${idx + 1}】${ans}`).join(' ')
        content += `[答案]${formattedAnswers}\n`
      } else {
        // 单空题：直接使用答案
        content += `[答案]${q.answer}\n`
      }
    } else {
      // 简答题、编程题：直接使用答案内容
      // 对于编程题，需要转义代码中的 # 符号
      let answerContent = q.answer
      if (q.type === '编程题') {
        // 转义代码中的 # 为 \#
        answerContent = answerContent.replace(/#/g, '\\#')
      }
      content += `[答案]\n`
      content += `${answerContent}\n`
    }
    content += '\n'

    // 章节信息
    if (chapter) {
      content += `[章节]${chapter}\n`
      content += '\n'
    }

    // 解析内容（编程题使用[题解]，其他使用[解析]）
    if (q.explain) {
      const formattedExplanation = formatAnswerForMarkdown(q.explain)
      if (q.type === '编程题') {
        content += `[题解]${formattedExplanation}\n`
      } else {
        content += `[解析]${formattedExplanation}\n`
      }
      content += '\n'
    }

    // 题目之间空两行
    content += '\n'
  })

  return content
}

/**
 * 下载 Markdown 文件
 * 
 * @param content Markdown 内容
 * @param filename 文件名（不含扩展名）
 */
export function downloadMarkdown(content: string, filename: string = '习题集'): void {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  
  // 生成文件名，包含时间戳
  const timestamp = new Date().getTime()
  const safeFilename = filename.replace(/[^a-zA-Z0-9\u4e00-\u9fa5_-]/g, '_')
  a.download = `${safeFilename}_${timestamp}.md`
  
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * 导出题目为 Markdown 并下载
 * 
 * @param questions 题目列表
 * @param options 导出选项
 */
export async function exportAndDownload(
  questions: Question[],
  options?: {
    title?: string
    sourceFile?: string
    chapter?: string
    includeAnswer?: boolean
    includeExplanation?: boolean
    filename?: string
  }
): Promise<void> {
  // 按照图书章节顺序排序题目（根据章节的display_order和chunk顺序）
  const sortedQuestions = await sortQuestionsByChapterOrder(questions)
  const content = exportQuestionsToMarkdown(sortedQuestions, options)
  const filename = options?.filename || options?.title || '习题集'
  downloadMarkdown(content, filename)
}

