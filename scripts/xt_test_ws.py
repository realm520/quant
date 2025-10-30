import os
import time
import threading
import requests
from pyxt.perp import Perp
from pyxt.websocket.perp import PerpWebsocketStreamClient



def get_listen_key():
    api_key = os.environ.get("XT_API_KEY")
    api_secret = os.environ.get("XT_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("XT_API_KEY / XT_API_SECRET 未设置")

    # 按你之前可成功的方式：直接使用 pyxt 的 Perp.get_listen_key()
    perp = Perp("https://fapi.xt.com", api_key, api_secret)
    return perp.get_listen_key()

if __name__ == '__main__':
    # 方案一：从返回三元组中提取 result 字段
    lk_tuple = get_listen_key()  # 预期为 (status_code, body_dict, headers)
    listen_key = lk_tuple[1].get("result") if isinstance(lk_tuple, tuple) and isinstance(lk_tuple[1], dict) else lk_tuple
    print(f"listenKey: {listen_key}")

    def message_handler(_, message):
        print(message)


    my_client = PerpWebsocketStreamClient(on_message=message_handler,
                                          is_auth=True)

    # Subscribe to a single symbol stream
    my_client.user_balance(listen_key=listen_key, action=PerpWebsocketStreamClient.ACTION_SUBSCRIBE)
    # keep heartbeat
    threading.Thread(target=my_client.heartbeat, daemon=False).start()
    time.sleep(5)
    # # Unsubscribe
    my_client.user_balance(listen_key=listen_key, action=PerpWebsocketStreamClient.ACTION_UNSUBSCRIBE)
    time.sleep(5)
    print("closing ws connection")
    my_client.stop()







