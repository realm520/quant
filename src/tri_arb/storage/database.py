"""Database connection and session management."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from tri_arb.config.logging import get_logger
from tri_arb.storage.models import Base as BinanceBase
from tri_arb.storage.okx_models import Base as OKXBase
from tri_arb.storage.gate_models import Base as GateBase
from tri_arb.storage.xt_websocket_models import Base as XTWebSocketBase
from tri_arb.storage.rest_models import Base as RestBase
from tri_arb.storage.xt_rest_models import Base as XTRestBase
from tri_arb.storage.exchange_rest_models import (
    Base as ExchangeRestBase,
    # 导入所有模型类以确保它们注册到 metadata
    BinanceBalanceRest,
    BinancePositionRest,
    BinanceOrderRest,
    XTBalanceRest,
    XTPositionRest,
    XTOrderRest,
    OKXBalanceRest,
    OKXPositionRest,
    OKXOrderRest,
    GateBalanceRest,
    GatePositionRest,
    GateOrderRest,
)
from tri_arb.storage.position_metrics_models import Base as PositionMetricsBase

logger = get_logger(__name__)


class DatabaseManager:
    """PostgreSQL数据库管理器.
    
    管理数据库连接、会话和表创建。
    """
    
    def __init__(self, database_url: str | None = None):
        """初始化数据库管理器.
        
        Args:
            database_url: PostgreSQL连接URL，格式：
                同步：postgresql://user:password@host:port/dbname
                异步：postgresql+asyncpg://user:password@host:port/dbname
                无密码：postgresql+asyncpg://user@host:port/dbname
                如果为None，从环境变量DATABASE_URL读取
                
        Raises:
            ValueError: 如果未提供database_url且环境变量DATABASE_URL也未设置
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        
        if not self.database_url:
            raise ValueError(
                "数据库连接URL未设置。请通过以下方式之一设置：\n"
                "1. 设置环境变量 DATABASE_URL:\n"
                "   export DATABASE_URL='postgresql+asyncpg://user:password@host:port/dbname'\n"
                "2. 或在代码中传入 database_url 参数\n"
                "\n"
                "示例:\n"
                "   postgresql+asyncpg://postgres:password@localhost:5432/trading\n"
                "   postgresql+asyncpg://postgres@localhost:5432/trading  # 无密码\n"
        )
        
        # 异步引擎
        self.async_engine = create_async_engine(
            self.database_url,
            echo=False,  # 设置为True可以看到SQL语句
            pool_size=10,
            max_overflow=20,
        )
        
        # 异步会话工厂
        self.async_session_maker = async_sessionmaker(
            self.async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        logger.info(
            "Database manager initialized",
            url_host=self.database_url.split("@")[-1] if "@" in self.database_url else "localhost"
        )
    
    async def create_tables(self):
        """创建数据库表（Binance、OKX、Gate.io、XT WebSocket、REST API、XT REST API、按交易所区分的REST API）。"""
        from sqlalchemy import inspect, text
        from sqlalchemy.exc import ProgrammingError, DBAPIError
        
        # 使用 connect() 而不是 begin()，每个操作单独提交，避免事务中止问题
        async with self.async_engine.connect() as conn:
            def _create_safe(sync_conn, metadata, name: str):
                """创建表，忽略已存在的表/索引错误."""
                from sqlalchemy import text
                
                # 获取 metadata 中定义的所有表
                metadata_tables = set(metadata.tables.keys())
                logger.info(f"{name}: Found {len(metadata_tables)} tables in metadata: {sorted(metadata_tables)}")
                
                # 先检查哪些表已经存在
                existing_tables = set()
                try:
                    inspector = inspect(sync_conn)
                    existing_tables = set(inspector.get_table_names())
                    logger.info(f"{name}: Found {len(existing_tables)} existing tables in database")
                    # 特别检查 binance_balance_rest
                    if "binance_balance_rest" in existing_tables:
                        logger.info(f"{name}: ✓ binance_balance_rest already exists in database")
                    else:
                        logger.info(f"{name}: binance_balance_rest does NOT exist in database (will create)")
                except Exception as inspect_err:
                    logger.warning(f"{name}: Failed to inspect existing tables: {inspect_err}")
                
                # 检查哪些表需要创建
                missing_tables = metadata_tables - existing_tables
                
                if not missing_tables:
                    logger.info(f"All {name} tables already exist")
                    return
                
                logger.info(f"Creating {len(missing_tables)} missing {name} tables: {', '.join(sorted(missing_tables))}")
                
                # 对每个缺失的表，尝试创建（忽略索引错误）
                created_tables = []
                failed_tables = []
                for table_name in sorted(missing_tables):
                    table = metadata.tables[table_name]
                    try:
                        # 先检查表是否真的存在（可能索引存在但表不存在）
                        inspector = inspect(sync_conn)
                        table_exists = inspector.has_table(table_name)
                        
                        table_created = False
                        if not table_exists:
                            # 表不存在，使用 CreateTable 创建表（包含所有约束和 UniqueConstraint）
                            # CreateTable 会自动包含 UniqueConstraint，不需要单独创建
                            try:
                                from sqlalchemy.schema import CreateTable
                                from sqlalchemy import text
                                
                                # 生成创建表的 SQL
                                try:
                                    create_table_sql = str(CreateTable(table).compile(dialect=sync_conn.dialect))
                                    logger.debug(f"Generated SQL for {table_name} (length: {len(create_table_sql)})")
                                except Exception as sql_gen_err:
                                    error_msg = f"Failed to generate SQL for table {table_name}: {sql_gen_err}"
                                    logger.error(error_msg, exc_info=True)
                                    failed_tables.append((table_name, error_msg))
                                    continue
                                
                                # 执行创建表的 SQL
                                try:
                                    # 执行 DDL 语句
                                    # 注意：PostgreSQL 的 DDL 语句在事务中执行，需要显式提交
                                    logger.info(f"Executing CREATE TABLE for {table_name}...")
                                    
                                    # 如果表创建失败是因为约束已存在，先删除约束
                                    try:
                                        result = sync_conn.execute(text(create_table_sql))
                                        sync_conn.commit()
                                        logger.info(f"✓ CREATE TABLE executed and committed for {table_name}")
                                    except Exception as create_err:
                                        error_str = str(create_err).lower()
                                        # 检查是否是约束已存在的错误
                                        if "already exists" in error_str and "constraint" in error_str:
                                            logger.warning(f"Constraint already exists for {table_name}, attempting to drop and recreate...")
                                            # 提取约束名
                                            import re
                                            constraint_match = re.search(r'"([^"]+)"', error_str)
                                            if constraint_match:
                                                constraint_name = constraint_match.group(1)
                                                logger.info(f"Dropping existing constraint: {constraint_name}")
                                                # 尝试删除约束（可能约束在另一个表上）
                                                try:
                                                    # 查找约束所属的表
                                                    inspector = inspect(sync_conn)
                                                    cur = sync_conn.connection.cursor()
                                                    cur.execute("""
                                                        SELECT conrelid::regclass::text
                                                        FROM pg_constraint
                                                        WHERE conname = %s
                                                    """, (constraint_name,))
                                                    result = cur.fetchone()
                                                    if result:
                                                        constraint_table = result[0]
                                                        cur.execute(f'ALTER TABLE "{constraint_table}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')
                                                        cur.close()
                                                        sync_conn.commit()
                                                        logger.info(f"✓ Dropped constraint {constraint_name} from {constraint_table}")
                                                        
                                                        # 重新尝试创建表
                                                        result = sync_conn.execute(text(create_table_sql))
                                                        sync_conn.commit()
                                                        logger.info(f"✓ CREATE TABLE executed and committed for {table_name} (after dropping constraint)")
                                                    else:
                                                        raise create_err
                                                except Exception as drop_err:
                                                    logger.error(f"Failed to drop constraint: {drop_err}")
                                                    raise create_err
                                            else:
                                                raise create_err
                                        else:
                                            raise create_err
                                    
                                    # 立即验证表是否创建成功（在同一连接中）
                                    inspector = inspect(sync_conn)
                                    table_exists_after = inspector.has_table(table_name)
                                    logger.info(f"Verification: table {table_name} exists = {table_exists_after}")
                                    
                                    if not table_exists_after:
                                        error_msg = f"Table {table_name} was not created after CREATE TABLE statement (commit succeeded but table missing)"
                                        logger.error(error_msg)
                                        raise RuntimeError(error_msg)
                                except Exception as exec_err:
                                    sync_conn.rollback()
                                    error_msg = f"Failed to execute CREATE TABLE for {table_name}: {exec_err}"
                                    logger.error(error_msg, exc_info=True)
                                    failed_tables.append((table_name, error_msg))
                                    continue
                                
                                # 验证表是否真的创建成功
                                inspector = inspect(sync_conn)
                                if inspector.has_table(table_name):
                                    logger.info(f"✓ Created table: {table_name}")
                                    table_created = True
                                    created_tables.append(table_name)
                                else:
                                    error_msg = f"Table {table_name} creation appeared to succeed but table does not exist"
                                    logger.error(error_msg)
                                    failed_tables.append((table_name, error_msg))
                                    continue  # 表创建失败，跳过索引创建
                            except (ProgrammingError, DBAPIError) as create_err:
                                sync_conn.rollback()
                                create_err_str = str(create_err).lower()
                                if "already exists" in create_err_str or "duplicate" in create_err_str:
                                    # 表已存在，验证一下
                                    inspector = inspect(sync_conn)
                                    if inspector.has_table(table_name):
                                        logger.debug(f"Table {table_name} already exists (skipping)")
                                        table_created = True
                                        created_tables.append(table_name)
                                    else:
                                        error_msg = f"Table {table_name} marked as existing but not found: {create_err}"
                                        logger.error(error_msg)
                                        failed_tables.append((table_name, error_msg))
                                        continue
                                else:
                                    logger.error(f"Failed to create table {table_name}: {create_err}")
                                    failed_tables.append((table_name, str(create_err)))
                                    continue  # 表创建失败，跳过索引创建
                        else:
                            # 表已存在，再次验证
                            inspector = inspect(sync_conn)
                            if inspector.has_table(table_name):
                                logger.debug(f"Table {table_name} already exists (skipping table creation)")
                                table_created = True
                                created_tables.append(table_name)
                            else:
                                error_msg = f"Table {table_name} marked as existing but not found"
                                logger.error(error_msg)
                                failed_tables.append((table_name, error_msg))
                                continue  # 表不存在，跳过索引创建
                        
                        # 只有在表创建成功或已存在时，才尝试创建索引
                        # UniqueConstraint 已经在 CreateTable 中创建，不需要单独处理
                        if table_created:
                            for index in table.indexes:
                                try:
                                    index.create(sync_conn, checkfirst=True)
                                    sync_conn.commit()
                                except (ProgrammingError, DBAPIError) as idx_err:
                                    sync_conn.rollback()
                                    idx_err_str = str(idx_err).lower()
                                    if "already exists" in idx_err_str or "duplicate" in idx_err_str:
                                        logger.debug(f"Index {index.name} already exists (skipping)")
                                    else:
                                        # 索引创建失败不影响表的使用，只记录警告
                                        logger.warning(f"Failed to create index {index.name}: {idx_err}")
                    except (ProgrammingError, DBAPIError) as pe:
                        sync_conn.rollback()
                        pe_str = str(pe).lower()
                        if "already exists" in pe_str or "duplicate" in pe_str:
                            logger.debug(f"Table {table_name} or its indexes already exist (skipping)")
                            created_tables.append(table_name)  # 表已存在，也算成功
                        else:
                            logger.warning(f"Failed to create table {table_name}: {pe}")
                            failed_tables.append((table_name, str(pe)))
                    except Exception as e:
                        sync_conn.rollback()
                        error_str = str(e).lower()
                        if "already exists" in error_str or "duplicate" in error_str:
                            logger.debug(f"Table {table_name} already exists (skipping)")
                            created_tables.append(table_name)  # 表已存在，也算成功
                        else:
                            logger.error(f"Unexpected error creating table {table_name}: {e}", exc_info=True)
                            failed_tables.append((table_name, str(e)))
                
                # 验证所有表是否真的存在（防止创建失败但被误认为成功）
                inspector = inspect(sync_conn)
                existing_tables_after = set(inspector.get_table_names())
                verified_tables = []
                missing_after_creation = []
                
                logger.info(f"Verifying table creation: metadata has {len(metadata_tables)} tables, database has {len([t for t in existing_tables_after if t.startswith('xt_')])} xt_* tables")
                
                for table_name in metadata_tables:
                    if table_name in existing_tables_after:
                        verified_tables.append(table_name)
                        logger.debug(f"✓ Verified table exists: {table_name}")
                    else:
                        missing_after_creation.append(table_name)
                        logger.warning(f"✗ Table missing after creation attempt: {table_name}")
                        # 如果表应该在 created_tables 中但实际不存在，从 created_tables 中移除
                        if table_name in created_tables:
                            logger.warning(f"  Table {table_name} was in created_tables but does not exist in database")
                            created_tables.remove(table_name)
                        # 添加到失败列表（如果还没有）
                        if table_name not in [t[0] for t in failed_tables]:
                            error_msg = "Table creation appeared to succeed but table does not exist in database after creation"
                            logger.error(f"  Adding to failed_tables: {table_name} - {error_msg}")
                            failed_tables.append((table_name, error_msg))
                
                # 总结创建结果
                if verified_tables:
                    logger.info(f"✓ Successfully created/verified {len(verified_tables)} {name} tables: {', '.join(sorted(verified_tables))}")
                if failed_tables:
                    error_msg = f"⚠ Failed to create {len(failed_tables)} {name} tables: {', '.join([t[0] for t in failed_tables])}"
                    logger.error(error_msg)
                    detailed_errors = []
                    for table_name, error in failed_tables:
                        error_detail = f"{table_name}: {error}"
                        logger.error(f"  - {error_detail}")
                        detailed_errors.append(error_detail)
                    # 如果有表创建失败，抛出异常，包含详细错误信息
                    full_error_msg = f"Failed to create {len(failed_tables)} {name} table(s):\n" + "\n".join(f"  - {e}" for e in detailed_errors)
                    raise RuntimeError(full_error_msg)
                
                # 如果有表在创建后仍然缺失，抛出异常
                if missing_after_creation:
                    error_msg = f"⚠ Tables missing after creation attempt: {', '.join(missing_after_creation)}"
                    logger.error(error_msg)
                    raise RuntimeError(f"Tables missing after creation: {', '.join(missing_after_creation)}")
            
            try:
                logger.info("Creating Binance tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, BinanceBase.metadata, "Binance"))
                logger.info("✓ Binance tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some Binance tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create Binance tables: {e}", exc_info=True)
                    raise
            
            try:
                logger.info("Creating OKX tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, OKXBase.metadata, "OKX"))
                logger.info("✓ OKX tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some OKX tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create OKX tables: {e}", exc_info=True)
                    raise
            
            try:
                logger.info("Creating Gate.io tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, GateBase.metadata, "Gate.io"))
                logger.info("✓ Gate.io tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some Gate.io tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create Gate.io tables: {e}", exc_info=True)
                    raise
            
            try:
                logger.info("Creating XT WebSocket tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, XTWebSocketBase.metadata, "XT WebSocket"))
                logger.info("✓ XT WebSocket tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some XT WebSocket tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create XT WebSocket tables: {e}", exc_info=True)
                    raise
            
            try:
                logger.info("Creating REST API tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, RestBase.metadata, "REST API"))
                logger.info("✓ REST API tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some REST API tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create REST API tables: {e}", exc_info=True)
                    raise
            
            try:
                logger.info("Creating XT REST API tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, XTRestBase.metadata, "XT REST API"))
                logger.info("✓ XT REST API tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some XT REST API tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create XT REST API tables: {e}", exc_info=True)
                    raise
            
            try:
                # 先检查 metadata 中有哪些表
                metadata_tables = list(ExchangeRestBase.metadata.tables.keys())
                logger.info(f"Creating Exchange-specific REST API tables (binance_balance_rest, xt_balance_rest, etc.)... Found {len(metadata_tables)} tables in metadata: {metadata_tables}")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, ExchangeRestBase.metadata, "Exchange-specific REST API"))
                logger.info("✓ Exchange-specific REST API tables created/verified")
            except Exception as e:
                # 检查是否是索引/表已存在的错误（这些可以忽略）
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some Exchange-specific REST API tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create Exchange-specific REST API tables: {e}", exc_info=True)
                    raise
            
            try:
                logger.info("Creating Position Metrics tables...")
                await conn.run_sync(lambda sync_conn: _create_safe(sync_conn, PositionMetricsBase.metadata, "Position Metrics"))
                logger.info("✓ Position Metrics tables created/verified")
            except Exception as e:
                error_str = str(e).lower()
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.warning(f"Some Position Metrics tables/indexes already exist (this is OK): {e}")
                else:
                    logger.error(f"Failed to create Position Metrics tables: {e}", exc_info=True)
                    raise
        
        logger.info("✅ All database tables created/verified (Binance + OKX + Gate.io + XT WebSocket + REST API + XT REST API + Exchange-specific REST API + Position Metrics)")
    
    async def drop_tables(self):
        """删除数据库表（谨慎使用）。"""
        async with self.async_engine.begin() as conn:
            await conn.run_sync(BinanceBase.metadata.drop_all)
            await conn.run_sync(OKXBase.metadata.drop_all)
            await conn.run_sync(GateBase.metadata.drop_all)
            await conn.run_sync(XTWebSocketBase.metadata.drop_all)
            await conn.run_sync(RestBase.metadata.drop_all)
            await conn.run_sync(XTRestBase.metadata.drop_all)
            await conn.run_sync(ExchangeRestBase.metadata.drop_all)
            await conn.run_sync(PositionMetricsBase.metadata.drop_all)
        logger.warning("Database tables dropped (Binance + OKX + Gate.io + XT WebSocket + REST API + XT REST API + Exchange-specific REST API + Position Metrics)")
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """获取异步数据库会话.
        
        Yields:
            AsyncSession: 异步数据库会话
            
        Example:
            async with db_manager.session() as session:
                session.add(record)
                await session.commit()
        """
        session = self.async_session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def close(self):
        """关闭数据库连接."""
        await self.async_engine.dispose()
        logger.info("Database connections closed")

