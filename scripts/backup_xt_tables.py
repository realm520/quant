#!/usr/bin/env python3
"""备份 XT 相关的数据库表.

将现有的 XT 表重命名为带时间戳的备份表，以便重新运行程序创建新表。
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("错误: 需要安装 psycopg2")
    print("请运行: pip install psycopg2-binary")
    sys.exit(1)

# 读取数据库配置
project_root = Path(__file__).parent.parent
config_path = project_root / "config" / "accounts.json"
with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

database_url = config["global_settings"]["database_url"]
parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://"))
password = unquote(parsed.password) if parsed.password else None

db_params = {
    "host": parsed.hostname,
    "port": parsed.port or 5432,
    "database": parsed.path.lstrip("/"),
    "user": parsed.username,
    "password": password,
    "sslmode": "require",
}

# XT 相关的表列表
XT_TABLES = [
    # WebSocket 表
    "xt_account_update",
    "xt_spot_update",
    "xt_position_update",
    "xt_order_update",
    "xt_trade_update",
    "xt_transfer_update",
    "xt_connection",
    # REST API 表
    "xt_account_snapshot",
    "xt_position_snapshot",
]


def backup_tables():
    """备份 XT 相关的表."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_suffix = f"_backup_{timestamp}"
    
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("=" * 80)
            print(f"XT 表备份工具 (备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
            print("=" * 80)
            print()
            
            # 检查哪些表存在
            existing_tables = []
            for table_name in XT_TABLES:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()[0]
                if exists:
                    existing_tables.append(table_name)
                    print(f"✓ 找到表: {table_name}")
                else:
                    print(f"✗ 表不存在: {table_name} (跳过)")
            
            if not existing_tables:
                print("\n没有找到需要备份的表。")
                return
            
            print(f"\n共找到 {len(existing_tables)} 个表需要备份")
            print(f"备份后缀: {backup_suffix}")
            print()
            
            # 确认操作
            print("⚠️  警告: 此操作将重命名以下表:")
            for table in existing_tables:
                backup_name = f"{table}{backup_suffix}"
                print(f"  {table} → {backup_name}")
            
            print("\n确认要执行备份吗？(yes/no): ", end="")
            confirmation = input().strip().lower()
            
            if confirmation != "yes":
                print("操作已取消。")
                return
            
            print("\n开始备份...")
            print("-" * 80)
            
            # 备份每个表
            backed_up_tables = []
            for table_name in existing_tables:
                backup_name = f"{table_name}{backup_suffix}"
                
                try:
                    # 检查备份表是否已存在
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = %s
                        )
                    """, (backup_name,))
                    backup_exists = cur.fetchone()[0]
                    
                    if backup_exists:
                        print(f"⚠️  备份表 {backup_name} 已存在，跳过 {table_name}")
                        continue
                    
                    # 重命名表
                    cur.execute(f'ALTER TABLE "{table_name}" RENAME TO "{backup_name}"')
                    conn.commit()
                    
                    # 重命名索引（PostgreSQL 会自动重命名主键索引，但其他索引需要手动处理）
                    cur.execute("""
                        SELECT indexname 
                        FROM pg_indexes 
                        WHERE tablename = %s 
                        AND schemaname = 'public'
                    """, (backup_name,))
                    indexes = cur.fetchall()
                    
                    print(f"✓ 已备份: {table_name} → {backup_name}")
                    if indexes:
                        print(f"  (包含 {len(indexes)} 个索引)")
                    
                    backed_up_tables.append((table_name, backup_name))
                    
                except Exception as e:
                    print(f"✗ 备份失败: {table_name} - {e}")
                    conn.rollback()
            
            print("-" * 80)
            print(f"\n备份完成！共备份 {len(backed_up_tables)} 个表")
            print()
            print("备份的表:")
            for original, backup in backed_up_tables:
                print(f"  {original} → {backup}")
            
            print("\n" + "=" * 80)
            print("现在可以重新运行程序，程序会创建新的表。")
            print("=" * 80)
            
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


def list_backups():
    """列出所有备份表."""
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("=" * 80)
            print("XT 表备份列表")
            print("=" * 80)
            print()
            
            # 查找所有备份表
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name LIKE 'xt_%_backup_%'
                ORDER BY table_name
            """)
            
            backups = cur.fetchall()
            
            if not backups:
                print("没有找到备份表。")
                return
            
            print(f"找到 {len(backups)} 个备份表:\n")
            
            # 按原始表名分组
            backup_groups = {}
            for row in backups:
                backup_name = row['table_name']
                # 提取原始表名（去掉 _backup_YYYYMMDD_HHMMSS）
                parts = backup_name.rsplit('_backup_', 1)
                if len(parts) == 2:
                    original_name = parts[0]
                    timestamp = parts[1]
                    if original_name not in backup_groups:
                        backup_groups[original_name] = []
                    backup_groups[original_name].append((backup_name, timestamp))
            
            for original_name in sorted(backup_groups.keys()):
                print(f"【{original_name}】")
                for backup_name, timestamp in sorted(backup_groups[original_name], reverse=True):
                    # 解析时间戳
                    try:
                        dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        time_str = timestamp
                    print(f"  {backup_name} (备份时间: {time_str})")
                print()
            
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


def restore_backup(backup_name: str, restore_name: str = None):
    """恢复备份表.
    
    Args:
        backup_name: 备份表名
        restore_name: 恢复后的表名（如果不指定，使用原始表名）
    """
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 检查备份表是否存在
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
            """, (backup_name,))
            exists = cur.fetchone()[0]
            
            if not exists:
                print(f"错误: 备份表 {backup_name} 不存在")
                return
            
            # 确定恢复后的表名
            if not restore_name:
                # 从备份名提取原始表名
                parts = backup_name.rsplit('_backup_', 1)
                if len(parts) == 2:
                    restore_name = parts[0]
                else:
                    print(f"错误: 无法从备份名 {backup_name} 提取原始表名")
                    return
            
            # 检查目标表是否已存在
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = %s
                )
            """, (restore_name,))
            target_exists = cur.fetchone()[0]
            
            if target_exists:
                print(f"⚠️  警告: 表 {restore_name} 已存在")
                print("确认要覆盖吗？(yes/no): ", end="")
                confirmation = input().strip().lower()
                if confirmation != "yes":
                    print("操作已取消。")
                    return
                
                # 删除现有表
                cur.execute(f'DROP TABLE IF EXISTS "{restore_name}" CASCADE')
                conn.commit()
            
            # 重命名备份表
            cur.execute(f'ALTER TABLE "{backup_name}" RENAME TO "{restore_name}"')
            conn.commit()
            
            print(f"✓ 已恢复: {backup_name} → {restore_name}")
            
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


def main():
    """主函数."""
    import argparse
    
    parser = argparse.ArgumentParser(description="备份和恢复 XT 数据库表")
    parser.add_argument("action", choices=["backup", "list", "restore"], help="操作: backup(备份), list(列出备份), restore(恢复)")
    parser.add_argument("--backup-name", type=str, help="备份表名（用于 restore 操作）")
    parser.add_argument("--restore-name", type=str, help="恢复后的表名（用于 restore 操作，可选）")
    
    args = parser.parse_args()
    
    if args.action == "backup":
        backup_tables()
    elif args.action == "list":
        list_backups()
    elif args.action == "restore":
        if not args.backup_name:
            print("错误: restore 操作需要指定 --backup-name")
            sys.exit(1)
        restore_backup(args.backup_name, args.restore_name)


if __name__ == "__main__":
    main()
