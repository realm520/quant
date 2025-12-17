#!/usr/bin/env python3
"""打印最新的 XT 成交记录，方便手动核对。

用法:
    python scripts/print_latest_trades.py tradoor_usdt
    python scripts/print_latest_trades.py tradoor_usdt --count 200
"""

import argparse
import json
import time
import os
import hmac
import hashlib
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import requests
from urllib.parse import urlencode

BASE_URL = "https://fapi.xt.com"
ACCOUNTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "accounts.json"
)


def load_accounts_config() -> Dict[str, Any]:
    if not os.path.exists(ACCOUNTS_PATH):
        raise RuntimeError(f"找不到配置文件: {ACCOUNTS_PATH}")
    with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_api_credentials_from_accounts(
    account_id: Optional[str] = None,
) -> Tuple[str, str, str]:
    """从 config/accounts.json 中读取 XT API KEY / SECRET。"""

    data = load_accounts_config()
    accounts: Dict[str, Any] = data.get("accounts", {})

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
        preferred = "account_008"
        if preferred in accounts and is_xt_trade_enabled(accounts[preferred]):
            target_key = preferred
        else:
            for key, acc in accounts.items():
                if is_xt_trade_enabled(acc):
                    target_key = key
                    break

    if target_key is None:
        raise RuntimeError("accounts.json 中没有启用的 XT 交易账户")

    acc = accounts[target_key]
    api_key = acc.get("api_key")
    api_secret = acc.get("api_secret")

    if not api_key or not api_secret:
        raise RuntimeError(f"账户 {target_key} 缺少 api_key 或 api_secret")

    print(f"使用账户: {target_key} ({acc.get('name')})")

    return api_key, api_secret, target_key


def build_signature_headers(
    method: str,
    path: str,
    query_params: Dict[str, Any],
    api_key: str,
    api_secret: str,
) -> Dict[str, str]:
    """构造 XT 所需的鉴权头部。"""

    timestamp = str(int(time.time() * 1000))

    message = ""
    if query_params:
        sorted_params = dict(
            sorted(
                {k: v for k, v in query_params.items() if v is not None}.items(),
                key=lambda e: e[0],
            )
        )
        message = "&".join(f"{k}={sorted_params[k]}" for k in sorted_params)

    if message:
        signkey = (
            f"xt-validate-appkey={api_key}"
            f"&xt-validate-timestamp={timestamp}"
            f"#{path}#{message}"
        )
    else:
        signkey = (
            f"xt-validate-appkey={api_key}"
            f"&xt-validate-timestamp={timestamp}"
            f"#{path}"
        )

    signature = hmac.new(
        api_secret.encode("utf-8"),
        signkey.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "validate-signversion": "2",
        "xt-validate-appkey": api_key,
        "xt-validate-timestamp": timestamp,
        "xt-validate-signature": signature,
        "xt-validate-algorithms": "HmacSHA256",
        "xt-validate-recvwindow": "8000",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return headers


def fetch_latest_trades(
    symbol: str,
    count: int = 100,
    hours: int = 1,
    account_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """获取最新的成交记录。"""

    api_key, api_secret, _ = get_api_credentials_from_accounts(account_id=account_id)

    path = "/future/trade/v1/order/trade-list"
    all_items: List[Dict[str, Any]] = []
    page = 1
    page_size = 100

    # 时间范围：最近 N 小时
    now_ms = int(time.time() * 1000)
    start_time = now_ms - (hours * 60 * 60 * 1000)
    end_time = now_ms

    print(f"拉取时间范围: {datetime.fromtimestamp(start_time/1000)} ~ {datetime.fromtimestamp(end_time/1000)}")

    while len(all_items) < count:
        params: Dict[str, Any] = {
            "symbol": symbol,
            "page": page,
            "size": page_size,
            "startTime": start_time,
            "endTime": end_time,
        }

        headers = build_signature_headers("GET", path, params, api_key, api_secret)

        resp = requests.get(
            BASE_URL + path,
            headers=headers,
            params=params,
            timeout=10,
        )

        if not resp.ok:
            print("请求失败:")
            print("status_code:", resp.status_code)
            print("response text:", resp.text)
            resp.raise_for_status()

        data = resp.json()

        if data.get("returnCode") != 0:
            print("接口返回错误:", data)
            break

        result = data.get("result") or {}
        items = result.get("items") or []

        if not items:
            break

        all_items.extend(items)

        if len(all_items) >= count:
            all_items = all_items[:count]
            break

        page += 1
        time.sleep(0.05)

    return all_items


def format_trade(trade: Dict[str, Any]) -> str:
    """格式化单条成交记录。"""

    exec_id = trade.get("execId", "")
    order_id = trade.get("orderId", "")
    symbol = trade.get("symbol", "")
    side = trade.get("takerMaker", "")
    price = trade.get("price", 0)
    quantity = trade.get("quantity", 0)
    fee = trade.get("fee", 0)
    fee_coin = trade.get("feeCoin", "")
    ts_ms = trade.get("timestamp", 0)

    # 时间戳转可读时间
    ts_str = datetime.fromtimestamp(ts_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if ts_ms else ""

    return (
        f"execId={exec_id:<20} | "
        f"orderId={order_id:<20} | "
        f"symbol={symbol:<15} | "
        f"side={side:<6} | "
        f"price={price:<12} | "
        f"quantity={quantity:<15} | "
        f"fee={fee} {fee_coin:<8} | "
        f"timestamp={ts_ms} ({ts_str})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="打印最新的 XT 成交记录，方便手动核对",
    )
    parser.add_argument("symbol", help="交易对，例如 tradoor_usdt")
    parser.add_argument(
        "--count",
        type=int,
        default=100,
        help="要打印的成交数量（默认 100 条）",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=1,
        help="查询最近多少小时的数据（默认 1 小时）",
    )
    parser.add_argument(
        "--account-id",
        type=str,
        default=None,
        help="使用的账户 ID，默认自动选择 account_008",
    )
    args = parser.parse_args()

    print("=" * 80)
    print(f"开始拉取 {args.symbol} 最新的 {args.count} 条成交记录")
    print("=" * 80)

    trades = fetch_latest_trades(
        symbol=args.symbol,
        count=args.count,
        hours=args.hours,
        account_id=args.account_id,
    )

    print(f"\n总共获取成交记录数量: {len(trades)}")
    print("=" * 80)
    print("\n成交记录详情（按时间倒序，最新的在前）:\n")

    # 按时间戳倒序排序（最新的在前）
    trades_sorted = sorted(trades, key=lambda x: x.get("timestamp", 0), reverse=True)

    for idx, trade in enumerate(trades_sorted, 1):
        print(f"[{idx:4d}] {format_trade(trade)}")

    print("\n" + "=" * 80)
    print("打印完成。你可以用这些 execId 去数据库查询对应的 trade_id 进行核对。")
    print("=" * 80)


if __name__ == "__main__":
    main()
