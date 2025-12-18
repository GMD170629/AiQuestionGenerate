# 任务持久化与恢复功能说明

## 概述

已实现任务持久化、恢复、暂停和取消功能，确保在 Docker 环境项目重启后，未完成的任务可以继续执行。

## 功能特性

### 1. 任务持久化

- 所有任务状态保存在数据库中（SQLite）
- 任务进度实时更新到数据库
- 项目重启后可以从数据库恢复任务状态

### 2. 任务恢复

- **自动恢复**：项目启动时（`@app.on_event("startup")`）自动检查并恢复未完成的任务
- **恢复策略**：
  - `PENDING` 状态：直接恢复执行
  - `PROCESSING` 状态：重置为 `PENDING` 后恢复执行（因为可能是重启前未完成的任务）
  - `PAUSED` 状态：保持暂停，不自动恢复（需要手动恢复）
  - `COMPLETED`、`FAILED`、`CANCELLED` 状态：不恢复
- **进度恢复**：从上次的进度继续执行，不会重复处理已完成的文件

### 3. 任务暂停

- **API 接口**：`POST /tasks/{task_id}/pause`
- **功能**：
  - 暂停正在执行的任务
  - 更新数据库状态为 `PAUSED`
  - 任务会在下一个检查点暂停（文件或切片处理完成后）
- **状态检查**：任务执行过程中会定期检查暂停状态，如果已暂停则等待恢复

### 4. 任务恢复（从暂停状态）

- **API 接口**：`POST /tasks/{task_id}/resume`
- **功能**：
  - 恢复已暂停的任务
  - 更新数据库状态为 `PROCESSING`
  - 如果任务不在运行，重新启动任务
  - 从上次的进度继续执行

### 5. 任务取消

- **API 接口**：`POST /tasks/{task_id}/cancel`
- **功能**：
  - 取消正在执行的任务
  - 更新数据库状态为 `CANCELLED`
  - 取消异步任务对象
  - 任务会在下一个检查点停止执行

## 实现细节

### 任务管理器 (`task_manager.py`)

- `TaskManager` 类：管理正在执行的任务
- 使用 `asyncio.Event` 实现暂停/恢复机制
- 使用 `asyncio.Task` 跟踪任务对象，支持取消

### 任务执行逻辑 (`main.py`)

- `process_full_textbook_task()` 函数：
  - 在关键检查点调用 `task_manager.check_and_wait()` 检查状态
  - 支持从上次进度继续执行
  - 处理 `asyncio.CancelledError` 异常

### 状态检查点

任务在以下位置检查状态：
1. 开始处理每个文件前
2. 开始处理每个切片前
3. 每个切片生成题目后

### 数据库状态

任务状态包括：
- `PENDING`：等待中
- `PROCESSING`：执行中
- `PAUSED`：已暂停
- `COMPLETED`：已完成
- `FAILED`：失败
- `CANCELLED`：已取消

## API 接口

### 暂停任务
```http
POST /tasks/{task_id}/pause
```

### 恢复任务
```http
POST /tasks/{task_id}/resume
```

### 取消任务
```http
POST /tasks/{task_id}/cancel
```

## 使用示例

### 暂停任务
```python
response = requests.post(f"http://localhost:8000/tasks/{task_id}/pause")
```

### 恢复任务
```python
response = requests.post(f"http://localhost:8000/tasks/{task_id}/resume")
```

### 取消任务
```python
response = requests.post(f"http://localhost:8000/tasks/{task_id}/cancel")
```

## 注意事项

1. **任务恢复**：项目重启后，`PROCESSING` 状态的任务会被重置为 `PENDING` 并恢复执行
2. **进度恢复**：任务从上次的进度继续执行，已处理的文件不会重复处理
3. **暂停状态**：暂停的任务不会在项目重启时自动恢复，需要手动调用恢复接口
4. **取消操作**：取消操作是异步的，任务会在下一个检查点停止
5. **状态一致性**：任务状态同时保存在数据库和内存中，确保一致性

## 测试建议

1. 启动一个任务，观察进度更新
2. 暂停任务，验证任务停止
3. 恢复任务，验证任务继续执行
4. 取消任务，验证任务停止
5. 重启项目，验证未完成的任务自动恢复

