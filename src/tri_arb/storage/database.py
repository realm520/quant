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
                try:
                    # 先尝试标准的 create_all（这会处理表和索引）
                    metadata.create_all(sync_conn, checkfirst=True)
                    sync_conn.commit()
                except (ProgrammingError, DBAPIError) as e:
                    error_str = str(e).lower()
                    # 回滚当前事务
                    try:
                        sync_conn.rollback()
                    except Exception:
                        pass
                    
                    # 如果是索引已存在的错误，尝试逐个创建表（跳过索引）
                    if "already exists" in error_str or "duplicate" in error_str or "aborted" in error_str:
                        logger.warning(f"Some {name} indexes already exist, creating tables individually...")
                        
                        # 获取所有表名
                        try:
                            inspector = inspect(sync_conn)
                            existing_tables = set(inspector.get_table_names())
                        except Exception as inspect_err:
                            # 如果检查失败，假设所有表都不存在
                            logger.warning(f"Failed to inspect existing tables, will try to create all: {inspect_err}")
                            existing_tables = set()
                        
                        # 获取 metadata 中定义的所有表
                        metadata_tables = set(metadata.tables.keys())
                        
                        # 检查哪些表需要创建
                        missing_tables = metadata_tables - existing_tables
                        
                        if missing_tables:
                            logger.info(f"Creating {len(missing_tables)} missing {name} tables: {', '.join(sorted(missing_tables))}")
                            # 对每个缺失的表，尝试创建（忽略索引错误）
                            for table_name in missing_tables:
                                table = metadata.tables[table_name]
                                try:
                                    # 创建表结构（不创建索引）
                                    table.create(sync_conn, checkfirst=True)
                                    sync_conn.commit()
                                    logger.debug(f"Created table: {table_name}")
                                    
                                    # 尝试创建索引（忽略已存在的错误）
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
                                                logger.warning(f"Failed to create index {index.name}: {idx_err}")
                                except (ProgrammingError, DBAPIError) as pe:
                                    sync_conn.rollback()
                                    pe_str = str(pe).lower()
                                    if "already exists" in pe_str or "duplicate" in pe_str:
                                        logger.debug(f"Table {table_name} or its indexes already exist (skipping)")
                                    else:
                                        logger.warning(f"Failed to create table {table_name}: {pe}")
                        else:
                            logger.debug(f"All {name} tables already exist")
                    else:
                        # 其他类型的错误，重新抛出
                        raise
                except Exception as e:
                    error_str = str(e).lower()
                    # 回滚事务
                    try:
                        sync_conn.rollback()
                    except Exception:
                        pass
                    # 如果是表/索引已存在的错误，记录为警告而不是错误
                    if "already exists" in error_str or "duplicate" in error_str:
                        logger.warning(f"Some {name} tables/indexes already exist (this is OK): {e}")
                    else:
                        logger.error(f"Failed to create {name} tables: {e}", exc_info=True)
                        raise
            
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
                logger.info("Creating Exchange-specific REST API tables (binance_balance_rest, xt_balance_rest, etc.)...")
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
        
        logger.info("✅ All database tables created/verified (Binance + OKX + Gate.io + XT WebSocket + REST API + XT REST API + Exchange-specific REST API)")
    
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
        logger.warning("Database tables dropped (Binance + OKX + Gate.io + XT WebSocket + REST API + XT REST API + Exchange-specific REST API)")
    
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

