import argparse
import json
import time
import os
import hmac
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import requests
from urllib.parse import urlencode

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tri_arb.storage.xt_websocket_models import XTTradeUpdate

BASE_URL = "https://fapi.xt.com"  # XT 期货域名
ACCOUNTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "accounts.json"
)


def load_accounts_config() -> Dict[str, Any]:
    if not os.path.exists(ACCOUNTS_PATH):
        raise RuntimeError(f"找不到配置文件: {ACCOUNTS_PATH}")
    with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_database_url() -> str:
    """从 accounts.json 的 global_settings 中拿数据库 URL，并转换为同步驱动。"""
    data = load_accounts_config()
    db_url = data.get("global_settings", {}).get("database_url")
    if not db_url:
        raise RuntimeError("accounts.json.global_settings.database_url 未配置")
    # 应用里用的是 asyncpg，这里改成同步驱动
    return db_url.replace("+asyncpg", "")


def get_api_credentials_from_accounts(
    account_id: Optional[str] = None,
) -> Tuple[str, str, str]:
    """从 config/accounts.json 中读取 XT API KEY / SECRET。

    - 如果传入 account_id，则使用对应账户。
    - 否则选择第一个 `exchange == xt` 且 `enabled == true`
      且包含 trade 通道的账户。
    """

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

    # 1. 如果显式指定了 account_id，优先使用
    if account_id is not None:
        if account_id not in accounts:
            raise RuntimeError(f"accounts.json 中不存在账户: {account_id}")
        target_key = account_id
    else:
        # 2. 默认优先使用 account_008
        preferred = "account_008"
        if preferred in accounts and is_xt_trade_enabled(accounts[preferred]):
            target_key = preferred
        else:
            # 3. 否则选择第一个启用的 XT 交易账户
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

    # 返回 api_key, api_secret, account_id(用于对比 xt_trade_update.account_id)
    return api_key, api_secret, target_key


def build_signature_headers(
    method: str,
    path: str,
    query_params: Dict[str, Any],
    api_key: str,
    api_secret: str,
) -> Dict[str, str]:
    """构造 XT 所需的鉴权头部（复用现有 xt_perp 适配器的签名逻辑）。

    签名规则（signversion=2）：
    - 对于 GET + form-urlencoded：
      1. 将 query 参数按 key 升序排序，拼成 `k=v&k2=v2` 的 message 字符串。
      2. 构造 signkey:
         `xt-validate-appkey={api_key}&xt-validate-timestamp={timestamp}#{path}#{message}`
      3. 对 signkey 做 HMAC-SHA256，hex 输出即为 `xt-validate-signature`。
    """

    timestamp = str(int(time.time() * 1000))

    # 1. 构造 message（按 key 升序）
    message = ""
    if query_params:
        sorted_params = dict(
            sorted(
                {k: v for k, v in query_params.items() if v is not None}.items(),
                key=lambda e: e[0],
            )
        )
        message = "&".join(f"{k}={sorted_params[k]}" for k in sorted_params)

    # 2. 构造 signkey
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

    # 3. HMAC-SHA256 签名
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


