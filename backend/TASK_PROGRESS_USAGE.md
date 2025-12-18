# 任务进度推送功能使用说明

## 概述

已实现实时任务进度推送功能，支持通过 Server-Sent Events (SSE) 实时推送任务进度更新。

## 后端实现

### 1. 进度管理器 (`task_progress.py`)

`TaskProgressManager` 类负责管理所有任务的进度更新队列：

- 为每个任务维护多个客户端连接队列
- 支持推送进度更新到所有订阅的客户端
- 保存最后状态，供新连接的客户端获取初始状态

### 2. API 接口

#### 创建任务
```http
POST /tasks
Content-Type: application/json

{
  "textbook_id": "textbook-123",
  "total_files": 10
}
```

#### 获取任务进度（SSE）
```http
GET /tasks/{task_id}/progress
```

返回 Server-Sent Events 流，实时推送进度更新。

#### 更新任务进度
```http
PUT /tasks/{task_id}
Content-Type: application/json

{
  "progress": 0.5,
  "current_file": "第一章.md",
  "status": "PROCESSING"
}
```

### 3. 在生成任务中使用

```python
from database import db
from task_progress import task_progress_manager

async def generate_questions_task(task_id: str, textbook_id: str, file_ids: List[str]):
    # 1. 创建任务
    db.create_task(task_id, textbook_id, len(file_ids))
    
    # 2. 更新状态为处理中
    db.update_task_status(task_id, "PROCESSING")
    
    try:
        # 3. 遍历文件，更新进度
        for index, file_id in enumerate(file_ids):
            file_info = db.get_file(file_id)
            filename = file_info.get("filename", file_id)
            
            # 计算进度
            progress = (index + 1) / len(file_ids)
            
            # 更新数据库
            db.update_task_progress(task_id, progress, filename)
            
            # 推送进度更新（所有订阅的客户端都会收到）
            await task_progress_manager.push_progress(
                task_id=task_id,
                progress=progress,
                current_file=filename,
                message=f"正在处理: {filename} ({index + 1}/{len(file_ids)})"
            )
            
            # 执行实际的生成逻辑
            # ...
        
        # 4. 任务完成
        db.update_task_status(task_id, "COMPLETED")
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=1.0,
            message="所有文件处理完成",
            status="COMPLETED"
        )
        
    except Exception as e:
        # 5. 任务失败
        db.update_task_status(task_id, "FAILED", str(e))
        await task_progress_manager.push_progress(
            task_id=task_id,
            progress=0.0,
            message=f"任务失败: {str(e)}",
            status="FAILED"
        )
```

## 前端实现

### 使用 TaskProgressMonitor 组件

```tsx
import TaskProgressMonitor from '@/components/TaskProgressMonitor'

function MyComponent() {
  const [taskId, setTaskId] = useState<string | null>(null)
  
  return (
    <div>
      {taskId && (
        <TaskProgressMonitor
          taskId={taskId}
          onComplete={() => {
            console.log('任务完成')
          }}
          onError={(error) => {
            console.error('任务失败:', error)
          }}
        />
      )}
    </div>
  )
}
```

### 组件属性

- `taskId`: 任务 ID（必需）
- `onComplete`: 任务完成时的回调函数（可选）
- `onError`: 任务失败时的回调函数（可选）
- `className`: 自定义 CSS 类名（可选）

### 进度数据格式

```typescript
interface TaskProgress {
  progress: number        // 0.0 - 1.0
  percentage: number      // 0 - 100
  current_file?: string   // 当前处理的文件名
  message?: string        // 进度消息
  status?: string         // 任务状态
  timestamp: string       // 时间戳
}
```

## 进度推送格式

SSE 接口返回的数据格式：

```json
{
  "status": "progress",
  "progress": 0.5,
  "percentage": 50.0,
  "current_file": "第一章.md",
  "message": "正在处理: 第一章.md (5/10)",
  "timestamp": "2024-01-01T00:00:00"
}
```

## 注意事项

1. **连接管理**: 前端组件会自动处理连接、重连和错误处理
2. **多客户端支持**: 多个客户端可以同时订阅同一个任务的进度
3. **状态持久化**: 任务状态保存在数据库中，即使客户端断开连接也能获取最后状态
4. **心跳机制**: SSE 连接会定期发送心跳，保持连接活跃

## 示例

完整的使用示例请参考 `backend/task_example.py`。

