"""XT账户定时任务主程序.

启动XT交易所账户定时任务服务，定期获取账户余额和仓位数据。
"""

import asyncio
import os
import signal
import sys
from typing import Optional

from tri_arb.config.logging import get_logger
from tri_arb.services.xt_account_scheduler import XTAccountScheduler
from tri_arb.storage.database import DatabaseManager

logger = get_logger(__name__)


class SchedulerApp:
    """定时任务应用主程序."""
    
    def __init__(self):
        """初始化应用."""
        self.scheduler: Optional[XTAccountScheduler] = None
        self.db_manager: Optional[DatabaseManager] = None
        self._shutdown_requested = False
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum: int, frame):
        """处理退出信号."""
        logger.info("收到退出信号", signal=signum)
        self._shutdown_requested = True
        asyncio.create_task(self._shutdown())
    
    async def _shutdown(self):
        """关闭应用."""
        logger.info("正在关闭应用...")
        if self.scheduler:
            await self.scheduler.stop()
        if self.db_manager:
            await self.db_manager.close()
        logger.info("应用已关闭")
    
    def run(self):
        """运行应用."""
        try:
            asyncio.run(self._main())
        except KeyboardInterrupt:
            logger.info("收到键盘中断信号")
        except Exception as e:
            logger.error("应用运行出错", error=str(e), exc_info=True)
            sys.exit(1)
    
    async def _main(self):
        """主函数."""
        # 从环境变量获取配置（XT API现货和合约共用同一套密钥）
        api_key = os.getenv("XT_API_KEY", "")
        api_secret = os.getenv("XT_API_SECRET", "")
        interval_minutes = 10  # 默认10分钟
        
        # 验证配置
        if not api_key or not api_secret:
            logger.error("缺少XT API密钥配置 (XT_API_KEY, XT_API_SECRET)")
            logger.error("XT交易所的现货和合约使用同一套API密钥")
            sys.exit(1)
        
        # 初始化数据库管理器
        self.db_manager = DatabaseManager()
        
        # 创建数据库表（如果不存在）
        try:
            await self.db_manager.create_tables()
            logger.info("数据库表已创建/验证")
        except Exception as e:
            logger.error("创建数据库表失败", error=str(e), exc_info=True)
            sys.exit(1)
        
        # 初始化定时任务服务
        self.scheduler = XTAccountScheduler(
            api_key=api_key,
            api_secret=api_secret,
            db_manager=self.db_manager,
            interval_minutes=interval_minutes,
        )
        
        # 启动定时任务服务
        try:
            await self.scheduler.start()
            logger.info("定时任务服务已启动", interval_minutes=interval_minutes)
            
            # 保持运行直到收到退出信号
            while not self._shutdown_requested:
                await asyncio.sleep(1)
        
        except Exception as e:
            logger.error("定时任务服务运行出错", error=str(e), exc_info=True)
            raise
        finally:
            # 清理资源
            await self._shutdown()


def main():
    """主入口函数."""
    app = SchedulerApp()
    app.run()


if __name__ == "__main__":
    main()

