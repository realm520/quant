#!/usr/bin/env python3
"""数据清理脚本：删除旧数据，默认保留最近3天.

此脚本用于定期清理数据库，释放存储空间。
默认会清理各类「流式推送 / REST 快照 / 多账号分表」中的历史行，不仅限于订单表。
只删除超过保留期的数据，不会影响最近的数据。

未纳入清理的表（避免影响在线状态）：
- connection_status（WebSocket 连接与断线补全指针）
- scheduled_queries（定时任务配置与统计，通常体积极小）

支持两种模式：
1. 立即执行模式（默认）：执行一次清理后退出
2. 定时任务模式：启动后台定时任务，每天自动执行清理

使用示例：
    # 立即执行清理（默认模式）
    uv run cleanup-old-data cleanup
    
    # 模拟运行，查看将要删除的数据
    uv run cleanup-old-data cleanup --dry-run
    
    # 启动定时任务模式（每天凌晨2点自动执行）
    uv run cleanup-old-data cleanup --schedule
    
    # 启动定时任务，指定执行时间为凌晨3点
    uv run cleanup-old-data cleanup --schedule --schedule-time 03:00
    
    # 停止定时任务（如果在运行中，也可以按 Ctrl+C）
    uv run cleanup-old-data stop
    
    # 查看配置的表列表
    uv run cleanup-old-data list-tables
"""

import asyncio
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable

import typer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tri_arb.config.logging import get_logger
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)

app = typer.Typer(help="数据库数据清理工具")

# 全局变量：定时任务控制
_scheduler_thread: Optional[threading.Thread] = None
_scheduler_running = False
_scheduler_lock = threading.Lock()


# 表清理配置
# 静态表配置格式: (表名, 时间字段名, 说明)
STATIC_TABLE_CONFIGS: List[Tuple[str, str, str]] = [
    # ---- XT WebSocket（单表）----
    ("xt_account_update", "update_time", "XT账户更新"),
    ("xt_spot_update", "update_time", "XT现货更新"),
    ("xt_position_update", "update_time", "XT持仓更新"),
    ("xt_order_update", "update_time", "XT订单更新"),
    ("xt_trade_update", "update_time", "XT成交更新"),
    ("xt_transfer_update", "transfer_time", "XT划转记录"),
    ("xt_order_history", "sync_time", "XT历史订单"),
    ("xt_connection", "start_time", "XT连接记录"),
    # ---- Binance WebSocket（单表）----
    ("binance_account_update", "event_time", "Binance账户/持仓更新"),
    ("binance_order_update", "event_time", "Binance订单更新"),
    ("binance_trade_update", "event_time", "Binance成交更新"),
    # ---- Gate WebSocket ----
    ("gate_account_update", "update_time", "Gate账户更新"),
    ("gate_position_update", "update_time", "Gate持仓更新"),
    ("gate_order_update", "update_time", "Gate订单更新"),
    ("gate_trade_update", "create_time", "Gate成交更新"),
    # ---- OKX WebSocket ----
    ("okx_account_update", "update_time", "OKX账户更新"),
    ("okx_position_update", "update_time", "OKX持仓更新"),
    ("okx_order_update", "u_time", "OKX订单更新"),
    ("okx_trade_update", "fill_time", "OKX成交更新"),
    # ---- 通用 REST 聚合表 ----
    ("rest_balances", "query_time", "REST余额快照"),
    ("rest_positions", "query_time", "REST持仓快照"),
    ("rest_orders", "query_time", "REST订单快照"),
    # ---- XT REST（与 exchange_rest 的 xt 快照并行存在的表名）----
    ("xt_account_snapshot", "query_time", "XT账户余额快照"),
    ("xt_position_snapshot", "query_time", "XT持仓快照"),
    # ---- 各所 REST 快照（exchange_rest_models）----
    ("binance_account_snapshot", "query_time", "Binance余额REST快照"),
    ("binance_position_snapshot", "query_time", "Binance持仓REST快照"),
    ("binance_order_snapshot", "query_time", "Binance订单REST快照"),
    ("xt_order_snapshot", "query_time", "XT订单REST快照"),
    ("okx_account_snapshot", "query_time", "OKX余额REST快照"),
    ("okx_position_snapshot", "query_time", "OKX持仓REST快照"),
    ("okx_order_snapshot", "query_time", "OKX订单REST快照"),
    ("gate_account_snapshot", "query_time", "Gate余额REST快照"),
    ("gate_position_snapshot", "query_time", "Gate持仓REST快照"),
    ("gate_order_snapshot", "query_time", "Gate订单REST快照"),
    # ---- 定时计算的时序指标 ----
    ("position_metrics", "timestamp", "持仓指标时序"),
    # ---- ListenKey 历史（体量通常不大，可一并收敛）----
    ("listen_keys", "created_at", "Binance ListenKey 记录"),
]

