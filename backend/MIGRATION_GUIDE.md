# 知识点模型重构迁移指南

## 概述

本次重构更新了知识点模型，添加了层级结构和依赖关系支持：

1. **层级结构**：知识点分为三个层级
   - Level 1: 一级全局知识点（全局概念）
   - Level 2: 二级章节知识点（章节级概念）
   - Level 3: 三级原子知识点（具体知识点）

2. **父子关系**：通过 `parent_id` 字段构建一级→二级、二级→三级的层级关系

3. **依赖关系**：通过 `knowledge_dependencies` 表存储横向依赖关系（同级或跨级）

## 数据库变更

### 新增字段

- `knowledge_nodes.level` (INTEGER): 知识点层级，1-3
- `knowledge_nodes.parent_id` (TEXT): 父节点 ID，可为 NULL

### 新增表

- `knowledge_dependencies`: 存储知识点之间的横向依赖关系
  - `source_node_id`: 源节点（依赖者）
  - `target_node_id`: 目标节点（被依赖者）
  - `dependency_type`: 依赖类型（默认为 "depends_on"）

## 自动迁移

数据库初始化时会自动运行迁移，无需手动操作。迁移会：

1. 检查现有表结构
2. 添加缺失的字段（`level` 和 `parent_id`）
3. 创建 `knowledge_dependencies` 表
4. 创建必要的索引

## 手动迁移

如果需要手动运行迁移脚本：

```bash
# 基本迁移（只更新表结构）
python backend/migrations.py

# 迁移并清理旧测试数据
python backend/migrations.py --clean
```

## API 变更

### `store_knowledge_node` 方法

**旧签名**：
```python
store_knowledge_node(
    node_id: str,
    chunk_id: int,
    file_id: str,
    core_concept: str,
    prerequisites: List[str],
    confusion_points: List[str],
    bloom_level: int,
    application_scenarios: Optional[List[str]] = None
)
```

**新签名**：
```python
store_knowledge_node(
    node_id: str,
    chunk_id: int,
    file_id: str,
    core_concept: str,
    level: int,  # 新增：知识点层级（1-3）
    prerequisites: List[str],
    confusion_points: List[str],
    bloom_level: int,
    application_scenarios: Optional[List[str]] = None,
    parent_id: Optional[str] = None  # 新增：父节点 ID
)
```

### 新增方法

- `add_knowledge_dependency(source_node_id, target_node_id, dependency_type)`: 添加依赖关系
- `remove_knowledge_dependency(source_node_id, target_node_id)`: 删除依赖关系
- `get_node_dependencies(node_id)`: 获取节点的依赖关系
- `get_node_dependents(node_id)`: 获取节点的被依赖关系
- `delete_node_dependencies(node_id)`: 删除节点的所有依赖关系
- `get_child_nodes(parent_id)`: 获取节点的子节点

## 数据兼容性

- 现有数据会自动设置 `level = 3`（三级原子点）
- `parent_id` 默认为 `NULL`
- `prerequisites_json` 字段保留用于向后兼容，但建议使用 `knowledge_dependencies` 表

## 注意事项

1. **迁移是安全的**：不会删除现有数据，只会添加新字段
2. **默认值**：旧数据的 `level` 会自动设置为 3
3. **依赖关系**：旧的 `prerequisites` 数据不会自动迁移到 `knowledge_dependencies` 表，需要手动迁移
4. **清理测试数据**：使用 `--clean` 参数会删除孤立的旧测试数据（level=3 且 parent_id=NULL 且没有依赖关系的节点）

## 后续工作

1. 构建知识点层级关系（一级→二级→三级）
2. 将现有的 `prerequisites` 数据迁移到 `knowledge_dependencies` 表
3. 更新知识图谱可视化以支持层级结构

