"""
知识图谱管理器
使用 NetworkX 构建和管理知识点之间的依赖关系图
"""

import json
import uuid
import httpx
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import deque

try:
    import networkx as nx
except ImportError:
    raise ImportError(
        "NetworkX 未安装。请运行: pip install networkx"
    )

from database import db


class KnowledgeGraphManager:
    """知识图谱管理器"""
    
    def __init__(self):
        """初始化知识图谱管理器"""
        self.graph = nx.DiGraph()  # 有向图
        self.concept_to_node_id: Dict[str, str] = {}  # 概念名称到节点ID的映射
        self.node_id_to_concept: Dict[str, str] = {}  # 节点ID到概念名称的映射
        self.concept_metadata: Dict[str, Dict[str, Any]] = {}  # 概念元数据（包含摘要等信息）
        self._is_loaded = False
    
    def load_from_database(self) -> int:
        """
        从数据库加载所有知识点节点并构建图
        
        Returns:
            加载的节点数量
        """
        # 清空现有图
        self.graph.clear()
        self.concept_to_node_id.clear()
        self.node_id_to_concept.clear()
        self.concept_metadata.clear()
        
        # 从数据库获取所有知识点节点
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT node_id, chunk_id, file_id, core_concept, level, parent_id,
                       prerequisites_json, confusion_points_json, bloom_level, 
                       application_scenarios_json, created_at
                FROM knowledge_nodes
                ORDER BY level ASC, created_at ASC
            """)
            rows = cursor.fetchall()
            
            # 第一遍：创建所有节点
            for row in rows:
                node_id = row["node_id"]
                core_concept = row["core_concept"]
                
                # 如果概念已存在，合并元数据（保留更早的节点ID）
                if core_concept in self.concept_to_node_id:
                    # 使用已存在的节点ID
                    existing_node_id = self.concept_to_node_id[core_concept]
                    # 更新元数据（合并信息）
                    existing_metadata = self.concept_metadata.get(core_concept, {})
                    existing_metadata.setdefault("node_ids", []).append(node_id)
                    existing_metadata.setdefault("chunk_ids", []).append(row["chunk_id"])
                    existing_metadata.setdefault("file_ids", set()).add(row["file_id"])
                    # 如果当前节点有 bloom_level 且现有元数据中没有，则使用当前节点的
                    if row["bloom_level"] is not None:
                        if "bloom_level" not in existing_metadata or existing_metadata["bloom_level"] is None:
                            existing_metadata["bloom_level"] = row["bloom_level"]
                    # 更新 level 和 parent_id（使用最新的值）
                    if "level" in row.keys() and row["level"] is not None:
                        existing_metadata["level"] = row["level"]
                    if "parent_id" in row.keys() and row["parent_id"] is not None:
                        existing_metadata["parent_id"] = row["parent_id"]
                    if row["confusion_points_json"]:
                        confusion_points = json.loads(row["confusion_points_json"])
                        existing_metadata.setdefault("confusion_points", []).extend(confusion_points)
                    if row["application_scenarios_json"]:
                        scenarios = json.loads(row["application_scenarios_json"])
                        existing_metadata.setdefault("application_scenarios", []).extend(scenarios or [])
                    self.concept_metadata[core_concept] = existing_metadata
                else:
                    # 创建新节点
                    self.concept_to_node_id[core_concept] = node_id
                    self.node_id_to_concept[node_id] = core_concept
                    
                    # 存储元数据
                    prerequisites = json.loads(row["prerequisites_json"]) if row["prerequisites_json"] else []
                    confusion_points = json.loads(row["confusion_points_json"]) if row["confusion_points_json"] else []
                    application_scenarios = json.loads(row["application_scenarios_json"]) if row["application_scenarios_json"] else None
                    
                    # 确保 bloom_level 不为 None，如果为 None 则使用默认值 3
                    bloom_level = row["bloom_level"] if row["bloom_level"] is not None else 3
                    
                    # 获取 level 和 parent_id（如果存在）
                    level = row["level"] if "level" in row.keys() and row["level"] is not None else 3
                    parent_id = row["parent_id"] if "parent_id" in row.keys() and row["parent_id"] is not None else None
                    
                    self.concept_metadata[core_concept] = {
                        "node_id": node_id,
                        "node_ids": [node_id],
                        "chunk_id": row["chunk_id"],
                        "chunk_ids": [row["chunk_id"]],
                        "file_id": row["file_id"],
                        "file_ids": {row["file_id"]},
                        "level": level,
                        "parent_id": parent_id,
                        "prerequisites": prerequisites,
                        "confusion_points": confusion_points,
                        "bloom_level": bloom_level,
                        "application_scenarios": application_scenarios or [],
                        "created_at": row["created_at"]
                    }
                    
                    # 在图中添加节点
                    self.graph.add_node(core_concept, **self.concept_metadata[core_concept])
            
            # 第二遍：创建边
            # 1. 创建父子关系边（基于 parent_id）
            for row in rows:
                core_concept = row["core_concept"]
                parent_id = row["parent_id"] if "parent_id" in row.keys() and row["parent_id"] else None
                
                if parent_id:
                    # 查找父节点的概念名称
                    parent_node_info = db.get_knowledge_node(parent_id)
                    if parent_node_info:
                        parent_concept = parent_node_info.get("core_concept")
                        if parent_concept and parent_concept in self.graph:
                            # 添加父子关系边：parent_concept -> core_concept（表示 core_concept 属于 parent_concept）
                            self.graph.add_edge(parent_concept, core_concept, relation="parent_child")
            
            # 2. 创建依赖关系边（基于 knowledge_dependencies 表）
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT kd.source_node_id, kd.target_node_id
                    FROM knowledge_dependencies kd
                    JOIN knowledge_nodes kn1 ON kd.source_node_id = kn1.node_id
                    JOIN knowledge_nodes kn2 ON kd.target_node_id = kn2.node_id
                """)
                dependency_rows = cursor.fetchall()
                
                for dep_row in dependency_rows:
                    source_node_id = dep_row["source_node_id"]
                    target_node_id = dep_row["target_node_id"]
                    
                    # 查找源节点和目标节点的概念名称
                    source_node_info = db.get_knowledge_node(source_node_id)
                    target_node_info = db.get_knowledge_node(target_node_id)
                    
                    if source_node_info and target_node_info:
                        source_concept = source_node_info.get("core_concept")
                        target_concept = target_node_info.get("core_concept")
                        
                        if source_concept and target_concept:
                            # 如果节点不在图中，先添加节点
                            if source_concept not in self.graph:
                                # 创建临时节点
                                if source_concept not in self.concept_to_node_id:
                                    temp_node_id = f"temp_{source_concept}"
                                    self.concept_to_node_id[source_concept] = temp_node_id
                                    self.node_id_to_concept[temp_node_id] = source_concept
                                    self.concept_metadata[source_concept] = {
                                        "node_id": temp_node_id,
                                        "is_temporary": True,
                                        "prerequisites": [],
                                        "confusion_points": [],
                                        "bloom_level": 3,
                                        "application_scenarios": []
                                    }
                                    self.graph.add_node(source_concept, **self.concept_metadata[source_concept])
                            
                            if target_concept not in self.graph:
                                # 创建临时节点
                                if target_concept not in self.concept_to_node_id:
                                    temp_node_id = f"temp_{target_concept}"
                                    self.concept_to_node_id[target_concept] = temp_node_id
                                    self.node_id_to_concept[temp_node_id] = target_concept
                                    self.concept_metadata[target_concept] = {
                                        "node_id": temp_node_id,
                                        "is_temporary": True,
                                        "prerequisites": [],
                                        "confusion_points": [],
                                        "bloom_level": 3,
                                        "application_scenarios": []
                                    }
                                    self.graph.add_node(target_concept, **self.concept_metadata[target_concept])
                            
                            # 添加依赖关系边：source_concept -> target_concept（表示 target_concept 依赖于 source_concept）
                            if source_concept != target_concept:  # 避免自环
                                self.graph.add_edge(source_concept, target_concept, relation="depends_on")
            
            # 3. 创建前置依赖关系边（基于 prerequisites_json，向后兼容）
            for row in rows:
                core_concept = row["core_concept"]
                prerequisites = json.loads(row["prerequisites_json"]) if row["prerequisites_json"] else []
                
                # 为每个前置依赖创建边
                for prereq in prerequisites:
                    prereq = prereq.strip()
                    if prereq and prereq != core_concept:  # 避免自环
                        # 如果前置知识点在图中存在，创建边
                        if prereq in self.graph:
                            # 添加边：prereq -> core_concept（表示 core_concept 依赖于 prereq）
                            # 检查是否已存在边（避免重复）
                            if not self.graph.has_edge(prereq, core_concept):
                                self.graph.add_edge(prereq, core_concept, relation="depends_on")
                        else:
                            # 前置知识点不存在，创建孤立节点（可能来自其他文件）
                            if prereq not in self.concept_to_node_id:
                                # 创建临时节点ID
                                temp_node_id = f"temp_{prereq}"
                                self.concept_to_node_id[prereq] = temp_node_id
                                self.node_id_to_concept[temp_node_id] = prereq
                                self.concept_metadata[prereq] = {
                                    "node_id": temp_node_id,
                                    "is_temporary": True,  # 标记为临时节点
                                    "prerequisites": [],
                                    "confusion_points": [],
                                    "bloom_level": 3,  # 默认设置为应用层级
                                    "application_scenarios": []
                                }
                                self.graph.add_node(prereq, **self.concept_metadata[prereq])
                            
                            # 创建边（检查是否已存在）
                            if not self.graph.has_edge(prereq, core_concept):
                                self.graph.add_edge(prereq, core_concept, relation="depends_on")
        
        self._is_loaded = True
        return len(self.graph.nodes())
    
    def reload(self) -> int:
        """
        重新加载图（从数据库）
        
        Returns:
            加载的节点数量
        """
        return self.load_from_database()
    
    def _normalize_concept_name(self, concept_name: str) -> Optional[str]:
        """
        规范化概念名称，尝试在图中找到匹配的节点
        
        Args:
            concept_name: 原始概念名称
            
        Returns:
            规范化后的概念名称，如果找不到则返回 None
        """
        concept_name = concept_name.strip()
        
        # 直接匹配
        if concept_name in self.graph:
            return concept_name
        
        # 尝试大小写不敏感匹配
        for node in self.graph.nodes():
            if node.lower() == concept_name.lower():
                return node
        
        # 尝试包含匹配（部分匹配）
        for node in self.graph.nodes():
            if concept_name.lower() in node.lower() or node.lower() in concept_name.lower():
                return node
        
        return None
    
    def get_prerequisite_context(self, concept_name: str, max_depth: int = 3, max_concepts: int = 3) -> List[Dict[str, Any]]:
        """
        根据当前知识点，回溯出与其最相关的 2-3 个前置知识点及其摘要
        
        使用广度优先搜索（BFS）从当前节点向上回溯，找到最直接的前置依赖。
        优先返回距离最近（深度最小）的前置知识点。
        
        Args:
            concept_name: 当前知识点名称
            max_depth: 最大回溯深度（默认 3）
            max_concepts: 最多返回的前置知识点数量（默认 3）
            
        Returns:
            前置知识点列表，每个元素包含：
            - concept: 知识点名称
            - depth: 距离当前知识点的深度（1表示直接依赖）
            - summary: 知识点摘要（包含核心概念、易错点、应用场景等）
            - bloom_level: Bloom 认知层级
        """
        if not self._is_loaded:
            self.load_from_database()
        
        # 规范化概念名称
        normalized_name = self._normalize_concept_name(concept_name)
        if not normalized_name:
            return []
        
        # 使用 BFS 向上回溯（从当前节点向入边方向遍历）
        visited: Set[str] = {normalized_name}
        queue = deque([(normalized_name, 0)])  # (节点名称, 深度)
        prerequisites: List[Tuple[str, int]] = []  # (概念名称, 深度)
        
        while queue and len(prerequisites) < max_concepts * 2:  # 多收集一些，然后筛选
            current, depth = queue.popleft()
            
            if depth >= max_depth:
                continue
            
            # 获取当前节点的所有前置节点（入边的源节点）
            predecessors = list(self.graph.predecessors(current))
            
            for pred in predecessors:
                if pred not in visited:
                    visited.add(pred)
                    prerequisites.append((pred, depth + 1))
                    queue.append((pred, depth + 1))
        
        # 按深度排序，优先返回深度小的（直接依赖）
        prerequisites.sort(key=lambda x: x[1])
        
        # 限制返回数量
        prerequisites = prerequisites[:max_concepts]
        
        # 构建结果
        result = []
        for concept, depth in prerequisites:
            metadata = self.concept_metadata.get(concept, {})
            
            # 构建摘要
            summary_parts = []
            
            # 核心概念
            summary_parts.append(f"核心概念：{concept}")
            
            # Bloom 层级
            bloom_level = metadata.get("bloom_level")
            if bloom_level:
                bloom_names = {
                    1: "记忆",
                    2: "理解",
                    3: "应用",
                    4: "分析",
                    5: "评价",
                    6: "创造"
                }
                summary_parts.append(f"认知层级：{bloom_level}级（{bloom_names.get(bloom_level, '未知')}）")
            
            # 易错点
            confusion_points = metadata.get("confusion_points", [])
            if confusion_points:
                # 过滤空字符串
                confusion_points = [cp for cp in confusion_points if cp and cp.strip()]
                if confusion_points:
                    summary_parts.append(f"易错点：{', '.join(confusion_points[:3])}")  # 最多显示3个
            
            # 应用场景
            application_scenarios = metadata.get("application_scenarios", [])
            if application_scenarios:
                # 过滤空字符串
                application_scenarios = [as_scenario for as_scenario in application_scenarios if as_scenario and as_scenario.strip()]
                if application_scenarios:
                    summary_parts.append(f"应用场景：{', '.join(application_scenarios[:2])}")  # 最多显示2个
            
            summary = "；".join(summary_parts) if summary_parts else f"核心概念：{concept}"
            
            result.append({
                "concept": concept,
                "depth": depth,
                "summary": summary,
                "bloom_level": bloom_level,
                "confusion_points": confusion_points[:3] if confusion_points else [],  # 最多返回3个
                "application_scenarios": application_scenarios[:2] if application_scenarios else []  # 最多返回2个
            })
        
        return result
    
    def get_concept_info(self, concept_name: str) -> Optional[Dict[str, Any]]:
        """
        获取知识点的详细信息
        
        Args:
            concept_name: 知识点名称
            
        Returns:
            知识点信息字典，如果不存在则返回 None
        """
        if not self._is_loaded:
            self.load_from_database()
        
        # 规范化概念名称
        normalized_name = self._normalize_concept_name(concept_name)
        if not normalized_name:
            return None
        
        concept_name = normalized_name
        
        metadata = self.concept_metadata.get(concept_name, {})
        
        # 获取前置依赖
        predecessors = list(self.graph.predecessors(concept_name))
        
        # 获取后续依赖（依赖当前知识点的知识点）
        successors = list(self.graph.successors(concept_name))
        
        return {
            "concept": concept_name,
            "metadata": metadata,
            "prerequisites": predecessors,
            "dependents": successors,  # 依赖当前知识点的知识点
            "in_degree": self.graph.in_degree(concept_name),  # 入度（前置依赖数量）
            "out_degree": self.graph.out_degree(concept_name),  # 出度（后续依赖数量）
        }
    
    def get_all_concepts(self) -> List[str]:
        """
        获取所有知识点名称列表
        
        Returns:
            知识点名称列表
        """
        if not self._is_loaded:
            self.load_from_database()
        
        return list(self.graph.nodes())
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """
        获取图的统计信息
        
        Returns:
            统计信息字典
        """
        if not self._is_loaded:
            self.load_from_database()
        
        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "is_dag": nx.is_directed_acyclic_graph(self.graph),
            "has_cycles": not nx.is_directed_acyclic_graph(self.graph),
            "connected_components": nx.number_weakly_connected_components(self.graph),
        }
    
    def find_path(self, source_concept: str, target_concept: str) -> Optional[List[str]]:
        """
        查找两个知识点之间的路径
        
        Args:
            source_concept: 源知识点
            target_concept: 目标知识点
            
        Returns:
            路径列表（如果存在），否则返回 None
        """
        if not self._is_loaded:
            self.load_from_database()
        
        # 规范化概念名称
        normalized_source = self._normalize_concept_name(source_concept)
        normalized_target = self._normalize_concept_name(target_concept)
        
        if not normalized_source or not normalized_target:
            return None
        
        try:
            # 使用 NetworkX 的最短路径算法
            path = nx.shortest_path(self.graph, normalized_source, normalized_target)
            return path
        except nx.NetworkXNoPath:
            return None
    
    def get_topological_order(self) -> List[str]:
        """
        获取拓扑排序（如果图是 DAG）
        
        Returns:
            拓扑排序后的知识点列表
        """
        if not self._is_loaded:
            self.load_from_database()
        
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXError:
            # 如果图有环，返回空列表
            return []