def fetch_trades(
    symbol: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    page_size: int = 100,
    max_pages: Optional[int] = None,
    max_count: int = 5000,
    account_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """批量获取成交记录，自动翻页，直到没有数据或达到限制为止。

    - start_time / end_time 为毫秒时间戳（和文档一致）。
    - max_count 控制最多拿多少条成交（默认 5000 条）。
    """

    api_key, api_secret, real_account_id = get_api_credentials_from_accounts(account_id=account_id)

    path = "/future/trade/v1/order/trade-list"
    all_items: List[Dict[str, Any]] = []
    page = 1

    # 安全起见，page_size 不超过 100
    page_size = min(page_size, 100)

    while True:
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

        # 如果出现 4xx/5xx，先打印出返回内容再抛异常，方便排查
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

        print(f"page={page}, 本页成交数量: {len(items)}")

        if not items:
            break

        all_items.extend(items)

        # 如果已经达到 max_count，则截断并退出
        if len(all_items) >= max_count:
            all_items = all_items[:max_count]
            print(f"达到最大条数限制 max_count={max_count}，停止拉取。")
            break

        if max_pages is not None and page >= max_pages:
            break

        page += 1
        # 文档限流 200/s，这里稍微 sleep 一下
        time.sleep(0.05)

    return all_items, real_account_id


def compare_with_xt_trade_update(
    trades: List[Dict[str, Any]],
    symbol: str,
    account_id: str,
) -> None:
    """将 API 返回的成交与 xt_trade_update 表进行对比，找出缺失的成交。

    xt_trade_update.trade_id 的格式是：`{order_id}_{timestamp}`，例如：
    568975636608241600_1765356362850

    因此这里用以下规则对齐：
    - 对于每一条 API 成交，取：
        db_trade_id = f\"{orderId}_{timestamp}\"
      然后检查 xt_trade_update.trade_id 是否存在这条记录。
    - 同时要求 account_id、symbol 匹配，避免跨账号/跨交易对误判。
    """

    if not trades:
        print("API 未返回任何成交记录，无需对比。")
        return

    db_url = get_database_url()
    engine = create_engine(db_url)

    missing: List[Dict[str, Any]] = []

    with Session(engine) as session:
        for idx, item in enumerate(trades):
            order_id = item.get("orderId")
            ts = item.get("timestamp")
            api_symbol = item.get("symbol")
            if not order_id or ts is None or not api_symbol:
                continue

            db_trade_id = f"{order_id}_{ts}"

            exists = (
                session.query(XTTradeUpdate)
                .filter(
                    XTTradeUpdate.trade_id == db_trade_id,
                    XTTradeUpdate.account_id == account_id,
                    XTTradeUpdate.symbol == api_symbol,
                )
                .first()
            )
            if not exists:
                missing.append(item)

    print(f"总 API 成交数量: {len(trades)}")
    print(f"xt_trade_update 中缺失的成交数量: {len(missing)}")
    if missing:
        print("示例缺失成交前 10 条:")
        for t in missing[:10]:
            print(t)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从 XT 期货接口批量拉取成交记录",
    )
    parser.add_argument("symbol", help="交易对，例如 btc_usdt")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="从现在往前推的天数（默认 7 天）",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="每页大小（最大 100，默认 100）",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="最多翻多少页（默认不限，直到没有数据）",
    )
    parser.add_argument(
        "--max-count",
        type=int,
        default=5000,
        help="最多拉取多少条成交记录（默认 5000 条）",
    )
    parser.add_argument(
        "--account-id",
        type=str,
        default=None,
        help="使用的账户 ID（来自 config/accounts.json 的 key），"
        "默认自动选择第一个启用的 XT 交易账户。",
    )
    parser.add_argument(
        "--no-compare",
        action="store_true",
        help="只拉取 API 成交，不和 xt_trade_update 做对比。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    now_ms = int(time.time() * 1000)
    days_ms = args.days * 24 * 60 * 60 * 1000
    start_time = now_ms - days_ms
    end_time = now_ms

    print(
        f"开始拉取 {args.symbol} 最近 {args.days} 天的成交记录，"
        f"page_size={args.page_size}, max_pages={args.max_pages}, "
        f"max_count={args.max_count}, account_id={args.account_id}"
    )

    trades, real_account_id = fetch_trades(
        symbol=args.symbol,
        start_time=start_time,
        end_time=end_time,
        page_size=args.page_size,
        max_pages=args.max_pages,
        max_count=args.max_count,
        account_id=args.account_id,
    )

    print(f"总共获取成交记录数量: {len(trades)}")

    if not args.no_compare:
        compare_with_xt_trade_update(trades, args.symbol, real_account_id)
    else:
        # 简单打印前几条
        for t in trades[:5]:
            print(t)


if __name__ == "__main__":
    main()
