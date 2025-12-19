#!/usr/bin/env python3
"""查看 XT WebSocket 成交数据的原始数据和解析后的 record。

复用 XTUserStreamService._save_trade_update 的解析逻辑，但不插入数据库，
只打印原始数据和解析后的 record 字段。

用法:
    python scripts/view_xt_trade_raw_data.py
    python scripts/view_xt_trade_raw_data.py --account-id account_008
"""

import asyncio
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tri_arb.services.xt_user_stream import XTUserStreamService, DecimalEncoder
from tri_arb.storage.database import DatabaseManager
from tri_arb.storage.xt_websocket_models import XTTradeUpdate


class TradeViewerService(XTUserStreamService):
    """只查看成交数据，不保存到数据库的服务。"""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        account_id: Optional[str] = None,
    ):
        # 创建一个假的 db_manager（不会真正使用）
        # 但我们需要它来初始化父类
        fake_db_url = "postgresql+asyncpg://fake:fake@localhost/fake"
        db_manager = DatabaseManager(fake_db_url)
        
        # 只启用 trade 频道
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
        """复用了父类的解析逻辑，但只打印不保存。"""
        try:
            # 复用父类的解析逻辑
            # 支持多种格式：
            # 1. trades 列表格式: {"trades": [...]}
            # 2. 单个成交对象格式: {"trade_id": "...", "order_id": "...", ...}
            # 3. XT WebSocket 格式: {"orderId": "...", "orderSide": "...", ...}
            trades = []
            if "trades" in data and isinstance(data.get("trades"), list):
                trades = data.get("trades", [])
            elif isinstance(data, list):
                trades = data
            elif "orderId" in data or "order_id" in data or "trade_id" in data or "tradeId" in data:
                # 单个成交对象（包括 XT 格式），转换为列表
                trades = [data]
            
            if not trades:
                print("⚠️  没有成交数据")
                return
            
            for trade in trades:
                self.trade_count += 1
                
                # 支持不同的字段名
                # XT 格式没有 trade_id，使用 orderId + timestamp 作为 trade_id
                trade_id = trade.get("trade_id") or trade.get("tradeId") or ""
                order_id = trade.get("orderId") or trade.get("order_id") or ""
                
                # 如果没有 trade_id，使用 orderId + timestamp 生成一个
                if not trade_id and order_id:
                    timestamp = trade.get("timestamp")
                    if timestamp:
                        trade_id = f"{order_id}_{timestamp}"
                    else:
                        trade_id = order_id
                
                if not trade_id:
                    print("⚠️  成交缺少 trade_id 和 orderId，跳过")
                    continue
                
                symbol = trade.get("symbol") or ""
                # XT 使用 orderSide，其他使用 side
                side = trade.get("orderSide") or trade.get("side") or ""
                price = self._safe_decimal(trade.get("price") or "0")
                quantity = self._safe_decimal(trade.get("quantity") or trade.get("qty") or "0")
                quote_quantity = self._safe_decimal(
                    trade.get("quote_quantity") or 
                    trade.get("quoteQuantity") or 
                    trade.get("amount") or 
                    str(price * quantity)  # 如果没有提供，计算它
                )
                
                # 使用 XT 的 timestamp（如果存在），否则使用当前时间
                timestamp = trade.get("timestamp")
                if timestamp:
                    try:
                        # XT timestamp 是秒级时间戳
                        if isinstance(timestamp, (int, float)):
                            update_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                        else:
                            update_time = datetime.utcnow()
                    except (ValueError, OSError):
                        update_time = datetime.utcnow()
                else:
                    update_time = datetime.utcnow()
                
                # 构造 record（不插入数据库，只用于显示）
                record = XTTradeUpdate(
                    update_time=update_time,
                    account_id=self.account_id,
                    symbol=symbol,
                    order_id=str(order_id),
                    trade_id=str(trade_id),
                    side=side,
                    price=price,
                    quantity=quantity,
                    quote_quantity=quote_quantity,
                    commission=self._safe_decimal(trade.get("commission") or trade.get("fee") or "0"),
                    commission_asset=trade.get("commission_asset") or trade.get("feeCurrency") or "",
                    is_maker=trade.get("is_maker") or trade.get("isMaker") or False,
                    position_side=trade.get("position_side") or trade.get("positionSide") or "",
                    raw_data=json.dumps(trade, cls=DecimalEncoder),
                )
                
                # 打印分隔线
                print("\n" + "=" * 80)
                print(f"成交 #{self.trade_count}")
                print("=" * 80)
                
                # 打印原始数据
                print("\n📦 原始数据 (Raw Data):")
                print(json.dumps(trade, indent=2, ensure_ascii=False, cls=DecimalEncoder))
                
                # 打印解析后的 record 字段
                print("\n📋 解析后的 Record 字段:")
                print(f"  trade_id        = {record.trade_id}")
                print(f"  order_id        = {record.order_id}")
                print(f"  symbol          = {record.symbol}")
                print(f"  account_id      = {record.account_id}")
                print(f"  side            = {record.side}")
                print(f"  price           = {record.price}")
                print(f"  quantity        = {record.quantity}")
                print(f"  quote_quantity  = {record.quote_quantity}")
                print(f"  commission      = {record.commission}")
                print(f"  commission_asset= {record.commission_asset}")
                print(f"  is_maker        = {record.is_maker}")
                print(f"  position_side   = {record.position_side}")
                print(f"  update_time     = {record.update_time} (UTC)")
                print(f"  raw_data        = {record.raw_data[:200]}..." if len(record.raw_data) > 200 else f"  raw_data        = {record.raw_data}")
                
                print("\n" + "-" * 80)
        
        except Exception as e:
            print(f"❌ 处理成交数据时出错: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()


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
        description="查看 XT WebSocket 成交数据的原始数据和解析后的 record",
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
    
    # 创建查看服务
    service = TradeViewerService(
        api_key=api_key,
        api_secret=api_secret,
        account_id=account_id,
    )
    
    print("=" * 80)
    print("XT 成交数据查看器")
    print("=" * 80)
    print(f"账户: {account_id}")
    print("正在连接 WebSocket...")
    print("等待成交数据推送...")
    print("=" * 80)
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
