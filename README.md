# 📚 AI 计算机教材习题生成器

基于 AI 的计算机教材习题自动生成工具，支持从 Markdown 教材中提取内容并生成多种类型的习题。

## 🏗️ 项目结构

```
QuestionGenerate/
├── backend/          # FastAPI 后端
│   ├── main.py      # 主应用文件
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/        # Next.js 前端
│   ├── app/         # Next.js App Router
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
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

4. **启动服务**
```bash
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
- **Pydantic** - 数据验证
- **Python 3.11+**

### 前端
- **Next.js 14** - React 框架
- **TypeScript** - 类型安全
- **Tailwind CSS** - 样式框架
- **Lucide React** - 图标库

## 🔧 开发说明

### 后端 API 端点

- `GET /` - 根路径，返回欢迎信息
- `GET /health` - 健康检查
- `GET /docs` - Swagger API 文档（自动生成）

### 环境变量

创建 `.env` 文件（如果需要）：

```env
# 后端
BACKEND_PORT=8000

# 前端
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 📝 开发计划

详见 [TODO.md](./TODO.md)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

