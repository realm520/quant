import fire
import json 
import requests
from datetime import datetime
import hmac, hashlib, base64
import random, string   
from pprint import pprint  


class BitMax(object):
    def __init__(self, apiKey, secret):
        self.url = "https://btmx.com"
        self.apiKey = apiKey
        self.secret = secret
        account_group = self.user_info()
        self.account_group = account_group['accountGroup']

    def uuid32(self):
        return ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(32))

    def utc_timestamp(self):
        tm = datetime.utcnow().timestamp()
        return int(tm * 1e3)

    def make_auth_header(self, timestamp, api_path, coid=None): 
        # convert timestamp to string   
        if isinstance(timestamp, bytes):
            timestamp = timestamp.decode("utf-8")
        elif isinstance(timestamp, int):
            timestamp = str(timestamp)

        if coid is None:
            msg = bytearray(f"{timestamp}+{api_path}".encode("utf-8"))
        else:
            msg = bytearray(f"{timestamp}+{api_path}+{coid}".encode("utf-8"))

        hmac_key = base64.b64decode(self.secret)
        signature = hmac.new(hmac_key, msg, hashlib.sha256)
        signature_b64 = base64.b64encode(signature.digest()).decode("utf-8")  
        header = {
            "x-auth-key": self.apiKey,
            "x-auth-signature": signature_b64,
            "x-auth-timestamp": timestamp,
        }

        if coid is not None:
            header["x-auth-coid"] = coid

        return header


    def POST(self, url, *args, **kwargs):
        try: 
            res = requests.post(url, *args, **kwargs)
            return self.__parse_response(res)
        except requests.exceptions.ConnectionError: 
            print(f"[WARN] Failed to connect {url}")
            return None
        except: 
            raise

    def DELETE(self, url, *args, **kwargs):
        try: 
            res = requests.delete(url, *args, **kwargs)
            return self.__parse_response(res)
        except requests.exceptions.ConnectionError: 
            print(f"[WARN] Failed to connect {url}")
            return None
        except: 
            raise

    def GET(self, url, *args, **kwargs):
        try: 
            res = requests.get(url, *args, **kwargs)
            return self.__parse_response(res)
        except requests.exceptions.ConnectionError: 
            print(f"[WARN] Failed to connect {url}")
            return None
        except: 
            raise

    def __parse_response(self, res):
        if res is None:
            return None 

        if res.status_code == 200:
            data = json.loads(res.text)
            return data
        else:
            print(f"request failed, error code = {res.status_code}")
            print(res.text)

    def listAssets(self):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "assets")
        return self.GET(f"{self.url}/api/v1/assets", headers=headers)

    def listProducts(self):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "products")
        return self.GET(f"{self.url}/api/v1/products", headers=headers)

    def getTradingFee(self):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "fees")
        return self.GET(f"{self.url}/api/v1/fees", headers=headers)

    def getBalance(self, asset='all'):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "balance")
        if asset == 'all':
            return self.GET(f"{self.url}/{self.account_group}/api/v1/balance", headers=headers)
        else:
            return self.GET(f"{self.url}/{self.account_group}/api/v1/balance/{asset}", headers=headers)

    def listOpenOrders(self):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "order/open")
        return self.GET(f"{self.url}/{self.account_group}/api/v1/order/open", headers=headers)

    def listHistoricalOrders(self):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "order/history")
        return self.GET(f"{self.url}/{self.account_group}/api/v2/order/history", headers=headers)

    def getOrderStatus(self, coid):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "order")
        return self.GET(f"{self.url}/{self.account_group}/api/v1/order/{coid}", headers=headers)

    def level1OrderBook(self, symbol):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "quote")
        return self.GET(f"{self.url}/api/v1/quote?symbol={symbol}", headers=headers)

    def level2OrderBook(self, symbol, n):
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "depth")
        return self.GET(f"{self.url}/api/v1/depth?symbol={symbol}&n={n}", headers=headers)

    def placeNewOrder(self, symbol, price, quantity, side):
        ts = self.utc_timestamp()
        coid = self.uuid32()
        headers = self.make_auth_header(ts, "order", coid)
        order = dict(
            coid       = coid,
            time       = ts,
            symbol     = symbol.replace("-", "/"),
            orderPrice = str(price),
            orderQty   = str(quantity),
            orderType  = "limit",
            side       = side.lower()
        )
        pprint(order)
        return self.POST(f"{self.url}/{self.account_group}/api/v1/order", json=order, headers=headers)

    def cancelOrder(self, origCoid, symbol):
        ts = self.utc_timestamp()
        coid = self.uuid32()
        headers = self.make_auth_header(ts, "order", coid)
        order = dict(
            coid       = coid,
            origCoid   = origCoid,
            time       = ts,
            symbol     = symbol.replace("-", "/")
        )
        return self.DELETE(f"{self.url}/{self.account_group}/api/v1/order", json=order, headers=headers)

    def user_info(self): 
        ts = self.utc_timestamp()
        headers = self.make_auth_header(ts, "user/info")
        return self.GET(f"{self.url}/api/v1/user/info", headers=headers)


class BtmxCli(object):
    def __init__(self):
        super().__init__()
        self.btmx = BitMax("IsjLHkaqIvG8evygdPqL8ZHoETVUpXle", "huKb2kMUdCIZdmqGXUtakcixDHEvaECJ5k9Zp5saGVcoUmr84nbJYfZE6kJYEnYU")

    def getOrderStatus(self, coid=''):
        if coid == "":
            print("Please indicate coid.")
        else:
            res = self.btmx.getOrderStatus(coid)
            pprint(res)

if __name__ == "__main__":
    fire.Fire(BtmxCli)
    # btmx = BitMax("", "")
    
    # res = btmx.placeNewOrder(
    #     symbol = "ETH/USDT",
    #     price = "188.08596",
    #     quantity = "0.027",
    #     side = "sell")
    # res = btmx.listAssets()
    # res = btmx.listProducts()
    # res = btmx.level1OrderBook('BTMX-USDT')
    # res = btmx.level2OrderBook('BTMX-USDT', 5)
    # res = btmx.getBalance('USDT')
    # res = btmx.listOpenOrders()
    # res = btmx.listHistoricalOrders()
    # res = btmx.getOrderStatus('YdFEX7iHVZJlIDrVgysiSmeo2S9yoqzZ')
    # res = btmx.user_info()
    # pprint(res)
