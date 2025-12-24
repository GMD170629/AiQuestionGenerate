"""
任务进度推送管理器
使用 asyncio.Queue 实现任务进度的实时推送
"""

# 注意：此文件已迁移到 app/core/，导入路径保持不变以保持向后兼容

import asyncio
from typing import Dict, Optional, Any
from datetime import datetime


class TaskProgressManager:
    """
    任务进度管理器
    为每个任务维护一个进度更新队列，支持多个客户端同时订阅
    """
    
    def __init__(self):
        # 存储每个任务的进度更新队列
        # 格式: {task_id: [asyncio.Queue, ...]}
        self._task_queues: Dict[str, list] = {}
        # 存储每个任务的最后进度状态（用于新连接的客户端获取初始状态）
        self._task_states: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def register_queue(self, task_id: str) -> asyncio.Queue:
        """
        为任务注册一个新的进度队列（用于新的客户端连接）
        
        Args:
            task_id: 任务 ID
            
        Returns:
            进度更新队列
        """
        async with self._lock:
            if task_id not in self._task_queues:
                self._task_queues[task_id] = []
            
            queue = asyncio.Queue()
            self._task_queues[task_id].append(queue)
            
            return queue
    
    async def unregister_queue(self, task_id: str, queue: asyncio.Queue):
        """
        取消注册进度队列（客户端断开连接时）
        
        Args:
            task_id: 任务 ID
            queue: 要移除的队列
        """
        async with self._lock:
            if task_id in self._task_queues:
                try:
                    self._task_queues[task_id].remove(queue)
                    # 如果该任务没有活跃的队列了，清理状态
                    if len(self._task_queues[task_id]) == 0:
                        # 保留状态一段时间，以便新连接可以获取最后状态
                        # 这里不立即删除，让状态保留一段时间
                        pass
                except ValueError:
                    pass  # 队列不在列表中
    
    async def push_progress(self, task_id: str, progress: float, 
                           current_file: Optional[str] = None,
                           message: Optional[str] = None,
                           status: Optional[str] = None):
        """
        推送任务进度更新
        
        Args:
            task_id: 任务 ID
            progress: 进度值（0.0-1.0）
            current_file: 当前处理的文件（可选）
            message: 进度消息（可选）
            status: 任务状态（可选）
        """
        # 确保进度在有效范围内
        progress = max(0.0, min(1.0, progress))
        
        # 更新最后状态
        async with self._lock:
            self._task_states[task_id] = {
                "progress": progress,
                "current_file": current_file,
                "message": message,
                "status": status,
                "updated_at": datetime.now().isoformat()
            }
        
        # 构建进度更新数据
        progress_data = {
            "progress": progress,
            "percentage": round(progress * 100, 2),
            "current_file": current_file,
            "message": message,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        # 推送到所有订阅的队列
        async with self._lock:
            if task_id in self._task_queues:
                queues = self._task_queues[task_id].copy()  # 复制列表以避免迭代时修改
                queue_count = len(queues)
                if queue_count > 0:
                    print(f"[进度推送] 任务 {task_id}: 推送到 {queue_count} 个队列, 进度: {progress:.2%}, 状态: {status}, 消息: {message}")
                for queue in queues:
                    try:
                        await queue.put(progress_data)
                    except Exception as e:
                        # 如果推送失败，可能是队列已关闭，忽略错误
                        print(f"[进度推送] 推送进度到队列失败: {e}")
            else:
                # 如果没有订阅的队列，记录警告（但这是正常的，如果客户端还没连接）
                print(f"[进度推送] 任务 {task_id}: 没有订阅的队列（客户端可能还未连接）")
    
    async def get_last_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务的最后状态（用于新连接的客户端获取初始状态）
        
        Args:
            task_id: 任务 ID
            
        Returns:
            最后状态字典，如果不存在则返回 None
        """
        async with self._lock:
            return self._task_states.get(task_id)
    
    async def cleanup_task(self, task_id: str):
        """
        清理任务的所有队列和状态（任务完成后调用）
        
        Args:
            task_id: 任务 ID
        """
        async with self._lock:
            if task_id in self._task_queues:
                # 清空所有队列
                for queue in self._task_queues[task_id]:
                    try:
                        # 尝试清空队列
                        while not queue.empty():
                            try:
                                queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                    except Exception:
                        pass
                del self._task_queues[task_id]
            
            # 保留状态一段时间，以便新连接可以获取最后状态
            # 这里可以选择保留或删除
            # if task_id in self._task_states:
            #     del self._task_states[task_id]


# 全局进度管理器实例
task_progress_manager = TaskProgressManager()

