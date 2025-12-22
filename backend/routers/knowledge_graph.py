"""
知识图谱相关路由
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from graph_manager import knowledge_graph
from database import db

router = APIRouter(prefix="/knowledge-graph", tags=["知识图谱"])


@router.get("/graph-data")
async def get_graph_data(
    file_id: Optional[str] = Query(None, description="文件 ID（可选，如果提供则只返回该文件的知识点）"),
    textbook_id: Optional[str] = Query(None, description="教材 ID（可选，如果提供则返回该教材的所有知识点）"),
    max_nodes: int = Query(100, description="最大节点数（默认 100）")
):
    """
    获取知识图谱数据（用于前端可视化）
    
    Args:
        file_id: 文件 ID（可选）
        textbook_id: 教材 ID（可选）
        max_nodes: 最大节点数
        
    Returns:
        知识图谱数据，包含节点和边的列表
    """
    try:
        # 重新加载图（确保数据最新）
        node_count = knowledge_graph.reload()
        print(f"[知识图谱API] 重新加载完成，节点数: {node_count}")
        
        # 获取所有节点
        all_nodes = list(knowledge_graph.graph.nodes())
        print(f"[知识图谱API] 当前图中有 {len(all_nodes)} 个节点")
        
        # 如果指定了 file_id，只返回该文件的知识点
        if file_id:
            file_nodes = []
            for node in all_nodes:
                metadata = knowledge_graph.concept_metadata.get(node, {})
                file_ids = metadata.get("file_ids", set())
                if file_id in file_ids:
                    file_nodes.append(node)
            all_nodes = file_nodes
        
        # 如果指定了 textbook_id，返回该教材的所有知识点
        elif textbook_id:
            # 获取教材的所有文件
            textbook_files = db.get_textbook_files(textbook_id)
            file_ids = {f["file_id"] for f in textbook_files}
            
            textbook_nodes = []
            for node in all_nodes:
                metadata = knowledge_graph.concept_metadata.get(node, {})
                node_file_ids = metadata.get("file_ids", set())
                if node_file_ids & file_ids:  # 有交集
                    textbook_nodes.append(node)
            all_nodes = textbook_nodes
        
        # 限制节点数量
        if len(all_nodes) > max_nodes:
            # 优先选择有更多连接关系的节点
            node_degrees = {
                node: knowledge_graph.graph.degree(node)
                for node in all_nodes
            }
            sorted_nodes = sorted(
                all_nodes,
                key=lambda n: node_degrees.get(n, 0),
                reverse=True
            )
            all_nodes = sorted_nodes[:max_nodes]
        
        # 构建子图（只包含选中的节点及其之间的边）
        subgraph_nodes = set(all_nodes)
        
        # 构建节点数据
        nodes_data = []
        # 构建概念到节点ID的映射（用于查找层级信息）
        concept_to_node_id = {}
        for node_name in all_nodes:
            metadata = knowledge_graph.concept_metadata.get(node_name, {})
            node_id = metadata.get("node_id")
            if node_id:
                concept_to_node_id[node_name] = node_id
        
        for node in all_nodes:
            metadata = knowledge_graph.concept_metadata.get(node, {})
            
            # 获取节点的连接度（用于可视化）
            in_degree = knowledge_graph.graph.in_degree(node)
            out_degree = knowledge_graph.graph.out_degree(node)
            total_degree = in_degree + out_degree
            
            # 获取层级信息
            node_id = metadata.get("node_id")
            # 优先使用 concept_metadata 中的 level 和 parent_id
            level = metadata.get("level")  # 可能为 None
            parent_id = metadata.get("parent_id")
            parent_concept = None
            hierarchy_path = node
            
            # 如果 metadata 中没有 level 或 parent_id，从数据库查询
            node_info = None
            if node_id:
                if level is None or parent_id is None:
                    node_info = db.get_knowledge_node(node_id)
                    if node_info:
                        # 只有在 metadata 中没有时才使用数据库的值
                        if level is None:
                            level = node_info.get("level", 3)  # 默认三级
                        if parent_id is None:
                            parent_id = node_info.get("parent_id")
                else:
                    # metadata 中已有 level 和 parent_id，但仍需要 node_info 来构建层级路径
                    node_info = db.get_knowledge_node(node_id)
            
            if level is None:
                # 如果 node_id 也不存在，使用默认值
                level = 3
            
            # 构建层级路径（需要从数据库查询父节点信息）
            if node_info:
                path_parts = []
                current_node_info = node_info
                current_level = level
                
                # 向上溯源构建路径
                while current_node_info:
                    current_concept = current_node_info.get("core_concept", "")
                    if current_concept:
                        path_parts.insert(0, current_concept)
                    
                    if current_level == 1:
                        break
                    
                    parent_id_temp = current_node_info.get("parent_id")
                    if parent_id_temp:
                        parent_node_info = db.get_knowledge_node(parent_id_temp)
                        if parent_node_info:
                            current_node_info = parent_node_info
                            current_level = parent_node_info.get("level", 3)
                        else:
                            break
                    else:
                        break
                
                if path_parts:
                    hierarchy_path = " > ".join(path_parts)
                
                # 获取父节点概念
                if parent_id:
                    parent_node_info = db.get_knowledge_node(parent_id)
                    if parent_node_info:
                        parent_concept = parent_node_info.get("core_concept", "")
            
            # 根据层级设置节点形状和颜色
            # Level 1: 大圆形，深蓝色
            # Level 2: 中等圆形，蓝色
            # Level 3: 小圆形，根据 Bloom 层级设置颜色
            level_colors = {
                1: "#1e40af",  # 深蓝色 - Level 1
                2: "#3b82f6",  # 蓝色 - Level 2
                3: None,  # Level 3 使用 Bloom 颜色
            }
            
            # 根据 Bloom 层级设置颜色（仅用于 Level 3）
            bloom_level = metadata.get("bloom_level")
            if bloom_level is None or not isinstance(bloom_level, int) or bloom_level < 1 or bloom_level > 6:
                bloom_level = 3  # 默认设置为应用层级
            
            bloom_colors = {
                1: "#93c5fd",  # 蓝色 - 记忆
                2: "#86efac",  # 绿色 - 理解
                3: "#fde047",  # 黄色 - 应用
                4: "#f97316",  # 橙色 - 分析
                5: "#ef4444",  # 红色 - 评价
                6: "#a855f7",  # 紫色 - 创造
            }
            
            # 确定最终颜色
            if level == 1:
                color = level_colors[1]
                node_size = max(25, min(35, total_degree * 2 + 25))  # Level 1 更大
                node_shape = "dot"
            elif level == 2:
                color = level_colors[2]
                node_size = max(15, min(25, total_degree * 2 + 15))  # Level 2 中等
                node_shape = "dot"
            else:
                color = bloom_colors.get(bloom_level, "#fde047")  # Level 3 使用 Bloom 颜色
                node_size = max(5, min(20, total_degree * 2 + 5))  # Level 3 较小
                node_shape = "dot"
            
            nodes_data.append({
                "id": node,
                "label": node,
                "level": level,
                "parent_id": parent_id,
                "parent_concept": parent_concept,
                "hierarchy_path": hierarchy_path,
                "bloom_level": bloom_level,
                "color": color,
                "size": node_size,
                "shape": node_shape,
                "in_degree": in_degree,
                "out_degree": out_degree,
                "metadata": {
                    "prerequisites": metadata.get("prerequisites", []),
                    "confusion_points": metadata.get("confusion_points", [])[:3],  # 最多3个
                    "application_scenarios": metadata.get("application_scenarios", [])[:2],  # 最多2个
                    "file_ids": list(metadata.get("file_ids", set())),
                }
            })
        
        # 构建边数据（只包含子图中的边）
        edges_data = []
        for source in all_nodes:
            successors = list(knowledge_graph.graph.successors(source))
            for target in successors:
                if target in subgraph_nodes:
                    # 获取边的属性（relation 类型）
                    edge_data = knowledge_graph.graph.get_edge_data(source, target)
                    relation = edge_data.get("relation", "depends_on") if edge_data else "depends_on"
                    
                    # 根据关系类型设置标签
                    if relation == "parent_child":
                        label = "属于"
                    else:
                        label = "依赖"
                    
                    edges_data.append({
                        "source": source,
                        "target": target,
                        "relation": relation,
                        "label": label
                    })
        
        # 统计各层级的节点数量
        level_counts = {1: 0, 2: 0, 3: 0}
        for node in nodes_data:
            level = node.get("level", 3)
            if level in level_counts:
                level_counts[level] += 1
        
        return JSONResponse(content={
            "nodes": nodes_data,
            "links": edges_data,
            "stats": {
                "total_nodes": len(nodes_data),
                "total_edges": len(edges_data),
                "level_counts": level_counts,
            }
        })
        
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取知识图谱数据失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取知识图谱数据失败"
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/concept/{concept_name}")
async def get_concept_info(concept_name: str):
    """
    获取知识点的详细信息
    
    Args:
        concept_name: 知识点名称
        
    Returns:
        知识点详细信息
    """
    try:
        info = knowledge_graph.get_concept_info(concept_name)
        if not info:
            raise HTTPException(status_code=404, detail=f"知识点 '{concept_name}' 不存在")
        
        return JSONResponse(content=info)
        
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取知识点信息失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取知识点信息失败"
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/concepts")
async def get_all_concepts(
    file_id: Optional[str] = Query(None, description="文件 ID（可选）"),
    textbook_id: Optional[str] = Query(None, description="教材 ID（可选）")
):
    """
    获取所有知识点列表
    
    Args:
        file_id: 文件 ID（可选）
        textbook_id: 教材 ID（可选）
        
    Returns:
        知识点列表
    """
    try:
        knowledge_graph.reload()
        all_concepts = knowledge_graph.get_all_concepts()
        
        # 如果指定了 file_id，只返回该文件的知识点
        if file_id:
            file_concepts = []
            for concept in all_concepts:
                metadata = knowledge_graph.concept_metadata.get(concept, {})
                file_ids = metadata.get("file_ids", set())
                if file_id in file_ids:
                    file_concepts.append(concept)
            return JSONResponse(content={"concepts": file_concepts})
        
        # 如果指定了 textbook_id，返回该教材的知识点
        if textbook_id:
            textbook_files = db.get_textbook_files(textbook_id)
            file_ids = {f["file_id"] for f in textbook_files}
            
            textbook_concepts = []
            for concept in all_concepts:
                metadata = knowledge_graph.concept_metadata.get(concept, {})
                node_file_ids = metadata.get("file_ids", set())
                if node_file_ids & file_ids:
                    textbook_concepts.append(concept)
            return JSONResponse(content={"concepts": textbook_concepts})
        
        return JSONResponse(content={"concepts": all_concepts})
        
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取知识点列表失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取知识点列表失败"
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/stats")
async def get_graph_stats():
    """
    获取知识图谱统计信息
    
    Returns:
        统计信息
    """
    try:
        knowledge_graph.reload()
        stats = knowledge_graph.get_graph_stats()
        return JSONResponse(content=stats)
        
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取统计信息失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取统计信息失败"
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/questions/{concept_name}")
async def get_concept_questions(concept_name: str):
    """
    获取某个知识点关联的题目
    
    Args:
        concept_name: 知识点名称
        
    Returns:
        题目列表
    """
    try:
        info = knowledge_graph.get_concept_info(concept_name)
        if not info:
            raise HTTPException(status_code=404, detail=f"知识点 '{concept_name}' 不存在")
        
        metadata = info.get("metadata", {})
        file_ids = list(metadata.get("file_ids", set()))
        
        # 获取这些文件的所有题目
        all_questions = []
        for file_id in file_ids:
            questions = db.get_all_questions(file_id=file_id)
            all_questions.extend(questions)
        
        return JSONResponse(content={
            "concept": concept_name,
            "questions": all_questions,
            "total": len(all_questions)
        })
        
    except HTTPException:
        raise
    except Exception as e:
        try:
            error_msg = repr(e) if hasattr(e, '__repr__') else "获取题目失败"
        except (UnicodeEncodeError, UnicodeDecodeError):
            error_msg = "获取题目失败"
        raise HTTPException(status_code=500, detail=error_msg)

