#!/usr/bin/env python3
"""单独订阅 XT 成交记录，只打印原始数据，不插入数据库。

用法:
    python scripts/subscribe_trades_only.py
    python scripts/subscribe_trades_only.py --account-id account_008
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tri_arb.services.xt_user_stream import XTUserStreamService, DecimalEncoder
from tri_arb.storage.database import DatabaseManager


class TradeSubscriberService(XTUserStreamService):
    """只订阅成交数据，不保存到数据库的服务。"""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        account_id: Optional[str] = None,
    ):
        # 创建一个假的 db_manager（不会真正使用）
        fake_db_url = "postgresql+asyncpg://fake:fake@localhost/fake"
        db_manager = DatabaseManager(fake_db_url)
        
        # 只启用 trade 频道，不启用数据同步
        super().__init__(
            api_key=api_key,
            api_secret=api_secret,
            db_manager=db_manager,
            auto_reconnect=True,
            display_format="json",
            enabled_channels={"trade"},  # 只订阅成交
            enable_data_sync=False,  # 不启用数据同步
        )
        
        self.account_id = account_id
        self.trade_count = 0

    async def _save_trade_update(self, data: Dict[str, Any]) -> None:
        """重写保存方法，只打印原始数据，不保存到数据库。"""
        # 支持多种格式
        trades = []
        if "trades" in data and isinstance(data.get("trades"), list):
            trades = data.get("trades", [])
        elif isinstance(data, list):
            trades = data
        elif "orderId" in data or "order_id" in data or "trade_id" in data or "tradeId" in data:
            trades = [data]
        
        if not trades:
            return
        
        for trade in trades:
            self.trade_count += 1
            
            # 打印分隔线
            print("\n" + "=" * 100)
            print(f"成交记录 #{self.trade_count}")
            print("=" * 100)
            
            # 打印完整原始数据（JSON 格式）
            print("\n📦 原始数据 (Raw Data):")
            print(json.dumps(trade, indent=2, ensure_ascii=False, cls=DecimalEncoder))
            
            # 提取关键字段并打印
            print("\n📋 关键字段:")
            order_id = trade.get("orderId") or trade.get("order_id", "")
            symbol = trade.get("symbol", "")
            side = trade.get("orderSide") or trade.get("side", "")
            price = trade.get("price", "")
            quantity = trade.get("quantity", "")
            timestamp = trade.get("timestamp")
            is_maker = trade.get("isMaker") or trade.get("is_maker", False)
            position_side = trade.get("positionSide") or trade.get("position_side", "")
            
            print(f"  order_id      = {order_id}")
            print(f"  symbol        = {symbol}")
            print(f"  side          = {side}")
            print(f"  position_side = {position_side}")
            print(f"  price         = {price}")
            print(f"  quantity      = {quantity}")
            print(f"  is_maker      = {is_maker}")
            print(f"  timestamp     = {timestamp}")
            
            # 如果有 timestamp，显示转换后的时间
            if timestamp:
                try:
                    if isinstance(timestamp, (int, float)):
                        ts_sec = timestamp / 1000.0
                        dt = datetime.fromtimestamp(ts_sec, tz=timezone.utc)
                        print(f"  timestamp (转换后) = {dt}")
                        print(f"  当前时间          = {datetime.now(timezone.utc)}")
                        diff_sec = (datetime.now(timezone.utc) - dt).total_seconds()
                        print(f"  时间差            = {diff_sec:.2f} 秒 ({diff_sec/60:.2f} 分钟)")
                except Exception as e:
                    print(f"  timestamp 转换失败: {e}")
            
            print("\n" + "-" * 100)


def load_accounts_config() -> Dict[str, Any]:
    """从 config/accounts.json 加载账户配置。"""
    accounts_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "accounts.json"
    )
    if not os.path.exists(accounts_path):
        raise RuntimeError(f"找不到配置文件: {accounts_path}")
    with open(accounts_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_account_credentials(account_id: Optional[str] = None) -> tuple[str, str, str]:
    """从 config/accounts.json 获取账户凭证。"""
    data = load_accounts_config()
    accounts = data.get("accounts", {})
    
    def is_xt_trade_enabled(acc: Dict[str, Any]) -> bool:
        if acc.get("exchange") != "xt":
            return False
        if not acc.get("enabled", False):
            return False
        channels = acc.get("channels") or []
        return "trade" in channels
    
    target_key: Optional[str] = None
    
    if account_id is not None:
        if account_id not in accounts:
            raise RuntimeError(f"accounts.json 中不存在账户: {account_id}")
        target_key = account_id
    else:
        # 默认优先使用 account_008
        preferred = "account_008"
        if preferred in accounts and is_xt_trade_enabled(accounts[preferred]):
            target_key = preferred
        else:
            for key, acc in accounts.items():
                if is_xt_trade_enabled(acc):
                    target_key = key
                    break
    
    if target_key is None:
        raise RuntimeError("accounts.json 中没有启用的 XT 交易账户（enabled=true 且包含 trade 通道）")
    
    acc = accounts[target_key]
    api_key = acc.get("api_key")
    api_secret = acc.get("api_secret")
    
    if not api_key or not api_secret:
        raise RuntimeError(f"账户 {target_key} 缺少 api_key 或 api_secret")
    
    print(f"使用账户: {target_key} ({acc.get('name')})")
    
    return api_key, api_secret, target_key


async def main():
    parser = argparse.ArgumentParser(
        description="单独订阅 XT 成交记录，只打印原始数据",
    )
    parser.add_argument(
        "--account-id",
        type=str,
        default=None,
        help="使用的账户 ID（来自 config/accounts.json 的 key），默认自动选择 account_008",
    )
    args = parser.parse_args()
    
    # 获取账户凭证
    api_key, api_secret, account_id = get_account_credentials(args.account_id)
    
    # 创建订阅服务
    service = TradeSubscriberService(
        api_key=api_key,
        api_secret=api_secret,
        account_id=account_id,
    )
    
    print("=" * 100)
    print("XT 成交记录订阅器（仅查看原始数据，不插入数据库）")
    print("=" * 100)
    print(f"账户: {account_id}")
    print("正在连接 WebSocket...")
    print("等待成交数据推送...")
    print("=" * 100)
    print("\n提示: 按 Ctrl+C 停止\n")
    
    try:
        # 启动服务（会一直运行直到 Ctrl+C）
        await service.start()
    except KeyboardInterrupt:
        print("\n\n收到停止信号，正在关闭...")
        await service.stop()
        print(f"\n总共收到 {service.trade_count} 条成交记录")
        print("已退出")


if __name__ == "__main__":
    asyncio.run(main())