# 动态表模式（多账号表），格式: (like_pattern, 时间字段名, 说明)
TABLE_PATTERN_CONFIGS: List[Tuple[str, str, str]] = [
    ("xt_account_updates_%", "update_time", "XT账户更新（多账号表）"),
    ("xt_spot_updates_%", "update_time", "XT现货更新（多账号表）"),
    ("xt_position_updates_%", "update_time", "XT持仓更新（多账号表）"),
    ("xt_order_updates_%", "update_time", "XT订单更新（多账号表）"),
    ("xt_trade_updates_%", "update_time", "XT成交更新（多账号表）"),
    ("binance_account_updates_%", "event_time", "Binance账户更新（多账号表）"),
    ("binance_order_updates_%", "event_time", "Binance订单更新（多账号表）"),
    ("binance_trade_updates_%", "event_time", "Binance成交更新（多账号表）"),
]


def _is_safe_identifier(value: str) -> bool:
    """Very small guardrail: only allow [a-zA-Z0-9_]."""
    if not value:
        return False
    return all(ch.isalnum() or ch == "_" for ch in value)


async def discover_tables_by_patterns(
    session: AsyncSession, patterns: Iterable[Tuple[str, str, str]]
) -> list[Tuple[str, str, str]]:
    """Discover tables in public schema by LIKE patterns."""
    discovered: list[Tuple[str, str, str]] = []
    for like_pattern, time_column, description in patterns:
        result = await session.execute(
            text(
                """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public' AND tablename LIKE :pattern
                ORDER BY tablename
                """
            ),
            {"pattern": like_pattern},
        )
        for (table_name,) in result.fetchall():
            # Only accept safe identifiers
            if _is_safe_identifier(table_name) and _is_safe_identifier(time_column):
                discovered.append((table_name, time_column, description))
    return discovered


async def build_table_configs(session: AsyncSession) -> list[Tuple[str, str, str]]:
    """Build final table config list (static + discovered patterns)."""
    configs = list(STATIC_TABLE_CONFIGS)
    discovered = await discover_tables_by_patterns(session, TABLE_PATTERN_CONFIGS)
    # Avoid duplicates if a static table name matches a pattern
    existing = {t for (t, _, _) in configs}
    for table_name, time_column, desc in discovered:
        if table_name not in existing:
            configs.append((table_name, time_column, desc))
    return configs


async def get_table_row_count(session: AsyncSession, table_name: str) -> int:
    """获取表的行数."""
    try:
        result = await session.execute(
            text(f"SELECT COUNT(*) FROM {table_name}")
        )
        return result.scalar() or 0
    except Exception as e:
        logger.warning(f"无法获取表 {table_name} 的行数: {e}")
        return 0


