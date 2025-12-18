# 数据持久化实现说明

## 概述

已实现完整的数据持久化方案，确保在 Docker 容器删除或更新后，所有数据不会丢失。

## 持久化的数据

以下数据已实现持久化存储：

1. **文件基本信息**
   - 文件 ID (file_id)
   - 原始文件名 (filename)
   - 文件大小 (file_size)
   - 文件格式 (file_format，如 .md)
   - 文件存储路径 (file_path)
   - 上传时间 (upload_time)

2. **文件内容**
   - 文件原始内容（存储在 `uploads/` 目录）

3. **解析后的分片数据**
   - 每个分片的内容 (content)
   - 每个分片的元数据 (metadata)，包括：
     - 标题层级信息 (Header 1, Header 2, Header 3)
     - 章节名称和层级
     - 分片索引信息

4. **文档元数据**
   - 目录结构 (TOC)
   - 统计信息 (statistics)
   - 其他元数据

## 技术实现

### 数据库设计

使用 SQLite 数据库存储所有结构化数据，数据库文件位于 `backend/data/question_generator.db`。

**表结构：**

1. **files 表** - 存储文件基本信息
   - file_id (主键)
   - filename
   - file_size
   - file_format
   - file_path
   - upload_time
   - created_at

2. **chunks 表** - 存储文档分片
   - chunk_id (主键，自增)
   - file_id (外键)
   - chunk_index (分片索引)
   - content (分片内容)
   - metadata_json (元数据 JSON)
   - created_at

3. **file_metadata 表** - 存储文档元数据
   - file_id (主键，外键)
   - metadata_json (元数据 JSON)
   - cached_at

### 代码变更

1. **新增文件：**
   - `backend/database.py` - 数据库操作模块

2. **修改文件：**
   - `backend/document_cache.py` - 重构为使用数据库存储
   - `backend/main.py` - 更新所有文件操作接口使用数据库
   - `docker-compose.yml` - 添加数据目录卷挂载

### Docker 卷挂载

在 `docker-compose.yml` 中配置了以下卷挂载，确保数据持久化：

```yaml
volumes:
  - ./backend:/app
  - ./backend/data:/app/data      # 数据库文件
  - ./backend/uploads:/app/uploads # 上传的文件
```

## 数据恢复

当容器重启或重新创建时：

1. **文件内容**：从 `backend/uploads/` 目录自动恢复
2. **文件信息和分片数据**：从 SQLite 数据库自动恢复
3. **无需重新解析**：所有解析后的数据都保存在数据库中，无需重新处理

## 注意事项

1. **数据库文件位置**：数据库文件存储在 `backend/data/` 目录，已配置为持久化卷
2. **备份建议**：定期备份 `backend/data/` 和 `backend/uploads/` 目录
3. **数据迁移**：如果需要迁移数据，只需复制这两个目录即可

## 测试验证

重启容器后，验证以下功能：

1. 文件列表应显示所有之前上传的文件
2. 文件预览应能正常显示原始文件名和内容
3. 生成题目功能应能正常使用之前解析的分片数据
4. 文件删除功能应同时删除文件、数据库记录和相关分片