async def reconstruct_hierarchy(
    textbook_id: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    api_endpoint: Optional[str] = None
) -> Dict[str, Any]:
    """
    重构知识点层级结构
    
    将教材的所有知识点提交给 LLM，按照计算机学科逻辑划分为三个层级：
    - Level 1 (Global): 一级全局知识点（如"内存管理"、"进程管理"）
    - Level 2 (Chapter): 二级章节知识点（如"虚拟内存"、"页面置换算法"）
    - Level 3 (Unit): 三级原子知识点（如"TLB 快表"、"LRU 算法细节"）
    
    然后根据分类结果，自动为二级节点指定一级父节点，为三级节点指定二级父节点。
    
    Args:
        textbook_id: 教材 ID
        api_key: OpenRouter API 密钥（可选，默认从数据库读取）
        model: 模型名称（可选，默认从数据库读取）
        api_endpoint: API端点URL（可选，默认从数据库读取）
        
    Returns:
        包含以下字段的字典：
        - success: 是否成功
        - total_concepts: 总知识点数
        - level_1_count: Level 1 知识点数量
        - level_2_count: Level 2 知识点数量
        - level_3_count: Level 3 知识点数量
        - relationships_built: 建立的父子关系数量
        - message: 处理结果消息
    """
    try:
        # 导入 OpenRouter 客户端（延迟导入，避免循环依赖）
        from generator import OpenRouterClient, get_timeout_config, get_max_output_tokens
        
        # 获取教材信息
        textbook_info = db.get_textbook(textbook_id)
        if not textbook_info:
            return {
                "success": False,
                "total_concepts": 0,
                "level_1_count": 0,
                "level_2_count": 0,
                "level_3_count": 0,
                "relationships_built": 0,
                "message": f"教材 ID {textbook_id} 不存在"
            }
        
        textbook_name = textbook_info.get("name", "未知教材")
        
        # 获取教材的所有知识点节点
        knowledge_nodes = db.get_textbook_knowledge_nodes(textbook_id)
        if not knowledge_nodes:
            return {
                "success": False,
                "total_concepts": 0,
                "level_1_count": 0,
                "level_2_count": 0,
                "level_3_count": 0,
                "relationships_built": 0,
                "message": f"教材 {textbook_name} 没有知识点节点"
            }
        
        total_concepts = len(knowledge_nodes)
        print(f"[层级重构] 开始为教材 {textbook_name} 重构层级结构，共 {total_concepts} 个知识点")
        
        # 提取所有概念名称
        concept_names = [node["core_concept"] for node in knowledge_nodes]
        concept_to_node = {node["core_concept"]: node for node in knowledge_nodes}
        
        # 如果没有提供 API 配置，从数据库读取
        if not api_key or not model or not api_endpoint:
            ai_config = db.get_ai_config()
            if not api_key:
                api_key = ai_config.get("api_key")
            if not model:
                model = ai_config.get("model", "openai/gpt-4o-mini")
            if not api_endpoint:
                api_endpoint = ai_config.get("api_endpoint", "https://openrouter.ai/api/v1/chat/completions")
        
        if not api_key:
            return {
                "success": False,
                "total_concepts": total_concepts,
                "level_1_count": 0,
                "level_2_count": 0,
                "level_3_count": 0,
                "relationships_built": 0,
                "message": "API key 未配置，无法进行层级重构"
            }
        
        # 创建 OpenRouter 客户端
        client = OpenRouterClient(api_key=api_key, model=model, api_endpoint=api_endpoint)
        
        # 构建系统提示词
        system_prompt = """你是一位资深的计算机科学教育专家，专门从事知识点层级分类工作。你的任务是将给定的知识点列表按照计算机学科的逻辑划分为三个层级：

**层级定义：**

1. **Level 1 (Global - 一级全局知识点)**：
   - 宏观的、全局性的计算机科学主题或领域
   - 通常是课程或教材的主要章节主题
   - 例如："内存管理"、"进程管理"、"文件系统"、"网络协议"、"数据库设计"等
   - 特点：涵盖范围广，包含多个子主题

2. **Level 2 (Chapter - 二级章节知识点)**：
   - 一级主题下的具体章节或子领域
   - 通常是某个全局主题的重要组成部分
   - 例如："虚拟内存"、"页面置换算法"、"进程同步"、"死锁"、"TCP/IP协议"、"关系数据库"等
   - 特点：比一级更具体，但仍然是一个相对完整的知识模块

3. **Level 3 (Unit - 三级原子知识点)**：
   - 最具体、最细粒度的知识点
   - 通常是某个二级主题下的具体概念、算法、技术细节
   - 例如："TLB 快表"、"LRU 算法细节"、"信号量"、"银行家算法"、"三次握手"、"SQL 查询优化"等
   - 特点：非常具体，通常是可直接应用的知识点

**分类原则：**
1. 按照计算机学科的知识体系逻辑进行分类
2. 确保层级关系合理：Level 2 应该属于某个 Level 1，Level 3 应该属于某个 Level 2
3. 如果某个知识点可以属于多个父级，选择最直接、最相关的父级
4. 保持分类的一致性和逻辑性

请严格按照以下 JSON 格式返回分类结果：

```json
{
  "level_1": [
    {
      "concept": "知识点名称",
      "children": ["子知识点1", "子知识点2", ...]
    },
    ...
  ],
  "level_2": [
    {
      "concept": "知识点名称",
      "parent": "父知识点名称（Level 1）",
      "children": ["子知识点1", "子知识点2", ...]
    },
    ...
  ],
  "level_3": [
    {
      "concept": "知识点名称",
      "parent": "父知识点名称（Level 2）"
    },
    ...
  ]
}
```

**重要要求：**
1. 必须返回所有知识点，不能遗漏任何知识点
2. 每个 Level 2 知识点必须指定一个 Level 1 父节点
3. 每个 Level 3 知识点必须指定一个 Level 2 父节点
4. 父节点名称必须与输入列表中的知识点名称完全一致
5. 如果某个知识点无法明确分类，请根据其内容特征选择最合适的层级"""
        
        # 构建用户提示词
        concepts_list_str = "\n".join([f"{i+1}. {concept}" for i, concept in enumerate(concept_names)])
        user_prompt = f"""请将以下知识点按照计算机学科逻辑划分为三个层级：

**教材名称：** {textbook_name}
**知识点总数：** {total_concepts}

**知识点列表：**
{concepts_list_str}

请仔细分析每个知识点的内容和特征，将它们合理分类到三个层级中，并建立正确的父子关系。"""
        
        # 准备 API 请求
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/your-repo",
            "X-Title": "AI Question Generator",
        }
        
        # 估算需要的 tokens（保守估计）
        estimated_tokens = len(system_prompt) + len(user_prompt) + total_concepts * 50 + 2000
        max_tokens = get_max_output_tokens(model, "knowledge_extraction")
        max_tokens = min(max_tokens, max(estimated_tokens, 4000))
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,  # 降低温度，提高分类准确性
            "max_tokens": max_tokens,
        }
        
        print(f"[层级重构] 调用 LLM API 进行分类，使用模型: {model}")
        
        # 调用 API
        timeout_config = get_timeout_config(model, is_stream=False)
        async with httpx.AsyncClient(timeout=timeout_config) as http_client:
            response = await http_client.post(
                client.api_endpoint,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" not in result or len(result["choices"]) == 0:
                return {
                    "success": False,
                    "total_concepts": total_concepts,
                    "level_1_count": 0,
                    "level_2_count": 0,
                    "level_3_count": 0,
                    "relationships_built": 0,
                    "message": "API 返回结果中没有 choices 字段"
                }
            
            generated_text = result["choices"][0]["message"]["content"].strip()
            
            # 清理代码块标记
            if generated_text.startswith("```json"):
                generated_text = generated_text[7:].strip()
            elif generated_text.startswith("```"):
                generated_text = generated_text[3:].strip()
            if generated_text.endswith("```"):
                generated_text = generated_text[:-3].strip()
            
            # 解析 JSON
            try:
                hierarchy_data = json.loads(generated_text)
            except json.JSONDecodeError as e:
                print(f"[层级重构] JSON 解析失败: {e}")
                print(f"[层级重构] 原始响应（前500字符）: {generated_text[:500]}")
                return {
                    "success": False,
                    "total_concepts": total_concepts,
                    "level_1_count": 0,
                    "level_2_count": 0,
                    "level_3_count": 0,
                    "relationships_built": 0,
                    "message": f"JSON 解析失败: {str(e)}"
                }
        
        # 验证和提取分类结果
        level_1_items = hierarchy_data.get("level_1", [])
        level_2_items = hierarchy_data.get("level_2", [])
        level_3_items = hierarchy_data.get("level_3", [])
        
        # 构建概念到层级的映射
        concept_to_level = {}
        concept_to_parent = {}
        
        # 处理 Level 1
        level_1_concepts = []
        for item in level_1_items:
            concept = item.get("concept", "").strip()
            if concept and concept in concept_to_node:
                level_1_concepts.append(concept)
                concept_to_level[concept] = 1
                concept_to_parent[concept] = None
        
        # 处理 Level 2
        level_2_concepts = []
        for item in level_2_items:
            concept = item.get("concept", "").strip()
            parent = item.get("parent", "").strip()
            if concept and concept in concept_to_node:
                level_2_concepts.append(concept)
                concept_to_level[concept] = 2
                # 验证父节点是否存在且是 Level 1
                if parent and parent in concept_to_node and parent in level_1_concepts:
                    concept_to_parent[concept] = parent
                else:
                    # 如果父节点不存在或不是 Level 1，设置为 None（后续可以手动调整）
                    if parent:
                        print(f"[层级重构] ⚠ 警告：Level 2 知识点 '{concept}' 的父节点 '{parent}' 不存在或不是 Level 1")
                    concept_to_parent[concept] = None
        
        # 处理 Level 3
        level_3_concepts = []
        for item in level_3_items:
            concept = item.get("concept", "").strip()
            parent = item.get("parent", "").strip()
            if concept and concept in concept_to_node:
                level_3_concepts.append(concept)
                concept_to_level[concept] = 3
                # 验证父节点是否存在且是 Level 2
                if parent and parent in concept_to_node and parent in level_2_concepts:
                    concept_to_parent[concept] = parent
                else:
                    # 如果父节点不存在或不是 Level 2，设置为 None（后续可以手动调整）
                    if parent:
                        print(f"[层级重构] ⚠ 警告：Level 3 知识点 '{concept}' 的父节点 '{parent}' 不存在或不是 Level 2")
                    concept_to_parent[concept] = None
        
        # 检查是否有遗漏的知识点
        classified_concepts = set(level_1_concepts + level_2_concepts + level_3_concepts)
        missing_concepts = set(concept_names) - classified_concepts
        
        if missing_concepts:
            print(f"[层级重构] ⚠ 警告：有 {len(missing_concepts)} 个知识点未被分类，将默认设置为 Level 3")
            for concept in missing_concepts:
                if concept in concept_to_node:  # 确保概念存在于节点中
                    concept_to_level[concept] = 3
                    concept_to_parent[concept] = None
        
        # 建立概念名称到节点 ID 的映射（用于查找父节点）
        concept_to_node_id_map = {}
        for node in knowledge_nodes:
            concept_to_node_id_map[node["core_concept"]] = node["node_id"]
        
        # 更新数据库
        relationships_built = 0
        level_1_count = 0
        level_2_count = 0
        level_3_count = 0
        
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            for concept, level in concept_to_level.items():
                node = concept_to_node[concept]
                node_id = node["node_id"]
                parent_concept = concept_to_parent.get(concept)
                parent_id = None
                
                if parent_concept and parent_concept in concept_to_node_id_map:
                    parent_id = concept_to_node_id_map[parent_concept]
                    relationships_built += 1
                
                # 更新节点的 level 和 parent_id
                cursor.execute("""
                    UPDATE knowledge_nodes
                    SET level = ?, parent_id = ?
                    WHERE node_id = ?
                """, (level, parent_id, node_id))
                
                if level == 1:
                    level_1_count += 1
                elif level == 2:
                    level_2_count += 1
                elif level == 3:
                    level_3_count += 1
            
            conn.commit()
        
        print(f"[层级重构] ✓ 完成层级重构")
        print(f"[层级重构]   Level 1: {level_1_count} 个")
        print(f"[层级重构]   Level 2: {level_2_count} 个")
        print(f"[层级重构]   Level 3: {level_3_count} 个")
        print(f"[层级重构]   建立的父子关系: {relationships_built} 个")
        
        # 重新加载知识图谱（确保新更新的层级信息能够被查询到）
        try:
            knowledge_graph.reload()
            print(f"[层级重构] ✓ 知识图谱已重新加载，当前节点数: {knowledge_graph.graph.number_of_nodes()}")
        except Exception as e:
            print(f"[层级重构] ⚠ 警告：重新加载知识图谱失败: {e}")
            import traceback
            traceback.print_exc()
        
        return {
            "success": True,
            "total_concepts": total_concepts,
            "level_1_count": level_1_count,
            "level_2_count": level_2_count,
            "level_3_count": level_3_count,
            "relationships_built": relationships_built,
            "missing_concepts": len(missing_concepts) if missing_concepts else 0,
            "message": f"成功重构层级结构：Level 1 ({level_1_count}), Level 2 ({level_2_count}), Level 3 ({level_3_count})，建立 {relationships_built} 个父子关系"
        }
        
    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP 请求失败: {e.response.status_code}"
        print(f"[层级重构] ✗ {error_msg}")
        return {
            "success": False,
            "total_concepts": len(knowledge_nodes) if 'knowledge_nodes' in locals() else 0,
            "level_1_count": 0,
            "level_2_count": 0,
            "level_3_count": 0,
            "relationships_built": 0,
            "message": error_msg
        }
    except Exception as e:
        error_msg = f"层级重构失败: {str(e)}"
        print(f"[层级重构] ✗ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "total_concepts": len(knowledge_nodes) if 'knowledge_nodes' in locals() else 0,
            "level_1_count": 0,
            "level_2_count": 0,
            "level_3_count": 0,
            "relationships_built": 0,
            "message": error_msg
        }


async def build_dependency_edges(
    textbook_id: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    api_endpoint: Optional[str] = None
) -> Dict[str, Any]:
    """
    构建知识点横向依赖关系（基于学习路径）
    
    在层级构建完成后，按照三个层级分别构建横向依赖关系：
    1. Level 1 间依赖：分析一级概念间的先后顺序（如：理解"文件系统"前是否必须理解"磁盘存储"）
    2. Level 2 间依赖：在同一个父节点下，分析二级概念的逻辑递进关系（如：先学"分页存储"再学"分段存储"）
    3. Level 3 间依赖：构建具体技术点之间的微观依赖
    
    约束条件：
    - 避免循环依赖
    - 依赖关系应基于"学习路径"而非简单的包含关系
    - 最终生成完整的有向无环图 (DAG) 结构
    
    Args:
        textbook_id: 教材 ID
        api_key: OpenRouter API 密钥（可选，默认从数据库读取）
        model: 模型名称（可选，默认从数据库读取）
        api_endpoint: API端点URL（可选，默认从数据库读取）
        
    Returns:
        包含以下字段的字典：
        - success: 是否成功
        - level_1_edges: Level 1 依赖关系数量
        - level_2_edges: Level 2 依赖关系数量
        - level_3_edges: Level 3 依赖关系数量
        - total_edges: 总依赖关系数量
        - cycles_detected: 检测到的循环数量（已避免）
        - message: 处理结果消息
    """
    try:
        # 导入 OpenRouter 客户端（延迟导入，避免循环依赖）
        from generator import OpenRouterClient, get_timeout_config, get_max_output_tokens
        
        # 获取教材信息
        textbook_info = db.get_textbook(textbook_id)
        if not textbook_info:
            return {
                "success": False,
                "level_1_edges": 0,
                "level_2_edges": 0,
                "level_3_edges": 0,
                "total_edges": 0,
                "edges_added": 0,
                "cycles_detected": 0,
                "message": f"教材 ID {textbook_id} 不存在"
            }
        
        textbook_name = textbook_info.get("name", "未知教材")
        
        # 获取教材的所有知识点节点（按层级分组）
        knowledge_nodes = db.get_textbook_knowledge_nodes(textbook_id)
        if not knowledge_nodes:
            return {
                "success": False,
                "level_1_edges": 0,
                "level_2_edges": 0,
                "level_3_edges": 0,
                "total_edges": 0,
                "edges_added": 0,
                "cycles_detected": 0,
                "message": f"教材 {textbook_name} 没有知识点节点"
            }
        
        # 按层级分组
        level_1_nodes = [n for n in knowledge_nodes if n.get("level", 3) == 1]
        level_2_nodes = [n for n in knowledge_nodes if n.get("level", 3) == 2]
        level_3_nodes = [n for n in knowledge_nodes if n.get("level", 3) == 3]
        
        # 构建概念到节点ID的映射
        concept_to_node_id = {node["core_concept"]: node["node_id"] for node in knowledge_nodes}
        node_id_to_concept = {node["node_id"]: node["core_concept"] for node in knowledge_nodes}
        
        # 获取教材的第一个文件（用于创建新节点）
        textbook_files = db.get_textbook_files(textbook_id)
        default_file_id = None
        default_chunk_id = -1  # 使用虚拟 chunk_id
        if textbook_files:
            default_file_id = textbook_files[0]["file_id"]
            # 尝试获取该文件的第一个 chunk_id
            with db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT chunk_id FROM chunks 
                    WHERE file_id = ? 
                    ORDER BY chunk_index ASC 
                    LIMIT 1
                """, (default_file_id,))
                chunk_row = cursor.fetchone()
                if chunk_row:
                    default_chunk_id = chunk_row["chunk_id"]
        
        if not default_file_id:
            return {
                "success": False,
                "level_1_edges": 0,
                "level_2_edges": 0,
                "level_3_edges": 0,
                "total_edges": 0,
                "edges_added": 0,
                "cycles_detected": 0,
                "message": f"教材 {textbook_name} 没有关联的文件，无法创建新节点"
            }
        
        def _ensure_node_exists(concept: str, level: int, parent_concept: Optional[str] = None) -> str:
            """
            确保节点存在，如果不存在则创建
            
            Args:
                concept: 概念名称
                level: 层级（1/2/3）
                parent_concept: 父节点概念名称（可选）
                
            Returns:
                节点的 node_id
            """
            if concept in concept_to_node_id:
                return concept_to_node_id[concept]
            
            # 节点不存在，需要创建
            print(f"[依赖构建] ⚠ 发现缺失节点 '{concept}'，自动创建（Level {level}）")
            
            # 生成新的 node_id
            new_node_id = str(uuid.uuid4())
            
            # 确定 parent_id
            parent_id = None
            if parent_concept and parent_concept in concept_to_node_id:
                parent_id = concept_to_node_id[parent_concept]
            
            # 创建节点到数据库
            success = db.store_knowledge_node(
                node_id=new_node_id,
                chunk_id=default_chunk_id,
                file_id=default_file_id,
                core_concept=concept,
                level=level,
                prerequisites=[],
                confusion_points=[],
                bloom_level=3,  # 默认应用层级
                application_scenarios=None,
                parent_id=parent_id
            )
            
            if success:
                # 更新映射
                concept_to_node_id[concept] = new_node_id
                node_id_to_concept[new_node_id] = concept
                
                # 添加到知识节点列表（用于后续处理）
                knowledge_nodes.append({
                    "node_id": new_node_id,
                    "core_concept": concept,
                    "level": level,
                    "parent_id": parent_id,
                    "file_id": default_file_id
                })
                
                print(f"[依赖构建] ✓ 成功创建节点 '{concept}' (node_id: {new_node_id}, level: {level})")
                return new_node_id
            else:
                print(f"[依赖构建] ✗ 创建节点失败: {concept}")
                # 即使创建失败，也返回一个临时 ID，避免后续错误
                temp_node_id = f"temp_{concept}"
                concept_to_node_id[concept] = temp_node_id
                node_id_to_concept[temp_node_id] = concept
                return temp_node_id
        
        print(f"[依赖构建] 开始为教材 {textbook_name} 构建横向依赖关系")
        print(f"[依赖构建]   Level 1: {len(level_1_nodes)} 个")
        print(f"[依赖构建]   Level 2: {len(level_2_nodes)} 个")
        print(f"[依赖构建]   Level 3: {len(level_3_nodes)} 个")
        
        # 如果没有提供 API 配置，从数据库读取
        if not api_key or not model or not api_endpoint:
            ai_config = db.get_ai_config()
            if not api_key:
                api_key = ai_config.get("api_key")
            if not model:
                model = ai_config.get("model", "openai/gpt-4o-mini")
            if not api_endpoint:
                api_endpoint = ai_config.get("api_endpoint", "https://openrouter.ai/api/v1/chat/completions")
        
        if not api_key:
            return {
                "success": False,
                "level_1_edges": 0,
                "level_2_edges": 0,
                "level_3_edges": 0,
                "total_edges": 0,
                "edges_added": 0,
                "cycles_detected": 0,
                "message": "API key 未配置，无法构建依赖关系"
            }
        
        # 创建 OpenRouter 客户端
        client = OpenRouterClient(api_key=api_key, model=model, api_endpoint=api_endpoint)
        
        # 使用 NetworkX 构建临时图，用于检测循环
        temp_graph = nx.DiGraph()
        all_edges = []  # 存储所有要添加的边 (source_node_id, target_node_id)
        cycles_detected = 0
        
        # ========== 1. 构建 Level 1 之间的依赖关系 ==========
        level_1_edges = 0
        if len(level_1_nodes) > 1:
            print(f"[依赖构建] 构建 Level 1 之间的依赖关系...")
            level_1_concepts = [node["core_concept"] for node in level_1_nodes]
            
            # 调用 LLM 分析 Level 1 之间的依赖关系
            level_1_dependencies = await _analyze_level_dependencies(
                level_1_concepts,
                level=1,
                textbook_name=textbook_name,
                client=client,
                model=model,
                api_endpoint=api_endpoint,
                api_key=api_key
            )
            
            # 添加边到临时图（检测循环）
            for dep in level_1_dependencies:
                source_concept = dep["source"]
                target_concept = dep["target"]
                
                # 确保节点存在（如果不存在则自动创建）
                source_id = _ensure_node_exists(source_concept, level=1)
                target_id = _ensure_node_exists(target_concept, level=1)
                
                # 检查是否会形成循环
                temp_graph.add_edge(source_id, target_id)
                if not nx.is_directed_acyclic_graph(temp_graph):
                    # 如果形成循环，移除这条边
                    temp_graph.remove_edge(source_id, target_id)
                    cycles_detected += 1
                    print(f"[依赖构建] ⚠ 检测到循环依赖（已避免）: {source_concept} -> {target_concept}")
                else:
                    all_edges.append((source_id, target_id))
                    level_1_edges += 1
        
        # ========== 2. 构建 Level 2 之间的依赖关系（同一父节点下）==========
        level_2_edges = 0
        if level_2_nodes:
            print(f"[依赖构建] 构建 Level 2 之间的依赖关系...")
            
            # 按父节点分组
            level_2_by_parent = {}
            for node in level_2_nodes:
                parent_id = node.get("parent_id")
                if parent_id:
                    if parent_id not in level_2_by_parent:
                        level_2_by_parent[parent_id] = []
                    level_2_by_parent[parent_id].append(node)
            
            # 对每个父节点下的 Level 2 节点进行分析
            for parent_node_id, children_nodes in level_2_by_parent.items():
                if len(children_nodes) > 1:
                    # 获取父节点的概念名称（用于创建新节点时设置 parent_id）
                    parent_concept_name = node_id_to_concept.get(parent_node_id)
                    if not parent_concept_name:
                        # 如果父节点不存在，跳过这个分组
                        print(f"[依赖构建] ⚠ 警告：父节点 ID {parent_node_id} 不存在，跳过该分组")
                        continue
                    
                    level_2_concepts = [node["core_concept"] for node in children_nodes]
                    
                    # 调用 LLM 分析同一父节点下 Level 2 之间的依赖关系
                    level_2_dependencies = await _analyze_level_dependencies(
                        level_2_concepts,
                        level=2,
                        textbook_name=textbook_name,
                        parent_concept=parent_concept_name,
                        client=client,
                        model=model,
                        api_endpoint=api_endpoint,
                        api_key=api_key
                    )
                    
                    # 添加边到临时图（检测循环）
                    for dep in level_2_dependencies:
                        source_concept = dep["source"]
                        target_concept = dep["target"]
                        
                        # 确保节点存在（如果不存在则自动创建，使用当前父节点）
                        source_id = _ensure_node_exists(source_concept, level=2, parent_concept=parent_concept_name)
                        target_id = _ensure_node_exists(target_concept, level=2, parent_concept=parent_concept_name)
                        
                        # 检查是否会形成循环
                        temp_graph.add_edge(source_id, target_id)
                        if not nx.is_directed_acyclic_graph(temp_graph):
                            # 如果形成循环，移除这条边
                            temp_graph.remove_edge(source_id, target_id)
                            cycles_detected += 1
                            print(f"[依赖构建] ⚠ 检测到循环依赖（已避免）: {source_concept} -> {target_concept}")
                        else:
                            all_edges.append((source_id, target_id))
                            level_2_edges += 1
        
        # ========== 3. 构建 Level 3 之间的依赖关系 ==========
        level_3_edges = 0
        if len(level_3_nodes) > 1:
            print(f"[依赖构建] 构建 Level 3 之间的依赖关系...")
            
            # 按父节点分组（同一父节点下的 Level 3 节点）
            level_3_by_parent = {}
            for node in level_3_nodes:
                parent_id = node.get("parent_id")
                if parent_id:
                    if parent_id not in level_3_by_parent:
                        level_3_by_parent[parent_id] = []
                    level_3_by_parent[parent_id].append(node)
            
            # 对每个父节点下的 Level 3 节点进行分析
            for parent_node_id, children_nodes in level_3_by_parent.items():
                if len(children_nodes) > 1:
                    # 获取父节点的概念名称（用于创建新节点时设置 parent_id）
                    parent_concept_name = node_id_to_concept.get(parent_node_id)
                    if not parent_concept_name:
                        # 如果父节点不存在，跳过这个分组
                        print(f"[依赖构建] ⚠ 警告：父节点 ID {parent_node_id} 不存在，跳过该分组")
                        continue
                    
                    level_3_concepts = [node["core_concept"] for node in children_nodes]
                    
                    # 调用 LLM 分析同一父节点下 Level 3 之间的依赖关系
                    level_3_dependencies = await _analyze_level_dependencies(
                        level_3_concepts,
                        level=3,
                        textbook_name=textbook_name,
                        parent_concept=parent_concept_name,
                        client=client,
                        model=model,
                        api_endpoint=api_endpoint,
                        api_key=api_key
                    )
                    
                    # 添加边到临时图（检测循环）
                    for dep in level_3_dependencies:
                        source_concept = dep["source"]
                        target_concept = dep["target"]
                        
                        # 确保节点存在（如果不存在则自动创建，使用当前父节点）
                        source_id = _ensure_node_exists(source_concept, level=3, parent_concept=parent_concept_name)
                        target_id = _ensure_node_exists(target_concept, level=3, parent_concept=parent_concept_name)
                        
                        # 检查是否会形成循环
                        temp_graph.add_edge(source_id, target_id)
                        if not nx.is_directed_acyclic_graph(temp_graph):
                            # 如果形成循环，移除这条边
                            temp_graph.remove_edge(source_id, target_id)
                            cycles_detected += 1
                            print(f"[依赖构建] ⚠ 检测到循环依赖（已避免）: {source_concept} -> {target_concept}")
                        else:
                            all_edges.append((source_id, target_id))
                            level_3_edges += 1
        
        # ========== 4. 批量更新到数据库 ==========
        print(f"[依赖构建] 更新依赖关系到数据库...")
        edges_added = 0
        
        with db._get_connection() as conn:
            cursor = conn.cursor()
            
            # 批量插入新的依赖关系
            for source_id, target_id in all_edges:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO knowledge_dependencies 
                        (source_node_id, target_node_id, dependency_type, created_at)
                        VALUES (?, ?, ?, datetime('now'))
                    """, (source_id, target_id, "depends_on"))
                    if cursor.rowcount > 0:
                        edges_added += 1
                except Exception as e:
                    print(f"[依赖构建] ⚠ 插入依赖关系失败: {source_id} -> {target_id}: {e}")
            
            conn.commit()
        
        total_edges = level_1_edges + level_2_edges + level_3_edges
        
        print(f"[依赖构建] ✓ 完成依赖关系构建")
        print(f"[依赖构建]   Level 1 依赖: {level_1_edges} 条")
        print(f"[依赖构建]   Level 2 依赖: {level_2_edges} 条")
        print(f"[依赖构建]   Level 3 依赖: {level_3_edges} 条")
        print(f"[依赖构建]   总依赖关系: {total_edges} 条")
        print(f"[依赖构建]   检测到循环: {cycles_detected} 个（已避免）")
        print(f"[依赖构建]   成功写入数据库: {edges_added} 条")
        
        return {
            "success": True,
            "level_1_edges": level_1_edges,
            "level_2_edges": level_2_edges,
            "level_3_edges": level_3_edges,
            "total_edges": total_edges,
            "edges_added": edges_added,
            "cycles_detected": cycles_detected,
            "message": f"成功构建依赖关系：Level 1 ({level_1_edges}), Level 2 ({level_2_edges}), Level 3 ({level_3_edges})，共 {total_edges} 条，避免 {cycles_detected} 个循环"
        }
        
    except Exception as e:
        error_msg = f"构建依赖关系失败: {str(e)}"
        print(f"[依赖构建] ✗ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "level_1_edges": 0,
            "level_2_edges": 0,
            "level_3_edges": 0,
            "total_edges": 0,
            "edges_added": 0,
            "cycles_detected": 0,
            "message": error_msg
        }


