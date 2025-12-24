# 📚 AI 计算机教材习题生成器

基于 AI 的计算机教材习题自动生成工具，支持从 Markdown 教材中提取内容并生成多种类型的习题。系统集成了知识图谱构建、智能题目生成、批量处理等核心功能。

## ✨ 核心功能

- 📄 **文件管理**：支持 Markdown 文件上传、解析、预览和管理
- 📖 **教材管理**：组织多个文件为教材，支持目录结构管理
- 🧠 **知识图谱**：自动提取知识点并构建知识依赖关系图谱
- 🎯 **智能出题**：基于知识点内容自适应生成多种题型（单选、多选、判断、填空、简答、编程）
- 📚 **批量生成**：支持整本教材的自动化批量题目生成
- 📊 **任务管理**：实时任务进度追踪，支持暂停、恢复、取消操作
- 💾 **题目库**：题目持久化存储，支持筛选、搜索和导出
- 🎨 **可视化**：知识图谱可视化展示，支持交互式探索

## 🏗️ 项目结构

```
AiQuestionGenerate/
├── backend/                    # FastAPI 后端
│   ├── app/                   # 应用主目录
│   │   ├── api/              # API 路由
│   │   │   └── v1/
│   │   │       └── endpoints/  # API 端点（文件、题目、任务、知识图谱等）
│   │   ├── core/             # 核心模块（配置、数据库、缓存、任务管理）
│   │   ├── models/           # 数据模型（Pydantic）
│   │   ├── schemas/          # API 请求/响应模型
│   │   ├── services/         # 业务逻辑层（AI、文件、知识图谱等）
│   │   └── utils/            # 工具函数
│   ├── markdown/             # Markdown 解析模块
│   ├── prompts/              # AI 提示词管理
│   ├── data/                 # 数据库文件（SQLite）
│   ├── uploads/              # 上传文件存储目录
│   ├── main.py               # 应用入口（兼容旧版本）
│   ├── requirements.txt      # Python 依赖
│   └── Dockerfile            # Docker 镜像配置
├── frontend/                  # Next.js 前端
│   ├── app/                  # Next.js App Router 页面
│   │   ├── page.tsx          # 首页
│   │   ├── textbooks/        # 教材管理页面
│   │   ├── questions/        # 题目库页面
│   │   ├── tasks/            # 任务管理页面
│   │   ├── knowledge-map/    # 知识图谱页面
│   │   ├── generate/         # 题目生成页面
│   │   └── settings/         # 设置页面
│   ├── components/           # React 组件
│   │   ├── ui/               # 基础 UI 组件
│   │   └── ...               # 功能组件
│   ├── hooks/                # 自定义 Hooks
│   ├── lib/                  # 工具库（API 客户端、主题等）
│   ├── types/                # TypeScript 类型定义
│   ├── package.json          # Node.js 依赖
│   └── Dockerfile            # Docker 镜像配置
├── docs/                      # 项目文档
│   ├── 全书题目生成系统架构与流程.md
│   └── 知识点系统执行流程.md
├── docker-compose.yml         # Docker Compose 配置
├── TODO.md                    # 开发计划
└── README.md                  # 项目说明文档
```

## 🚀 快速开始

### 方式一：使用 Docker Compose（推荐）

1. **启动所有服务**
```bash
docker-compose up -d
```

2. **查看服务状态**
```bash
docker-compose ps
```

3. **查看日志**
```bash
docker-compose logs -f
```

4. **停止服务**
```bash
docker-compose down
```

服务启动后：
- 前端：http://localhost:3000
- 后端 API：http://localhost:8000
- API 文档：http://localhost:8000/docs

### 方式二：本地开发

#### 后端开发

1. **进入后端目录**
```bash
cd backend
```

2. **创建虚拟环境（可选但推荐）**
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **初始化数据库（首次运行）**
```bash
# 数据库会在首次运行时自动创建，无需手动初始化
# 如需重置数据库，可运行：
python reset_database.py
```

