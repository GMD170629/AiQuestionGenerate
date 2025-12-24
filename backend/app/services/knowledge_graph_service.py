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

from app.core.db import db


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
                ORDER BY created_at ASC
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
                    
                    self.concept_metadata[core_concept] = {
                        "node_id": node_id,
                        "node_ids": [node_id],
                        "chunk_id": row["chunk_id"],
                        "chunk_ids": [row["chunk_id"]],
                        "file_id": row["file_id"],
                        "file_ids": {row["file_id"]},
                        "prerequisites": prerequisites,
                        "confusion_points": confusion_points,
                        "bloom_level": bloom_level,
                        "application_scenarios": application_scenarios or [],
                        "created_at": row["created_at"]
                    }
                    
                    # 在图中添加节点
                    self.graph.add_node(core_concept, **self.concept_metadata[core_concept])
            
            # 第二遍：创建边
            # 1. 创建依赖关系边（基于 knowledge_dependencies 表）
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
            
            # 2. 创建前置依赖关系边（基于 prerequisites_json，向后兼容）
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


# 全局知识图谱管理器实例
knowledge_graph = KnowledgeGraphManager()


# ========== 使用示例 ==========
"""
使用示例：

1. 基本使用：
    # 避免循环导入，使用延迟导入
    # 注意：这里应该使用全局实例，但由于循环导入问题，暂时注释
    # from app.services.knowledge_graph_service import knowledge_graph
    pass  # 如果需要使用，应该在函数内部动态导入
    
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

"""

