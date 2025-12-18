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
        for node in all_nodes:
            metadata = knowledge_graph.concept_metadata.get(node, {})
            
            # 获取节点的连接度（用于可视化）
            in_degree = knowledge_graph.graph.in_degree(node)
            out_degree = knowledge_graph.graph.out_degree(node)
            total_degree = in_degree + out_degree
            
            # 根据 Bloom 层级设置颜色
            # 确保 bloom_level 不为 None，如果为 None 或不存在则使用默认值 3
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
            color = bloom_colors.get(bloom_level, "#fde047")  # 默认黄色（应用层级）
            
            nodes_data.append({
                "id": node,
                "label": node,
                "bloom_level": bloom_level,
                "color": color,
                "size": max(5, min(20, total_degree * 2 + 5)),  # 节点大小基于连接度
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
                    edges_data.append({
                        "source": source,
                        "target": target,
                        "relation": "depends_on",
                        "label": "依赖"
                    })
        
        return JSONResponse(content={
            "nodes": nodes_data,
            "links": edges_data,
            "stats": {
                "total_nodes": len(nodes_data),
                "total_edges": len(edges_data),
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