5. **启动服务**
```bash
# 方式一：使用 uvicorn 直接启动（推荐开发环境）
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 方式二：使用 main.py（兼容旧版本）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端将在 http://localhost:8000 启动

#### 前端开发

1. **进入前端目录**
```bash
cd frontend
```

2. **安装依赖**
```bash
npm install
```

3. **启动开发服务器**
```bash
npm run dev
```

前端将在 http://localhost:3000 启动

## 📦 技术栈

### 后端
- **FastAPI** - 现代、快速的 Web 框架
- **Uvicorn** - ASGI 服务器
- **Pydantic** - 数据验证和序列化
- **LangChain** - 文档处理和文本分割
- **NetworkX** - 知识图谱构建
- **SQLite** - 轻量级数据库
- **Python 3.11+**

### 前端
- **Next.js 14** - React 框架（App Router）
- **TypeScript** - 类型安全
- **Tailwind CSS** - 样式框架
- **Lucide React** - 图标库
- **vis-network** - 知识图谱可视化
- **react-syntax-highlighter** - 代码高亮
- **react-markdown** - Markdown 渲染

## 🔧 开发说明

### 环境变量

创建 `.env` 文件（在项目根目录）：

```env
# 后端配置
BACKEND_PORT=8000

# 前端配置
# Next.js 需要在环境变量前加 NEXT_PUBLIC_ 前缀才能在客户端使用
NEXT_PUBLIC_API_URL=http://localhost:8000

# Docker Compose 使用的环境变量（不需要 NEXT_PUBLIC_ 前缀）
API_URL=http://localhost:8000

# OpenRouter API 配置（可选，也可以通过前端设置页面配置）
OPENROUTER_API_KEY=your_api_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini

# 开发模式（可选）
DEV_MODE=false
```

**重要提示：**
- 如果使用 Docker Compose，`API_URL` 会被自动转换为 `NEXT_PUBLIC_API_URL` 传递给前端容器
- 如果直接运行前端（不使用 Docker），需要在 `.env.local` 或 `.env` 文件中设置 `NEXT_PUBLIC_API_URL`
- 前端代码已统一使用 `@/lib/api` 中的 `getApiUrl()` 函数，会自动读取环境变量

### 开发模式

开发模式提供了一些便捷的开发工具，包括快速清空所有系统数据的功能。

**启用开发模式：**

1. 设置环境变量 `DEV_MODE=true`
2. 重启后端服务
3. 在设置页面（Settings）将显示"开发模式"部分

**开发模式功能：**

- **清空所有数据**：一键清空所有上传的文件、教材、题目、切片、知识图谱等数据
  - 注意：此操作不可恢复，请谨慎使用
  - AI 配置不会被清空

**安全提示：**

- 开发模式仅在开发环境中使用
- 生产环境请勿启用开发模式
- 清空数据操作会永久删除所有数据（除 AI 配置外）

## 📝 开发计划

详见 [TODO.md](./TODO.md)

## 🏗️ 架构文档

详细的架构文档位于 `docs/` 目录：

- **[全书题目生成系统架构与流程](./docs/全书题目生成系统架构与流程.md)** - 全书题目生成系统的完整架构设计、数据流和 API 接口说明
- **[知识点系统执行流程](./docs/知识点系统执行流程.md)** - 知识点提取和知识图谱构建的执行流程

### 代码组织规范

项目遵循领域驱动设计 (DDD) 和整洁代码 (Clean Code) 准则：

#### 后端架构
- **Controller 层** (`app/api/`) - API 路由入口，仅负责请求处理和响应
- **Service 层** (`app/services/`) - 业务逻辑封装
- **Repository 层** (`app/core/db.py`) - 数据持久化
- **Model 层** (`app/models/`) - 数据模型定义
- **Schema 层** (`app/schemas/`) - API 请求/响应模型

#### 前端架构
- **页面层** (`app/`) - Next.js App Router 页面路由
- **组件层** (`components/`) - 可复用 UI 组件，按功能分目录
- **Hooks 层** (`hooks/`) - 自定义 React Hooks
- **工具层** (`lib/`) - API 客户端、工具函数等

#### AI 提示词管理
- 所有 AI 系统提示词统一存放在 `backend/prompts/` 目录
- 使用 `PromptManager` 统一管理，避免硬编码

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

