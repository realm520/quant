"""XT 多账号订阅服务.

支持同时订阅多个账号的 WebSocket 数据流，使用统一表 + account_id 字段区分账号。
"""

import asyncio
import logging
from typing import Dict, Optional, Set

from tri_arb.config.account_manager import AccountConfig, AccountManager
from tri_arb.services.xt_user_stream import XTUserStreamService
from tri_arb.storage.database import DatabaseManager

# 不再需要按账号分表，统一使用 account_id 字段

logger = logging.getLogger(__name__)


class XTMultiAccountStreamService:
    """XT 多账号订阅服务."""

    def __init__(
        self,
        account_manager: AccountManager,
        db_manager: DatabaseManager,
        auto_reconnect: bool = True,
        display_format: str = "table",
        enable_data_sync: bool = True,
    ):
        """初始化多账号订阅服务.

        Args:
            account_manager: 账号管理器
            db_manager: 数据库管理器
            auto_reconnect: 是否自动重连
            display_format: 显示格式 (table, json)
            enable_data_sync: 是否启用数据同步
        """
        self.account_manager = account_manager
        self.db_manager = db_manager
        self.auto_reconnect = auto_reconnect
        self.display_format = display_format
        self.enable_data_sync = enable_data_sync

        # 账号服务实例字典
        self.account_services: Dict[str, XTUserStreamService] = {}

        # 运行状态
        self.is_running = False
        self.tasks: Dict[str, asyncio.Task] = {}

    async def _ensure_account_tables(self, account_id: str):
        """确保账号的数据库表已创建（统一表，不再需要按账号分表）."""
        # 统一表已通过 create_tables() 创建，这里不再需要特殊处理
        pass

    def _create_account_service(
        self,
        account_config: AccountConfig,
    ) -> XTUserStreamService:
        """创建账号特定的订阅服务.

        使用统一表 + account_id 字段区分账号。
        """
        # 解析频道
        enabled_channels: Optional[Set[str]] = None
        if account_config.channels:
            enabled_channels = set(account_config.channels)

        service = XTUserStreamService(
            api_key=account_config.api_key,
            api_secret=account_config.api_secret,
            db_manager=self.db_manager,
            auto_reconnect=self.auto_reconnect,
            display_format=self.display_format,
            enabled_channels=enabled_channels,
            enable_data_sync=self.enable_data_sync,
        )

        # 将账号ID附加到服务实例（不再需要 account_models）
        service.account_id = account_config.account_id
        service.account_name = account_config.name

        return service

    async def start(self, account_ids: Optional[list[str]] = None):
        """启动多账号订阅服务.

        Args:
            account_ids: 要启动的账号ID列表，如果为None则启动所有启用的账号
        """
        if self.is_running:
            logger.warning("多账号订阅服务已在运行")
            return

        self.is_running = True

        # 获取要启动的账号列表
        if account_ids:
            accounts = [
                self.account_manager.get_account(acc_id)
                for acc_id in account_ids
                if self.account_manager.get_account(acc_id)
            ]
        else:
            accounts = self.account_manager.get_enabled_accounts()

        if not accounts:
            logger.error("没有可用的账号")
            self.is_running = False
            return

        logger.info(f"准备启动 {len(accounts)} 个账号的订阅服务")

        # 为每个账号创建表并启动服务
        for account_config in accounts:
            try:
                account_id = account_config.account_id
                logger.info(f"启动账号: {account_id} ({account_config.name})")

                # 确保数据库表已创建（统一表）
                await self._ensure_account_tables(account_id)

                # 创建账号服务
                service = self._create_account_service(account_config)
                self.account_services[account_id] = service

                # 启动服务（在后台任务中运行）
                task = asyncio.create_task(
                    self._run_account_service(account_id, service)
                )
                self.tasks[account_id] = task

                # 稍微延迟，避免同时连接过多
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(
                    f"启动账号 {account_config.account_id} 失败: {e}", exc_info=True
                )

        logger.info(f"已启动 {len(self.account_services)} 个账号的订阅服务")

        # 等待所有任务完成（或直到停止）
        try:
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        except KeyboardInterrupt:
            logger.info("收到停止信号")
        finally:
            await self.stop()

    async def _run_account_service(
        self,
        account_id: str,
        service: XTUserStreamService,
    ):
        """运行单个账号的订阅服务."""
        try:
            logger.info(f"账号 {account_id} 的订阅服务开始运行")
            await service.start()
        except Exception as e:
            logger.error(f"账号 {account_id} 的订阅服务异常: {e}", exc_info=True)
        finally:
            logger.info(f"账号 {account_id} 的订阅服务已停止")

    async def stop(self):
        """停止所有账号的订阅服务."""
        if not self.is_running:
            return

        logger.info("正在停止多账号订阅服务...")
        self.is_running = False

        # 停止所有账号服务
        stop_tasks = []
        for account_id, service in self.account_services.items():
            logger.info(f"停止账号 {account_id} 的订阅服务")
            stop_tasks.append(service.stop())

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        # 取消所有任务
        for account_id, task in self.tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self.account_services.clear()
        self.tasks.clear()

        logger.info("多账号订阅服务已停止")

    def get_account_status(self) -> Dict[str, dict]:
        """获取所有账号的运行状态."""
        status = {}
        for account_id, service in self.account_services.items():
            status[account_id] = {
                "is_connected": service.is_connected,
                "is_running": service.is_running,
                "connection_id": service.connection_id,
            }
        return status