async def _analyze_level_dependencies(
    concepts: List[str],
    level: int,
    textbook_name: str,
    client: Any,
    model: str,
    api_endpoint: str,
    api_key: str,
    parent_concept: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    使用 LLM 分析指定层级知识点之间的依赖关系
    
    Args:
        concepts: 知识点概念列表
        level: 层级（1, 2, 或 3）
        textbook_name: 教材名称
        client: OpenRouter 客户端
        model: 模型名称
        api_endpoint: API 端点
        api_key: API 密钥
        parent_concept: 父节点概念（可选，用于 Level 2 和 Level 3）
        
    Returns:
        依赖关系列表，每个元素包含 source 和 target
    """
    if len(concepts) < 2:
        return []
    
    # 构建系统提示词
    level_names = {1: "一级全局", 2: "二级章节", 3: "三级原子"}
    level_name = level_names.get(level, "未知")
    
    system_prompt = f"""你是一位资深的计算机科学教育专家，专门从事知识点学习路径分析工作。你的任务是分析给定知识点之间的学习顺序依赖关系。

**重要原则**：
1. **基于学习路径**：依赖关系应反映学习顺序，即"学习 A 之前必须先理解 B"
2. **避免循环依赖**：不能创建循环依赖（A依赖B，B依赖C，C依赖A）
3. **必要性**：只标记真正必要的依赖关系，不要过度连接
4. **简洁性**：每个知识点的前置依赖数量应该控制在 0-3 个

**分析标准**：
- 如果理解概念 A 需要先掌握概念 B，则 B -> A（B 是 A 的前置依赖）
- 如果两个概念可以独立学习，则不应该有依赖关系
- 如果两个概念是平行的、互补的，则不应该有依赖关系
- 依赖关系应该基于知识的内在逻辑，而非简单的包含关系

请严格按照以下 JSON 格式返回，不要添加任何额外的文本、说明或代码块标记：

```json
{{
  "dependencies": [
    {{
      "source": "前置知识点名称",
      "target": "依赖知识点名称"
    }},
    ...
  ]
}}
```

**重要要求**：
1. 必须返回所有有效的依赖关系
2. source 和 target 必须是输入列表中的知识点名称（完全一致）
3. 不要创建循环依赖
4. 不要创建自环（source 和 target 不能相同）
5. 如果没有任何依赖关系，返回空的 dependencies 数组"""
    
    # 构建用户提示词
    concepts_list_str = "\n".join([f"{i+1}. {concept}" for i, concept in enumerate(concepts)])
    
    if parent_concept:
        user_prompt = f"""请分析以下{level_name}知识点之间的学习顺序依赖关系。

**教材名称：** {textbook_name}
**父节点：** {parent_concept}
**知识点数量：** {len(concepts)}

**知识点列表：**
{concepts_list_str}

请仔细分析每个知识点，确定哪些知识点是其他知识点的前置依赖。只标记真正必要的、基于学习路径的依赖关系。"""
    else:
        user_prompt = f"""请分析以下{level_name}知识点之间的学习顺序依赖关系。

**教材名称：** {textbook_name}
**知识点数量：** {len(concepts)}

**知识点列表：**
{concepts_list_str}

请仔细分析每个知识点，确定哪些知识点是其他知识点的前置依赖。只标记真正必要的、基于学习路径的依赖关系。"""
    
    # 准备 API 请求
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/your-repo",
        "X-Title": "AI Question Generator",
    }
    
    # 估算需要的 tokens
    estimated_tokens = len(system_prompt) + len(user_prompt) + len(concepts) * 50 + 2000
    max_tokens = get_max_output_tokens(model, "knowledge_extraction")
    max_tokens = min(max_tokens, max(estimated_tokens, 4000))
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    
    try:
        # 调用 API
        timeout_config = get_timeout_config(model, is_stream=False)
        async with httpx.AsyncClient(timeout=timeout_config) as http_client:
            response = await http_client.post(
                api_endpoint,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" not in result or len(result["choices"]) == 0:
                print(f"[依赖构建] ⚠ API 返回结果中没有 choices 字段")
                return []
            
            generated_text = result["choices"][0]["message"]["content"].strip()
            
            # 清理代码块标记
            if generated_text.startswith("```json"):
                generated_text = generated_text[7:].strip()
            elif generated_text.startswith("```"):
                generated_text = generated_text[3:].strip()
            if generated_text.endswith("```"):
                generated_text = generated_text[:-3].strip()
            
            # 解析 JSON
            try:
                dependencies_data = json.loads(generated_text)
            except json.JSONDecodeError as e:
                print(f"[依赖构建] ⚠ JSON 解析失败: {e}")
                print(f"[依赖构建] 原始响应（前500字符）: {generated_text[:500]}")
                return []
            
            # 提取依赖关系
            dependencies_list = dependencies_data.get("dependencies", [])
            
            # 验证依赖关系
            valid_dependencies = []
            concepts_set = set(concepts)
            
            for dep in dependencies_list:
                source = dep.get("source", "").strip()
                target = dep.get("target", "").strip()
                
                # 验证 source 和 target 都在概念列表中
                if source in concepts_set and target in concepts_set and source != target:
                    valid_dependencies.append({
                        "source": source,
                        "target": target
                    })
                else:
                    if source not in concepts_set:
                        print(f"[依赖构建] ⚠ 警告：source '{source}' 不在概念列表中")
                    if target not in concepts_set:
                        print(f"[依赖构建] ⚠ 警告：target '{target}' 不在概念列表中")
            
            return valid_dependencies
            
    except Exception as e:
        print(f"[依赖构建] ⚠ 分析依赖关系失败: {e}")
        return []


# 全局知识图谱管理器实例
knowledge_graph = KnowledgeGraphManager()


# ========== 使用示例 ==========
"""
使用示例：

1. 基本使用：
    from graph_manager import knowledge_graph
    
    # 自动加载图（首次调用时）
    prerequisites = knowledge_graph.get_prerequisite_context("死锁")
    for prereq in prerequisites:
        print(f"{prereq['concept']} (深度: {prereq['depth']})")
        print(f"  摘要: {prereq['summary']}")
    
2. 手动重新加载图：
    knowledge_graph.reload()
    
3. 获取知识点详细信息：
    info = knowledge_graph.get_concept_info("死锁")
    if info:
        print(f"前置依赖: {info['prerequisites']}")
        print(f"后续依赖: {info['dependents']}")
    
4. 查找两个知识点之间的路径：
    path = knowledge_graph.find_path("进程同步", "死锁")
    if path:
        print(f"路径: {' -> '.join(path)}")
    
5. 获取图的统计信息：
    stats = knowledge_graph.get_graph_stats()
    print(f"节点数: {stats['total_nodes']}, 边数: {stats['total_edges']}")

6. 重构知识点层级结构：
    from graph_manager import reconstruct_hierarchy
    
    # 异步调用层级重构
    result = await reconstruct_hierarchy(textbook_id="your-textbook-id")
    if result["success"]:
        print(f"成功重构：Level 1 ({result['level_1_count']}), "
              f"Level 2 ({result['level_2_count']}), "
              f"Level 3 ({result['level_3_count']})")
        print(f"建立的父子关系: {result['relationships_built']} 个")
    else:
        print(f"重构失败: {result['message']}")

7. 构建横向依赖关系（在层级重构后调用）：
    from graph_manager import build_dependency_edges
    
    # 异步调用依赖关系构建
    result = await build_dependency_edges(textbook_id="your-textbook-id")
    if result["success"]:
        print(f"成功构建依赖关系：")
        print(f"  Level 1 依赖: {result['level_1_edges']} 条")
        print(f"  Level 2 依赖: {result['level_2_edges']} 条")
        print(f"  Level 3 依赖: {result['level_3_edges']} 条")
        print(f"  总依赖关系: {result['total_edges']} 条")
        print(f"  避免循环: {result['cycles_detected']} 个")
    else:
        print(f"构建失败: {result['message']}")

8. 完整的层级和依赖构建流程：
    from graph_manager import reconstruct_hierarchy, build_dependency_edges
    
    # 第一步：重构层级结构
    hierarchy_result = await reconstruct_hierarchy(textbook_id="your-textbook-id")
    if hierarchy_result["success"]:
        # 第二步：构建横向依赖关系
        dependency_result = await build_dependency_edges(textbook_id="your-textbook-id")
        if dependency_result["success"]:
            print("✓ 层级结构和依赖关系构建完成")
        else:
            print(f"依赖关系构建失败: {dependency_result['message']}")
    else:
        print(f"层级重构失败: {hierarchy_result['message']}")
"""

