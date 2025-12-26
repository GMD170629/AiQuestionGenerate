"""
初始化提示词到数据库
从 default_prompts 模块读取默认提示词并导入到数据库
"""
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.db import db
from prompts.default_prompts import get_default_prompts


def init_prompts(force: bool = False) -> int:
    """
    初始化所有默认提示词到数据库
    
    Args:
        force: 是否强制覆盖已存在的提示词
        
    Returns:
        成功初始化的提示词数量
    """
    default_prompts = get_default_prompts()
    count = 0
    
    for prompt_config in default_prompts:
        function_type = prompt_config["function_type"]
        prompt_type = prompt_config["prompt_type"]
        mode = prompt_config.get("mode")
        
        # 检查是否已存在
        existing = db.get_prompt_by_function(function_type, prompt_type, mode)
        if existing and not force:
            print(f"  跳过 {function_type}/{prompt_type}/{mode or 'N/A'}（已存在）")
            continue
        
        # 创建或更新提示词
        import uuid
        if existing:
            prompt_id = existing["prompt_id"]
        else:
            prompt_id = str(uuid.uuid4())
        
        success = db.create_prompt(
            prompt_id=prompt_id,
            function_type=function_type,
            prompt_type=prompt_type,
            mode=mode,
            content=prompt_config["content"],
            parameters=prompt_config.get("parameters"),
            description=prompt_config.get("description")
        )
        
        if success:
            count += 1
            action = "更新" if existing else "创建"
            print(f"  ✓ {action} {function_type}/{prompt_type}/{mode or 'N/A'}")
        else:
            print(f"  ✗ 失败 {function_type}/{prompt_type}/{mode or 'N/A'}")
    
    return count


if __name__ == "__main__":
    import sys
    
    force = "--force" in sys.argv or "-f" in sys.argv
    
    print("=" * 60)
    print("初始化提示词到数据库")
    print("=" * 60)
    print()
    
    count = init_prompts(force=force)
    
    print()
    print("=" * 60)
    print(f"提示词初始化完成！共处理 {count} 个提示词")
    print("=" * 60)

