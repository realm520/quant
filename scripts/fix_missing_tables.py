#!/usr/bin/env python3
"""修复缺失的表 - 删除已存在的约束后重新创建表."""

import json
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    import psycopg2
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

# 需要删除的约束
CONSTRAINTS_TO_DROP = [
    "uq_xt_order_id_time_account",  # xt_order_update
    "uq_xt_trade_id_account",        # xt_trade_update
]

# 创建表的 SQL（不包含约束，约束稍后单独创建）
CREATE_ORDER_TABLE = """
CREATE TABLE IF NOT EXISTS xt_order_update (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    account_id VARCHAR(64),
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(50) NOT NULL,
    client_order_id VARCHAR(50),
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(30) NOT NULL,
    position_side VARCHAR(10),
    quantity NUMERIC(30, 10) NOT NULL,
    price NUMERIC(30, 10),
    filled_quantity NUMERIC(30, 10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    time_in_force VARCHAR(10),
    create_time TIMESTAMP WITHOUT TIME ZONE,
    update_time_order TIMESTAMP WITHOUT TIME ZONE,
    raw_data TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
"""

CREATE_TRADE_TABLE = """
CREATE TABLE IF NOT EXISTS xt_trade_update (
    id BIGSERIAL PRIMARY KEY,
    update_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    account_id VARCHAR(64),
    symbol VARCHAR(20) NOT NULL,
    order_id VARCHAR(50) NOT NULL,
    trade_id VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price NUMERIC(30, 10) NOT NULL,
    quantity NUMERIC(30, 10) NOT NULL,
    quote_quantity NUMERIC(30, 10) NOT NULL,
    commission NUMERIC(30, 10),
    commission_asset VARCHAR(20),
    is_maker BOOLEAN DEFAULT FALSE,
    position_side VARCHAR(10),
    raw_data TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc')
);
"""


def fix_missing_tables():
    """修复缺失的表."""
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor() as cur:
            print("=" * 80)
            print("修复缺失的表")
            print("=" * 80)
            print()
            
            # 1. 删除已存在的约束（如果存在）
            print("步骤 1: 删除已存在的约束...")
            for constraint_name in CONSTRAINTS_TO_DROP:
                try:
                    # 检查约束是否存在
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM pg_constraint 
                            WHERE conname = %s
                        )
                    """, (constraint_name,))
                    exists = cur.fetchone()[0]
                    
                    if exists:
                        # 查找约束所属的表
                        cur.execute("""
                            SELECT conrelid::regclass::text
                            FROM pg_constraint
                            WHERE conname = %s
                        """, (constraint_name,))
                        result = cur.fetchone()
                        if result:
                            table_name = result[0]
                            print(f"  找到约束 {constraint_name} 在表 {table_name} 上")
                            
                            # 删除约束
                            cur.execute(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')
                            conn.commit()
                            print(f"  ✓ 已删除约束: {constraint_name}")
                        else:
                            print(f"  ⚠ 约束 {constraint_name} 存在但找不到所属表")
                    else:
                        print(f"  - 约束 {constraint_name} 不存在，跳过")
                except Exception as e:
                    conn.rollback()
                    print(f"  ✗ 删除约束 {constraint_name} 时出错: {e}")
            
            print()
            
            # 2. 创建表
            print("步骤 2: 创建缺失的表...")
            tables_to_create = {
                "xt_order_update": CREATE_ORDER_TABLE,
                "xt_trade_update": CREATE_TRADE_TABLE,
            }
            
            for table_name, create_sql in tables_to_create.items():
                try:
                    # 检查表是否存在
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_schema = 'public' 
                            AND table_name = %s
                        )
                    """, (table_name,))
                    exists = cur.fetchone()[0]
                    
                    if exists:
                        print(f"  ✓ 表 {table_name} 已存在，跳过")
                    else:
                        print(f"  创建表: {table_name}...")
                        cur.execute(create_sql)
                        conn.commit()
                        print(f"  ✓ 已创建表: {table_name}")
                except Exception as e:
                    conn.rollback()
                    print(f"  ✗ 创建表 {table_name} 时出错: {e}")
            
            print()
            
            # 3. 创建索引和约束
            print("步骤 3: 创建索引和约束...")
            
            # xt_order_update 的索引和约束
            order_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_xt_order_update_update_time ON xt_order_update(update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_update_account_id ON xt_order_update(account_id)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_update_symbol ON xt_order_update(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_update_order_id ON xt_order_update(order_id)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_update_status ON xt_order_update(status)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_id_time ON xt_order_update(order_id, update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_symbol_status_time ON xt_order_update(symbol, status, update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_time ON xt_order_update(update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_order_account_time ON xt_order_update(account_id, update_time)",
            ]
            order_constraint = "ALTER TABLE xt_order_update ADD CONSTRAINT uq_xt_order_id_time_account UNIQUE (order_id, update_time, account_id)"
            
            for sql in order_indexes:
                try:
                    cur.execute(sql)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"  ⚠ 创建索引失败（可能已存在）: {e}")
            
            try:
                cur.execute(order_constraint)
                conn.commit()
                print("  ✓ 已创建约束: uq_xt_order_id_time_account")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("  - 约束 uq_xt_order_id_time_account 已存在，跳过")
                else:
                    print(f"  ✗ 创建约束失败: {e}")
            
            # xt_trade_update 的索引和约束
            trade_indexes = [
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_update_update_time ON xt_trade_update(update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_update_account_id ON xt_trade_update(account_id)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_update_symbol ON xt_trade_update(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_update_order_id ON xt_trade_update(order_id)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_update_trade_id ON xt_trade_update(trade_id)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_symbol_time ON xt_trade_update(symbol, update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_order_trade ON xt_trade_update(order_id, trade_id)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_time ON xt_trade_update(update_time)",
                "CREATE INDEX IF NOT EXISTS idx_xt_trade_account_time ON xt_trade_update(account_id, update_time)",
            ]
            trade_constraint = "ALTER TABLE xt_trade_update ADD CONSTRAINT uq_xt_trade_id_account UNIQUE (trade_id, account_id)"
            
            for sql in trade_indexes:
                try:
                    cur.execute(sql)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"  ⚠ 创建索引失败（可能已存在）: {e}")
            
            try:
                cur.execute(trade_constraint)
                conn.commit()
                print("  ✓ 已创建约束: uq_xt_trade_id_account")
            except Exception as e:
                conn.rollback()
                if "already exists" in str(e).lower():
                    print("  - 约束 uq_xt_trade_id_account 已存在，跳过")
                else:
                    print(f"  ✗ 创建约束失败: {e}")
            
            print()
            print("=" * 80)
            print("完成！")
            print("=" * 80)
            
            # 验证表是否存在
            print("\n验证表是否存在:")
            for table_name in ["xt_order_update", "xt_trade_update"]:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()[0]
                if exists:
                    print(f"  ✓ {table_name} 存在")
                else:
                    print(f"  ✗ {table_name} 不存在")
            
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    fix_missing_tables()
