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
from tri_arb.storage.exchange_rest_models import Base as ExchangeRestBase

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
        async with self.async_engine.begin() as conn:
            await conn.run_sync(lambda sync_conn: BinanceBase.metadata.create_all(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: OKXBase.metadata.create_all(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: GateBase.metadata.create_all(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: XTWebSocketBase.metadata.create_all(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: RestBase.metadata.create_all(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: XTRestBase.metadata.create_all(sync_conn, checkfirst=True))
            await conn.run_sync(lambda sync_conn: ExchangeRestBase.metadata.create_all(sync_conn, checkfirst=True))
        logger.info("Database tables created (Binance + OKX + Gate.io + XT WebSocket + REST API + XT REST API + Exchange-specific REST API)")
    
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

