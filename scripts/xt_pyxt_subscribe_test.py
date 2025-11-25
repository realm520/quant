#!/usr/bin/env python3
"""XT 用户数据流订阅快速测试脚本（使用 pyxt）。

要求：
- 已安装 pyxt: pip install pyxt
- 已设置环境变量：XT_API_KEY, XT_API_SECRET

用法：
  python scripts/xt_pyxt_subscribe_test.py [channels]

channels 可选，逗号分隔，支持：account,position,order,trade（默认全部）
"""

import json
import os
import sys
import threading
import time
from typing import Optional


def ensure_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        print(f"[ERROR] 环境变量未设置: {name}")
        sys.exit(1)
    return val


def get_listen_key_via_pyxt_sign(host: str, api_key: str, api_secret: str) -> Optional[str]:
    """通过 pyxt 的签名辅助生成 header，直接请求 listen-key。

    兼容多种可能端点；返回第一个成功拿到的 listenKey。
    """
    try:
        import requests
        # 优先使用 pyxt.perp.Perp 的签名辅助
        try:
            from pyxt.perp import Perp
            perp = Perp(host, api_key, api_secret)
            create_sign = perp._create_sign  # type: ignore[attr-defined]
        except Exception:
            # 兜底：尝试 pyxt 其他模块（若未来变动）
            from pyxt.perp import Perp  # 再尝试一次，若失败会抛错
            perp = Perp(host, api_key, api_secret)
            create_sign = perp._create_sign  # type: ignore[attr-defined]

        candidate_paths = [
            "/future/user/v1/listen-key",  # fapi 风格
            "/v1/user/listen-key",        # sapi 风格
            "/future/user/v1/stream/listen-key",
        ]

        for path in candidate_paths:
            url = host.rstrip("/") + path
            headers = create_sign(
                api_key,
                api_secret,
                path=path,
                bodymod="application/json",
                params=None,
            )
            try:
                resp = requests.post(url, headers=headers, timeout=10)
                body = {}
                try:
                    body = resp.json()
                except Exception:
                    pass
                print(f"[DEBUG] listen-key {url} -> {resp.status_code} {str(body)[:200]}")
                if resp.status_code == 200 and isinstance(body, dict):
                    lk = body.get("listenKey") or body.get("listen_key")
                    if not lk and isinstance(body.get("result"), dict):
                        lk = body["result"].get("listenKey") or body["result"].get("listen_key")
                    if lk:
                        return lk
            except Exception as e:
                print(f"[WARN] 请求失败 {url}: {e}")
                continue
    except Exception as e:
        print(f"[ERROR] 获取 listen_key 失败（签名路径）：{e}")
    return None


def main():
    # 读取凭证
    api_key = ensure_env("XT_API_KEY")
    api_secret = ensure_env("XT_API_SECRET")

    # 订阅频道
    channels_arg = sys.argv[1] if len(sys.argv) > 1 else "account,position,order,trade"
    channels = {s.strip() for s in channels_arg.split(",") if s.strip()}

    # 导入 pyxt WebSocket 客户端
    try:
        from pyxt.websocket.perp import PerpWebsocketStreamClient
        from pyxt.perp import Perp
    except ImportError:
        print("[ERROR] 未安装 pyxt，请先执行: pip install pyxt")
        sys.exit(1)

    # 优先使用 sapi 获取 listen-key，不同环境可切换 host
    hosts = [
        "https://sapi.xt.com",
        "https://fapi.xt.com",
    ]

    listen_key: Optional[str] = None
    for host in hosts:
        listen_key = get_listen_key_via_pyxt_sign(host, api_key, api_secret)
        if listen_key:
            print(f"[INFO] listen_key 获取成功 (host={host}): {listen_key[:8]}***")
            break

    if not listen_key:
        print("[ERROR] 无法获取 listen_key，请检查 API 权限/签名/时间同步/IP 白名单")
        sys.exit(2)

    # WebSocket 回调
    def on_message(ws_app, message):
        try:
            data = json.loads(message)
        except Exception:
            data = message
        print("[WS] message:", (json.dumps(data) if isinstance(data, dict) else str(data))[:500])

    def on_open(ws_app):
        print("[WS] open")

    def on_close(ws_app, code, msg):
        print(f"[WS] close code={code} msg={msg}")

    def on_error(ws_app, error):
        print(f"[WS] error: {error}")

    # 创建客户端（鉴权流）
    ws = PerpWebsocketStreamClient(
        stream_url="wss://fstream.xt.com",
        on_message=on_message,
        on_open=on_open,
        on_close=on_close,
        on_error=on_error,
        is_auth=True,
    )

    # 根据频道订阅
    if "account" in channels:
        ws.user_balance(listen_key, action="sub")
        print("[SUB] account/balance")
    if "position" in channels:
        ws.user_position(listen_key, action="sub")
        print("[SUB] position")
    if "order" in channels:
        ws.user_order(listen_key, action="sub")
        print("[SUB] order")
    if "trade" in channels:
        ws.user_trade(listen_key, action="sub")
        print("[SUB] trade")

    # 在独立线程运行，主线程打印心跳
    t = threading.Thread(target=ws.run, daemon=True)
    t.start()

    try:
        while t.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("[INFO] Ctrl+C, exiting...")


if __name__ == "__main__":
    main()


