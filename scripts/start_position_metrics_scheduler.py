#!/usr/bin/env python3
"""持仓指标定时计算服务启动脚本.

每5分钟计算一次持仓和交易指标，并存储到数据库供 Grafana 可视化。
"""

import asyncio
import os
import signal
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tri_arb.config.logging import get_logger
from tri_arb.services.position_metrics_scheduler import PositionMetricsScheduler
from tri_arb.storage.database import DatabaseManager
from tri_arb.utils.metrics import MetricsServer

logger = get_logger(__name__)


class SchedulerApp:
    """定时任务应用主程序."""
    
    def __init__(self):
        """初始化应用."""
        self.scheduler: PositionMetricsScheduler | None = None
        self.db_manager: DatabaseManager | None = None
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
    
    def run(self, config_path: str = "config/accounts.json", interval_minutes: int = 5):
        """运行应用.
        
        Args:
            config_path: 账号配置文件路径
            interval_minutes: 计算间隔（分钟）
        """
        try:
            asyncio.run(self._main(config_path=config_path, interval_minutes=interval_minutes))
        except KeyboardInterrupt:
            logger.info("收到键盘中断信号")
        except Exception as e:
            logger.error("应用运行出错", error=str(e), exc_info=True)
            sys.exit(1)
    
    async def _main(self, config_path: str = "config/accounts.json", interval_minutes: int = 5):
        """主函数.
        
        Args:
            config_path: 账号配置文件路径
            interval_minutes: 计算间隔（分钟）
        """
        # 从环境变量或配置文件获取数据库URL
        database_url = os.getenv("DATABASE_URL")
        
        # 初始化数据库管理器
        if database_url:
            self.db_manager = DatabaseManager(database_url=database_url)
        else:
            # 尝试从配置文件读取
            try:
                import json
                config_file = Path(config_path)
                if config_file.exists():
                    with config_file.open("r", encoding="utf-8") as f:
                        config = json.load(f)
                    db_url = config.get("global_settings", {}).get("database_url")
                    if db_url:
                        self.db_manager = DatabaseManager(database_url=db_url)
                    else:
                        self.db_manager = DatabaseManager()
                else:
                    self.db_manager = DatabaseManager()
            except Exception as e:
                logger.warning(f"无法从配置文件读取数据库URL: {e}，使用默认配置")
                self.db_manager = DatabaseManager()
        
        # 创建数据库表（如果不存在）
        try:
            await self.db_manager.create_tables()
            logger.info("数据库表已创建/验证")
        except Exception as e:
            logger.error("创建数据库表失败", error=str(e), exc_info=True)
            sys.exit(1)
        
        # 启动 Prometheus metrics server
        # 注意：直接启动，不依赖 settings.enable_metrics（因为这是独立服务）
        from prometheus_client import start_http_server
        try:
            start_http_server(9602)
            logger.info("Prometheus metrics server 已启动", port=9602)
        except Exception as e:
            logger.warning(f"启动 Prometheus metrics server 失败: {e}，metrics 将不可用")
        
        # 初始化定时任务服务
        self.scheduler = PositionMetricsScheduler(
            db_manager=self.db_manager,
            config_path=config_path,
            interval_minutes=interval_minutes,
        )
        
        # 启动定时任务服务
        try:
            await self.scheduler.start()
            logger.info("持仓指标定时计算服务已启动", interval_minutes=interval_minutes)
            
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
    import argparse
    
    parser = argparse.ArgumentParser(
        description="持仓指标定时计算服务 - 每5分钟计算一次持仓和交易指标"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/accounts.json",
        help="账号配置文件路径（默认: config/accounts.json）",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="计算间隔（分钟），默认5分钟",
    )
    
    args = parser.parse_args()
    
    app = SchedulerApp()
    app.run(config_path=args.config, interval_minutes=args.interval)


if __name__ == "__main__":
    main()

