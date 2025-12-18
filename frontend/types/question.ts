/**
 * 题目相关的 TypeScript 类型定义
 * 对应后端 Pydantic 模型
 */

export type QuestionType = "单选题" | "多选题" | "判断题" | "填空题" | "简答题" | "编程题"
export type Difficulty = "简单" | "中等" | "困难"

/**
 * 编程题测试用例模型
 */
export interface TestCase {
  /** 输入说明 */
  input_description?: string
  
  /** 输出说明 */
  output_description?: string
  
  /** 输入用例列表 */
  input_cases?: string[]
  
  /** 输出用例列表（与输入用例一一对应） */
  output_cases?: string[]
}

/**
 * 题目数据模型
 */
export interface Question {
  /** 题目 ID（数据库中的唯一标识） */
  question_id?: number
  
  /** 文件 ID */
  file_id?: string
  
  /** 题型 */
  type: QuestionType
  
  /** 题干文本 */
  stem: string
  
  /** 选项列表（仅单选题和多选题使用） */
  options?: string[]
  
  /** 正确答案（编程题代码就是答案） */
  answer: string
  
  /** 详细解析 */
  explain: string
  
  /** 代码片段（可选，用于编程题） */
  code_snippet?: string
  
  /** 测试用例（仅编程题使用） */
  test_cases?: TestCase
  
  /** 难度等级 */
  difficulty: Difficulty
  
  /** 所属章节（可选） */
  chapter?: string
  
  /** 来源文件（可选） */
  source_file?: string
  
  /** 创建时间（可选） */
  created_at?: string
}

/**
 * 题目列表模型
 */
export interface QuestionList {
  /** 题目列表 */
  questions: Question[]
  
  /** 题目总数 */
  total: number
  
  /** 来源文件（可选） */
  source_file?: string
  
  /** 所属章节（可选） */
  chapter?: string
}