async def cleanup_table(
    session: AsyncSession,
    table_name: str,
    time_column: str,
    cutoff_date: datetime,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """清理指定表的旧数据.
    
    Args:
        session: 数据库会话
        table_name: 表名
        time_column: 时间字段名
        cutoff_date: 截止日期（删除此日期之前的数据）
        dry_run: 是否为模拟运行（不实际删除）
    
    Returns:
        (删除前的行数, 删除的行数)
    """
    try:
        if not _is_safe_identifier(table_name) or not _is_safe_identifier(time_column):
            logger.warning(
                f"跳过不安全的表/字段名: table={table_name!r}, column={time_column!r}"
            )
            return 0, 0

        # 获取删除前的行数
        total_before = await get_table_row_count(session, table_name)
        
        if total_before == 0:
            logger.info(f"表 {table_name} 为空，跳过")
            return 0, 0
        
        # 构建删除SQL
        delete_sql = f"""
            DELETE FROM {table_name}
            WHERE {time_column} < :cutoff_date
        """
        
        if dry_run:
            # 模拟运行：只查询要删除的行数
            count_sql = f"""
                SELECT COUNT(*) FROM {table_name}
                WHERE {time_column} < :cutoff_date
            """
            result = await session.execute(
                text(count_sql), {"cutoff_date": cutoff_date}
            )
            to_delete = result.scalar() or 0
            
            logger.info(
                f"[模拟] 表 {table_name}: 总计 {total_before} 行，"
                f"将删除 {to_delete} 行（{time_column} < {cutoff_date}）"
            )
            return total_before, to_delete
        else:
            # 实际执行删除
            result = await session.execute(
                text(delete_sql), {"cutoff_date": cutoff_date}
            )
            deleted_count = result.rowcount
            
            # 获取删除后的行数
            total_after = await get_table_row_count(session, table_name)
            
            logger.info(
                f"表 {table_name}: 删除前 {total_before} 行，"
                f"删除 {deleted_count} 行，剩余 {total_after} 行"
            )
            
            return total_before, deleted_count
            
    except Exception as e:
        logger.error(f"清理表 {table_name} 时出错: {e}", exc_info=True)
        return 0, 0


async def vacuum_tables(db_manager: DatabaseManager, table_names: list[str]) -> None:
    """对多个表执行 VACUUM FULL 回收磁盘空间.
    
    使用 VACUUM FULL 重写整个表，彻底回收磁盘空间。
    注意: VACUUM FULL 会锁表，但清理后数据量很少，锁定时间极短。
    不能在事务中执行，需要使用 autocommit 模式的原始连接。
    """
    engine = db_manager.async_engine
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        
        for table_name in table_names:
            try:
                logger.info(f"  VACUUM FULL {table_name} ...")
                await conn.execute(text(f"VACUUM FULL {table_name}"))
                logger.info(f"  ✅ VACUUM FULL {table_name} 完成")
            except Exception as e:
                logger.warning(f"  ⚠️ VACUUM FULL {table_name} 失败，尝试普通 VACUUM...")
                try:
                    await conn.execute(text(f"VACUUM (ANALYZE) {table_name}"))
                    logger.info(f"  ✅ VACUUM {table_name} 完成（普通模式）")
                except Exception as e2:
                    logger.warning(f"  ⚠️ VACUUM {table_name} 也失败: {e2}")


async def cleanup_all_tables(
    db_manager: DatabaseManager,
    retention_days: int = 3,
    dry_run: bool = False,
    *,
    only_orders: bool = False,
) -> Dict[str, Dict[str, int]]:
    """清理所有配置的表.
    
    Args:
        db_manager: 数据库管理器
        retention_days: 保留天数（默认3天）
        dry_run: 是否为模拟运行
    
    Returns:
        统计信息字典
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    logger.info(f"开始清理数据（保留 {retention_days} 天，截止日期: {cutoff_date})")
    if dry_run:
        logger.info("⚠️  这是模拟运行，不会实际删除数据")
    
    stats = {
        "total_before": 0,
        "total_deleted": 0,
        "tables": {},
    }
    
    tables_with_deletes = []
    
    async with db_manager.session() as session:
        table_configs = await build_table_configs(session)
        if only_orders:
            table_configs = [
                (t, c, d)
                for (t, c, d) in table_configs
                if ("order" in t.lower()) or ("订单" in (d or ""))
            ]
        # 为每个表执行清理
        for table_name, time_column, description in table_configs:
            logger.info(f"\n处理表: {table_name} ({description})")
            
            before, deleted = await cleanup_table(
                session=session,
                table_name=table_name,
                time_column=time_column,
                cutoff_date=cutoff_date,
                dry_run=dry_run,
            )
            
            stats["total_before"] += before
            stats["total_deleted"] += deleted
            stats["tables"][table_name] = {
                "before": before,
                "deleted": deleted,
            }
            
            # 如果不是模拟运行，提交事务
            if not dry_run:
                await session.commit()
                if deleted > 0:
                    tables_with_deletes.append(table_name)
    
    # DELETE 后执行 VACUUM 回收磁盘空间
    if not dry_run and tables_with_deletes:
        logger.info(f"\n回收磁盘空间 (VACUUM {len(tables_with_deletes)} 个表)...")
        await vacuum_tables(db_manager, tables_with_deletes)
    
    return stats


async def get_database_size(db_manager: DatabaseManager) -> Dict[str, float]:
    """获取数据库大小信息."""
    try:
        async with db_manager.session() as session:
            # 获取数据库总大小
            db_size_sql = """
                SELECT 
                    pg_size_pretty(pg_database_size(current_database())) as db_size,
                    pg_database_size(current_database()) as db_size_bytes
            """
            result = await session.execute(text(db_size_sql))
            row = result.fetchone()
            
            if row:
                return {
                    "formatted": row[0],
                    "bytes": float(row[1]),
                }
    except Exception as e:
        logger.warning(f"无法获取数据库大小: {e}")
    
    return {"formatted": "N/A", "bytes": 0.0}


@app.command()
def cleanup(
    days: int = typer.Option(
        3,
        "--days",
        "-d",
        help="保留天数（默认3天）",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="模拟运行（不实际删除数据）",
    ),
    database_url: str = typer.Option(
        None,
        "--database-url",
        "-u",
        help="数据库连接URL（可选，优先级最高）",
    ),
    config: str = typer.Option(
        "config/accounts.json",
        "--config",
        "-c",
        help="配置文件路径（默认: config/accounts.json）",
    ),
    schedule: bool = typer.Option(
        False,
        "--schedule",
        "-s",
        help="启动定时任务模式（每天自动执行）",
    ),
    schedule_time: str = typer.Option(
        "02:00",
        "--schedule-time",
        "-t",
        help="定时任务执行时间（格式: HH:MM，默认: 02:00）",
    ),
    only_orders: bool = typer.Option(
        False,
        "--only-orders",
        help="仅清理订单相关表（默认关闭：清理全部已配置的业务流水与快照表）",
    ),
) -> None:
    """清理数据库中超过保留期的旧数据.
    
    数据库URL获取优先级（从高到低）:
    1. 命令行参数 --database-url
    2. 环境变量 DATABASE_URL
    3. 配置文件中的 global_settings.database_url（默认: config/accounts.json）
    4. 默认方式（可能抛出异常）
    
    Examples:
        # 立即执行清理（默认模式）
        uv run cleanup-old-data cleanup
        
        # 模拟运行，查看将要删除的数据
        uv run cleanup-old-data cleanup --dry-run
        
        # 保留7天数据
        uv run cleanup-old-data cleanup --days 7
        
        # 启动定时任务模式（每天凌晨2点自动执行）
        uv run cleanup-old-data cleanup --schedule
        
        # 启动定时任务，指定执行时间为凌晨3点
        uv run cleanup-old-data cleanup --schedule --schedule-time 03:00
        
        # 使用自定义配置文件
        uv run cleanup-old-data cleanup --config config/accounts_test.json
    """
    if schedule:
        # 启动定时任务模式
        _start_scheduler(days, dry_run, database_url, config, schedule_time, only_orders)
    else:
        # 立即执行清理
        asyncio.run(_cleanup_async(days, dry_run, database_url, config, only_orders))


def load_database_url_from_config(config_path: str = "config/accounts.json") -> str | None:
    """从配置文件读取数据库URL.
    
    Args:
        config_path: 配置文件路径，默认为 config/accounts.json
    
    Returns:
        数据库URL，如果读取失败则返回None
    """
    try:
        import json
        config_file = Path(config_path)
        if config_file.exists():
            with config_file.open("r", encoding="utf-8") as f:
                config = json.load(f)
            db_url = config.get("global_settings", {}).get("database_url")
            if db_url:
                logger.info(f"从配置文件 {config_path} 读取数据库URL")
                return db_url
            else:
                logger.warning(f"配置文件 {config_path} 中没有找到 database_url")
        else:
            logger.debug(f"配置文件 {config_path} 不存在")
    except Exception as e:
        logger.warning(f"无法从配置文件 {config_path} 读取数据库URL: {e}")
    return None


async def _cleanup_async(
    days: int,
    dry_run: bool,
    database_url: str | None,
    config_path: str | None,
    only_orders: bool = False,
) -> None:
    try:
        # 初始化数据库管理器
        # 优先级: 命令行参数 > 环境变量 > 配置文件 > 默认（抛出异常）
        if database_url:
            db_manager = DatabaseManager(database_url=database_url)
        else:
            # 尝试从环境变量读取
            db_url = os.getenv("DATABASE_URL")
            if db_url:
                logger.info("从环境变量 DATABASE_URL 读取数据库URL")
                db_manager = DatabaseManager(database_url=db_url)
            else:
                # 尝试从配置文件读取
                config_file = config_path or "config/accounts.json"
                db_url = load_database_url_from_config(config_file)
                if db_url:
                    db_manager = DatabaseManager(database_url=db_url)
                else:
                    # 最后尝试默认方式（可能会抛出异常）
                    logger.info("尝试使用默认方式初始化数据库管理器...")
                    db_manager = DatabaseManager()
        
        # 获取清理前的数据库大小
        logger.info("获取数据库大小信息...")
        size_before = await get_database_size(db_manager)
        logger.info(f"清理前数据库大小: {size_before['formatted']}")
        
        # 执行清理
        stats = await cleanup_all_tables(
            db_manager=db_manager,
            retention_days=days,
            dry_run=dry_run,
            only_orders=only_orders,
        )
        
        # 打印统计信息
        logger.info("\n" + "=" * 60)
        logger.info("清理统计:")
        logger.info(f"  总计行数（清理前）: {stats['total_before']:,}")
        logger.info(f"  删除行数: {stats['total_deleted']:,}")
        
        if not dry_run:
            # 获取清理后的数据库大小
            size_after = await get_database_size(db_manager)
            logger.info(f"清理后数据库大小: {size_after['formatted']}")
            
            size_reduced = size_before['bytes'] - size_after['bytes']
            if size_reduced > 0:
                logger.info(
                    f"释放空间: {size_reduced / (1024**2):.2f} MB "
                    f"({size_reduced / (1024**3):.2f} GB)"
                )
        
        logger.info("=" * 60)
        
        if dry_run:
            logger.info("\n⚠️  这是模拟运行，没有实际删除数据。")
            logger.info("   要实际执行清理，请运行: python scripts/cleanup_old_data.py cleanup")
        else:
            logger.info("\n✅ 数据清理完成！")
        
    except KeyboardInterrupt:
        logger.info("\n操作已取消")
        sys.exit(1)
    except Exception as e:
        logger.error(f"清理过程中出错: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if 'db_manager' in locals():
            await db_manager.close()


@app.command()
def list_tables() -> None:
    """列出所有将被清理的表."""
    logger.info("配置的数据清理表列表（静态 + 动态表模式）:")
    logger.info("=" * 80)

    for i, (table_name, time_column, description) in enumerate(STATIC_TABLE_CONFIGS, 1):
        logger.info(
            f"{i:2d}. {table_name:30s} | 时间字段: {time_column:20s} | {description}"
        )

    logger.info("-" * 80)
    for i, (pattern, time_column, description) in enumerate(TABLE_PATTERN_CONFIGS, 1):
        logger.info(
            f"P{i:02d}. {pattern:30s} | 时间字段: {time_column:20s} | {description}"
        )

    logger.info("=" * 80)
    logger.info(
        "提示：动态表会在 cleanup 运行时从数据库自动发现并清理（例如 xt_order_updates_*）。"
    )


@app.command()
def stop() -> None:
    """停止正在运行的定时任务."""
    _stop_scheduler()


def _scheduler_loop(
    days: int,
    dry_run: bool,
    database_url: Optional[str],
    config: Optional[str],
    schedule_time: str,
    only_orders: bool,
) -> None:
    """定时任务循环.
    
    Args:
        days: 保留天数
        dry_run: 是否为模拟运行
        database_url: 数据库URL
        config: 配置文件路径
        schedule_time: 执行时间（格式: HH:MM）
    """
    global _scheduler_running
    
    # 解析执行时间
    try:
        hour, minute = map(int, schedule_time.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("时间格式不正确")
    except (ValueError, AttributeError) as e:
        logger.error(f"时间格式错误: {schedule_time}，应为 HH:MM 格式，例如: 02:00")
        _scheduler_running = False
        return
    
    logger.info(f"定时任务已启动，将在每天 {schedule_time} 执行清理（保留 {days} 天数据）")
    
    # 设置信号处理，优雅退出
    def signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止定时任务...")
        _scheduler_running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    while _scheduler_running:
        try:
            now = datetime.now()
            # 计算今天的执行时间
            execute_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # 如果今天的时间已过，则设置为明天
            if execute_time <= now:
                execute_time += timedelta(days=1)
            
            # 计算等待时间（秒）
            wait_seconds = (execute_time - now).total_seconds()
            
            logger.info(f"下次执行时间: {execute_time.strftime('%Y-%m-%d %H:%M:%S')} (等待 {wait_seconds/3600:.2f} 小时)")
            
            # 等待到执行时间（每秒检查一次是否还在运行）
            while wait_seconds > 0 and _scheduler_running:
                sleep_time = min(60, wait_seconds)  # 最多等待60秒
                time.sleep(sleep_time)
                wait_seconds -= sleep_time
            
            # 如果任务还在运行，执行清理
            if _scheduler_running:
                logger.info(f"开始执行定时清理任务（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）")
                asyncio.run(_cleanup_async(days, dry_run, database_url, config, only_orders))
                logger.info("定时清理任务执行完成，等待下次执行...")
        
        except KeyboardInterrupt:
            logger.info("收到中断信号，停止定时任务")
            _scheduler_running = False
            break
        except Exception as e:
            logger.error(f"定时任务执行出错: {e}", exc_info=True)
            # 出错后等待1小时再重试，避免频繁出错
            if _scheduler_running:
                logger.info("等待1小时后重试...")
                for _ in range(3600):
                    if not _scheduler_running:
                        break
                    time.sleep(1)
    
    logger.info("定时任务已停止")


def _start_scheduler(
    days: int,
    dry_run: bool,
    database_url: Optional[str],
    config: Optional[str],
    schedule_time: str,
    only_orders: bool,
) -> None:
    """启动定时任务.
    
    Args:
        days: 保留天数
        dry_run: 是否为模拟运行
        database_url: 数据库URL
        config: 配置文件路径
        schedule_time: 执行时间（格式: HH:MM）
    """
    global _scheduler_thread, _scheduler_running
    
    with _scheduler_lock:
        if _scheduler_running:
            logger.warning("定时任务已在运行中，请先停止现有任务")
            return
        
        _scheduler_running = True
        _scheduler_thread = threading.Thread(
            target=_scheduler_loop,
            args=(days, dry_run, database_url, config, schedule_time, only_orders),
            daemon=False,
            name="CleanupScheduler"
        )
        _scheduler_thread.start()
        
        logger.info("定时任务已启动，按 Ctrl+C 停止")
        logger.info(f"执行时间: 每天 {schedule_time}")
        logger.info(f"保留天数: {days} 天")
        logger.info(f"模拟运行: {'是' if dry_run else '否'}")
        logger.info(f"仅清理订单: {'是' if only_orders else '否'}")
        
        # 等待线程结束（保持主线程运行）
        try:
            _scheduler_thread.join()
        except KeyboardInterrupt:
            logger.info("\n收到中断信号，正在停止...")
            _stop_scheduler()


def _stop_scheduler() -> None:
    """停止定时任务."""
    global _scheduler_thread, _scheduler_running
    
    with _scheduler_lock:
        if not _scheduler_running:
            logger.info("定时任务未运行")
            return
        
        logger.info("正在停止定时任务...")
        _scheduler_running = False
        
        if _scheduler_thread and _scheduler_thread.is_alive():
            _scheduler_thread.join(timeout=5)
            if _scheduler_thread.is_alive():
                logger.warning("定时任务线程未能在5秒内停止")
            else:
                logger.info("定时任务已停止")
        else:
            logger.info("定时任务已停止")


def main():
    """脚本入口点，供 uv run 使用."""
    app()


if __name__ == "__main__":
    main()

