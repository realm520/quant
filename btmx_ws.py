import json
import time 
import hmac, hashlib, base64
import random, string   
from datetime import datetime
from threading import Thread
from websocket import create_connection
from decimal import Decimal
import logging


def uuid32():
    return ''.join(random.choice(string.ascii_uppercase + string.ascii_lowercase + string.digits) for _ in range(32))


def utc_timestamp():
    tm = datetime.utcnow().timestamp()
    return int(tm * 1e3)

class BtmxWsDepth(object):
    def __init__(self, symbol):
        super().__init__()
        self.asks = []
        self.bids = []
        self.symbol = symbol

    def processDepth(self, depth, isAsk):
        for o in depth:
            isFound = False
            for a in self.asks:
                # print(a)
                if a[0] == o[0]:
                    if o[1] == "0":
                        # print(f"remove: {o[0]}")
                        self.asks.remove(a)
                    else:
                        a[1] = o[1]
                    isFound = True
                    break
            if not isFound:
                if isAsk and o[1] != '0':
                    self.asks.append(o)
                elif not isAsk and o[1] != '0':
                    self.bids.append(o)
        if isAsk:
            self.asks.sort(key=lambda e: Decimal(e[0]))
        else:
            self.bids.sort(key=lambda e: Decimal(e[0]), reverse=True)
       
    def update(self, newOrderBook):
        if newOrderBook['s'] != self.symbol.replace('-', '/'):
            return
        self.processDepth(newOrderBook['asks'], True)
        self.processDepth(newOrderBook['bids'], False)
        # print(f"asks: {self.asks}")
        # print(f"bids: {self.bids}")

    def getOrderBook(self):
        return {
            "symbol": self.symbol,
            "askPrice": self.asks[0][0],
            "askSize": self.asks[0][1],
            "bidPrice": self.bids[0][0],
            "bidSize": self.bids[0][1],
            "recvTime": int(time.time())
        }

class BtmxWsThread(Thread):
    def __init__(self, apiKey, secret, symbol, group, q):
        Thread.__init__(self)
        self.url = f"wss://btmx.com/{group}/api/stream/{symbol}"
        self.apiKey = apiKey
        self.secret = secret
        self.symbol = symbol
        self.depth = BtmxWsDepth(self.symbol)
        self.q = q
        self.ws = None
        self.running = True

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

    def connect(self):
        ts = utc_timestamp()
        headers = self.make_auth_header(ts, "api/stream")
        self.ws = create_connection(self.url, header=headers) #, http_proxy_host="192.168.1.3", http_proxy_port=1080

    def disconnect(self):
        try:
            self.ws.close()
            logging.debug("disconnected")
        # except WebSocketConnectionClosedException as e:
        except Exception as e:
            pass

    def listen(self):
        subscribe = """{
            "messageType":         "subscribe",
            "marketDepthLevel":    5,
            "recentTradeMaxCount": 20
        }"""
        self.ws.send(subscribe)
        depth = None
        start_t = 0
        while self.running:
            try:
                if time.time() - start_t >= 30:
                    # Set a 30 second ping to keep connection alive
                    self.ws.ping("keepalive")
                    start_t = time.time()
                data = self.ws.recv()
                try: 
                    msg = json.loads(data)
                    if msg['m'] == 'depth':
                        self.depth.update(msg)
                        self.q.put(self.depth.getOrderBook())
                    elif msg['m'] == 'order':
                        logging.info(msg)
                        self.q.put(msg)
                except: 
                    raise f"Failed to parse message a json: {data}"
            except ValueError as e:
                self.running = False
            except Exception as e:
                logging.warning(f"Exception in depth thread: {str(e)}")
                self.running = False
        self.q.put({'m':'threadStop', 's':self.symbol})
        logging.debug(f"listen complete {self.symbol}")

    def run(self):
        self.connect()
        self.listen()
        self.disconnect()

    def stop(self):
        self.running = False

if __name__ == '__main__':
    api_key = ""
    secret  = ""
    group   = "6"
    from queue import Queue
    # Make sure your API key has view and trade permissions
    # If you do not plan to place order with websocket, try connecting with:
    # wss://bitmax.io/api/public/ETH-BTC
    q = Queue()
    thread = BtmxWsThread(api_key, secret, 'BTC-USDT', group, q)
    thread.start()
    while True:
        try:
            data = q.get()
            print(data)
        except KeyboardInterrupt:
            break
    thread.stop()
    thread.join()
