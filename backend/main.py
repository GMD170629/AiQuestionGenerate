"""
FastAPI 应用主入口
"""

import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database import db
from routers import config, files, questions, textbooks, tasks, question_library, knowledge_graph, knowledge_extraction, test_generation

# 创建 FastAPI 应用
app = FastAPI(title="AI 计算机教材习题生成器", version="1.0.0")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(config.router)
app.include_router(files.router)
app.include_router(questions.router)
app.include_router(question_library.router)
app.include_router(textbooks.router)
app.include_router(tasks.router)
app.include_router(knowledge_graph.router)
app.include_router(knowledge_extraction.router)
app.include_router(test_generation.router)

# 注册开发模式路由（仅在开发模式下可用）
import os
if os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes"):
    from routers import dev
    app.include_router(dev.router)


@app.get("/")
async def root():
    """根路径"""
    return {"message": "AI 计算机教材习题生成器 API"}


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


@app.on_event("startup")
async def startup_event():
    """
    应用启动时恢复未完成的任务
    """
    try:
        # 获取所有未完成的任务（PENDING 或 PROCESSING 状态）
        pending_tasks = db.get_all_tasks(status="PENDING")
        processing_tasks = db.get_all_tasks(status="PROCESSING")
        
        all_unfinished_tasks = pending_tasks + processing_tasks
        
        if all_unfinished_tasks:
            print(f"发现 {len(all_unfinished_tasks)} 个未完成的任务，开始恢复...")
            
            for task_info in all_unfinished_tasks:
                task_id = task_info.get("task_id")
                task_status = task_info.get("status")
                
                # 如果是 PROCESSING 状态，重置为 PENDING（因为可能是重启前未完成的任务）
                if task_status == "PROCESSING":
                    db.update_task_status(task_id, "PENDING", "项目重启，任务待恢复")
                    print(f"任务 {task_id} 状态重置为 PENDING")
                
                # 如果是 PAUSED 状态，保持暂停状态，不自动恢复（需要手动恢复）
                if task_status == "PAUSED":
                    print(f"任务 {task_id} 处于暂停状态，不会自动恢复")
                    continue
                
                # 启动任务恢复
                from services.task_service import process_full_textbook_task
                asyncio.create_task(process_full_textbook_task(task_id))
                print(f"任务 {task_id} 已恢复执行")
        else:
            print("没有未完成的任务需要恢复")
    except Exception as e:
        print(f"恢复任务时发生错误: {e}")
