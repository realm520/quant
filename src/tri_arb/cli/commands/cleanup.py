"""数据清理命令模块.

将 scripts/cleanup_old_data.py 的功能包装为 CLI 命令。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
# 从 src/tri_arb/cli/commands/cleanup.py 到项目根目录需要向上5级
_current_file = Path(__file__).resolve()
project_root = _current_file.parent.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入主应用
from scripts.cleanup_old_data import app


def main():
    """数据清理命令入口点，供 uv run 使用。
    
    使用示例:
        # 立即执行清理
        uv run cleanup-old-data cleanup
        
        # 模拟运行（查看将要删除的数据）
        uv run cleanup-old-data cleanup --dry-run
        
        # 启动定时任务模式（每天凌晨2点自动执行）
        uv run cleanup-old-data cleanup --schedule
        
        # 启动定时任务，指定执行时间
        uv run cleanup-old-data cleanup --schedule --schedule-time 03:00
        
        # 停止定时任务
        uv run cleanup-old-data stop
        
        # 查看配置的表列表
        uv run cleanup-old-data list-tables
    """
    app()


if __name__ == "__main__":
    main()

