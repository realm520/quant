from notify import qyvx
from exapi import ZBApi
import ujson
import time
from loguru import logger


with open("config.json", "r") as f:
    config = ujson.load(f)


def price_warning(symbol, price, volume, upOrDown):
    qyvx.push_message_QiYeVX(f"{symbol} price [{upOrDown}] to: {price} - {volume}")

class PriceMonitor(object):
    def __init__(self, market, price, side) -> None:
        self.market = market
        pairs = market.split('_')
        self.symbol = pairs[0]
        self.price = price
        self.side = side
        self.lastNotifyTime = 0
    
    def price_check(self, asks, bids):
        if self.side == 1:
            if bids[0][0] > self.price:
                now = int(time.time())
                if now - self.lastNotifyTime > 300:
                    price_warning(self.symbol, bids[0][0], bids[0][1], "UP")
        else:
            if asks[0][0] < self.price:
                now = int(time.time())
                if now - self.lastNotifyTime > 300:
                    price_warning(self.symbol, asks[0][0], asks[0][1], "DOWN")


hx_up = PriceMonitor("hx_qc", 0.1, 1)
hx_down = PriceMonitor("hx_qc", 0.02, 2)
while True:
    z = ZBApi(config["exchange"]["ZB"]["access_key"], config["exchange"]["ZB"]["secret_key"])
    ret = z.depth("hx_qc", 3)
    hx_up.price_check(ret['asks'], ret['bids'])
    hx_down.price_check(ret['asks'], ret['bids'])
    logger.debug(f"{ret['asks'][0][0]} - {ret['bids'][0][0]}")
    time.sleep(5)
# qyvx.push_message_QiYeVX("ZB is up")