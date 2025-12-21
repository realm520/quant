#!/usr/bin/env python3
"""手动创建缺失的 XT 表.

如果表创建失败，可以使用此脚本手动创建。
"""

import json
import sys
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

# xt_order_update 表定义
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

CREATE INDEX IF NOT EXISTS idx_xt_order_update_update_time ON xt_order_update(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_update_account_id ON xt_order_update(account_id);
CREATE INDEX IF NOT EXISTS idx_xt_order_update_symbol ON xt_order_update(symbol);
CREATE INDEX IF NOT EXISTS idx_xt_order_update_order_id ON xt_order_update(order_id);
CREATE INDEX IF NOT EXISTS idx_xt_order_update_status ON xt_order_update(status);
CREATE INDEX IF NOT EXISTS idx_xt_order_id_time ON xt_order_update(order_id, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_symbol_status_time ON xt_order_update(symbol, status, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_time ON xt_order_update(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_order_account_time ON xt_order_update(account_id, update_time);

-- 唯一约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_xt_order_id_time_account'
    ) THEN
        ALTER TABLE xt_order_update 
        ADD CONSTRAINT uq_xt_order_id_time_account 
        UNIQUE (order_id, update_time, account_id);
    END IF;
END $$;
"""

# xt_trade_update 表定义
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

CREATE INDEX IF NOT EXISTS idx_xt_trade_update_update_time ON xt_trade_update(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_update_account_id ON xt_trade_update(account_id);
CREATE INDEX IF NOT EXISTS idx_xt_trade_update_symbol ON xt_trade_update(symbol);
CREATE INDEX IF NOT EXISTS idx_xt_trade_update_order_id ON xt_trade_update(order_id);
CREATE INDEX IF NOT EXISTS idx_xt_trade_update_trade_id ON xt_trade_update(trade_id);
CREATE INDEX IF NOT EXISTS idx_xt_trade_symbol_time ON xt_trade_update(symbol, update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_order_trade ON xt_trade_update(order_id, trade_id);
CREATE INDEX IF NOT EXISTS idx_xt_trade_time ON xt_trade_update(update_time);
CREATE INDEX IF NOT EXISTS idx_xt_trade_account_time ON xt_trade_update(account_id, update_time);

-- 唯一约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_xt_trade_id_account'
    ) THEN
        ALTER TABLE xt_trade_update 
        ADD CONSTRAINT uq_xt_trade_id_account 
        UNIQUE (trade_id, account_id);
    END IF;
END $$;
"""


def create_missing_tables():
    """创建缺失的表."""
    conn = psycopg2.connect(**db_params)
    
    try:
        with conn.cursor() as cur:
            print("=" * 80)
            print("创建缺失的 XT 表")
            print("=" * 80)
            print()
            
            # 检查表是否存在
            tables_to_create = []
            for table_name in ["xt_order_update", "xt_trade_update"]:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    )
                """, (table_name,))
                exists = cur.fetchone()[0]
                if not exists:
                    tables_to_create.append(table_name)
                    print(f"✗ 表不存在: {table_name}")
                else:
                    print(f"✓ 表已存在: {table_name}")
            
            if not tables_to_create:
                print("\n所有表都已存在，无需创建。")
                return
            
            print(f"\n需要创建 {len(tables_to_create)} 个表")
            print("确认要创建吗？(yes/no): ", end="")
            confirmation = input().strip().lower()
            
            if confirmation != "yes":
                print("操作已取消。")
                return
            
            print("\n开始创建表...")
            print("-" * 80)
            
            # 创建 xt_order_update
            if "xt_order_update" in tables_to_create:
                try:
                    print("创建表: xt_order_update...")
                    cur.execute(CREATE_ORDER_TABLE)
                    conn.commit()
                    print("✓ 已创建: xt_order_update")
                except Exception as e:
                    conn.rollback()
                    print(f"✗ 创建失败: xt_order_update - {e}")
            
            # 创建 xt_trade_update
            if "xt_trade_update" in tables_to_create:
                try:
                    print("创建表: xt_trade_update...")
                    cur.execute(CREATE_TRADE_TABLE)
                    conn.commit()
                    print("✓ 已创建: xt_trade_update")
                except Exception as e:
                    conn.rollback()
                    print(f"✗ 创建失败: xt_trade_update - {e}")
            
            print("-" * 80)
            print("\n完成！")
            
            # 再次验证
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
                    print(f"✓ {table_name} 存在")
                else:
                    print(f"✗ {table_name} 不存在")
            
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    create_missing_tables()
