"""
知识提取进度管理器
用于跟踪文件知识提取的进度
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from collections import defaultdict


class KnowledgeExtractionProgressManager:
    """
    知识提取进度管理器
    使用类似 TaskProgressManager 的方式跟踪知识提取进度
    """
    
    def __init__(self):
        """初始化进度管理器"""
        self._file_progress: Dict[str, Dict[str, Any]] = {}
        self._file_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def register_queue(self, file_id: str, queue: asyncio.Queue):
        """
        注册进度队列
        
        Args:
            file_id: 文件 ID
            queue: 进度更新队列
        """
        async with self._lock:
            if file_id not in self._file_queues:
                self._file_queues[file_id] = []
            self._file_queues[file_id].append(queue)
    
    async def unregister_queue(self, file_id: str, queue: asyncio.Queue):
        """
        注销进度队列
        
        Args:
            file_id: 文件 ID
            queue: 进度更新队列
        """
        async with self._lock:
            if file_id in self._file_queues:
                try:
                    self._file_queues[file_id].remove(queue)
                except ValueError:
                    pass
    
    async def push_progress(self, file_id: str, 
                          current: int,
                          total: int,
                          current_chunk: Optional[str] = None,
                          message: Optional[str] = None,
                          status: Optional[str] = None):
        """
        推送知识提取进度更新
        
        Args:
            file_id: 文件 ID
            current: 当前已处理的切片数
            total: 总切片数
            current_chunk: 当前处理的切片信息（可选）
            message: 进度消息（可选）
            status: 状态（可选：'extracting', 'completed', 'failed'）
        """
        # 计算进度百分比
        progress = current / total if total > 0 else 0.0
        progress = max(0.0, min(1.0, progress))
        
        # 更新最后状态
        async with self._lock:
            self._file_progress[file_id] = {
                "current": current,
                "total": total,
                "progress": progress,
                "percentage": round(progress * 100, 2),
                "current_chunk": current_chunk,
                "message": message,
                "status": status or "extracting",
                "updated_at": datetime.now().isoformat()
            }
        
        # 构建进度更新数据
        progress_data = {
            "current": current,
            "total": total,
            "progress": progress,
            "percentage": round(progress * 100, 2),
            "current_chunk": current_chunk,
            "message": message,
            "status": status or "extracting",
            "timestamp": datetime.now().isoformat()
        }
        
        # 推送到所有订阅的队列
        async with self._lock:
            if file_id in self._file_queues:
                queues = self._file_queues[file_id].copy()
                for queue in queues:
                    try:
                        await queue.put(progress_data)
                    except Exception as e:
                        print(f"推送知识提取进度到队列失败: {e}")
    
    async def get_last_state(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        获取文件的最后进度状态
        
        Args:
            file_id: 文件 ID
            
        Returns:
            进度状态字典，如果不存在则返回 None
        """
        async with self._lock:
            return self._file_progress.get(file_id)
    
    async def clear_progress(self, file_id: str):
        """
        清除文件的进度状态
        
        Args:
            file_id: 文件 ID
        """
        async with self._lock:
            if file_id in self._file_progress:
                del self._file_progress[file_id]
            if file_id in self._file_queues:
                del self._file_queues[file_id]


# 全局知识提取进度管理器实例
knowledge_extraction_progress = KnowledgeExtractionProgressManager()

