"""
任务管理器
用于管理正在执行的任务，支持暂停、取消和恢复
"""

# 注意：此文件已迁移到 app/core/，导入路径保持不变以保持向后兼容

import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime


class TaskManager:
    """
    任务管理器
    跟踪正在执行的任务，支持暂停、取消和恢复
    """
    
    def __init__(self):
        # 存储正在执行的任务
        # 格式: {task_id: {"task": asyncio.Task, "cancelled": bool, "paused": bool, "pause_event": asyncio.Event}}
        self._running_tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def register_task(self, task_id: str, task: asyncio.Task):
        """
        注册正在执行的任务
        
        Args:
            task_id: 任务 ID
            task: 异步任务对象
        """
        async with self._lock:
            pause_event = asyncio.Event()
            pause_event.set()  # 初始状态为未暂停
            self._running_tasks[task_id] = {
                "task": task,
                "cancelled": False,
                "paused": False,
                "pause_event": pause_event
            }
    
    async def unregister_task(self, task_id: str):
        """
        取消注册任务（任务完成或失败时）
        
        Args:
            task_id: 任务 ID
        """
        async with self._lock:
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]
    
    async def pause_task(self, task_id: str) -> bool:
        """
        暂停任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功暂停
        """
        async with self._lock:
            if task_id in self._running_tasks:
                self._running_tasks[task_id]["paused"] = True
                self._running_tasks[task_id]["pause_event"].clear()
                return True
        return False
    
    async def resume_task(self, task_id: str) -> bool:
        """
        恢复任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功恢复
        """
        async with self._lock:
            if task_id in self._running_tasks:
                self._running_tasks[task_id]["paused"] = False
                self._running_tasks[task_id]["pause_event"].set()
                return True
        return False
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功取消
        """
        async with self._lock:
            if task_id in self._running_tasks:
                self._running_tasks[task_id]["cancelled"] = True
                self._running_tasks[task_id]["pause_event"].set()  # 确保任务可以继续执行以检查取消状态
                # 取消异步任务
                task = self._running_tasks[task_id]["task"]
                if not task.done():
                    task.cancel()
                return True
        return False
    
    async def is_cancelled(self, task_id: str) -> bool:
        """
        检查任务是否已取消
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否已取消
        """
        async with self._lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id]["cancelled"]
        return False
    
    async def is_paused(self, task_id: str) -> bool:
        """
        检查任务是否已暂停
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否已暂停
        """
        async with self._lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id]["paused"]
        return False
    
    async def wait_if_paused(self, task_id: str):
        """
        如果任务已暂停，等待恢复
        
        Args:
            task_id: 任务 ID
        """
        async with self._lock:
            if task_id not in self._running_tasks:
                return
            pause_event = self._running_tasks[task_id]["pause_event"]
        
        # 等待恢复（如果已暂停）
        await pause_event.wait()
    
    async def check_and_wait(self, task_id: str) -> bool:
        """
        检查任务状态，如果已取消返回 False，如果已暂停则等待恢复
        
        Args:
            task_id: 任务 ID
            
        Returns:
            True 表示可以继续执行，False 表示已取消
        """
        # 检查是否已取消
        if await self.is_cancelled(task_id):
            return False
        
        # 如果已暂停，等待恢复
        await self.wait_if_paused(task_id)
        
        # 再次检查是否已取消（可能在等待期间被取消）
        if await self.is_cancelled(task_id):
            return False
        
        return True
    
    async def get_running_tasks(self) -> List[str]:
        """
        获取所有正在运行的任务 ID 列表
        
        Returns:
            任务 ID 列表
        """
        async with self._lock:
            return list(self._running_tasks.keys())


# 全局任务管理器实例
task_manager = TaskManager()

