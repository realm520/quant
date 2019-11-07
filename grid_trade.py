import json
import time
import copy
from datetime import datetime
import hmac, hashlib, base64
# from pprint import pprint  
import logging
import prettytable as pt
from decimal import Decimal
from btmx import BitMax


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s",
                    datefmt = '%Y-%m-%d  %H:%M:%S %a'
                    )



class GridTrader(object):
    def __init__(self, sid, ex, symbol, amount):
        self.sid = sid
        self.stateFile = f'./grid_trade_{symbol}_{sid}.json'
        self.ex = ex
        self.symbol = symbol
        self.amount = amount
        self.totalUsdt = 100
        self.positions = []
        self.openedPositions = []
        self.closedPositions = []
        self.fee = 0.0004
        self.statusUpdated = False
        try:
            with open(self.stateFile, 'r') as fp:
                state = json.load(fp)
                if 'openedPositions' in state:
                    self.openedPositions = state['openedPositions']
                if 'closedPositions' in state:
                    self.closedPositions = state['closedPositions']
        except Exception as e:
            pass

    def doPassiveTrade(self):
        orderBook = self.ex.level1OrderBook(self.symbol)
        if orderBook is None:
            return
        logging.info(f'Tick: {json.dumps(orderBook)}')
        if len(self.openedPositions) == 0:
            self.openPosition(orderBook)
        elif len(self.openedPositions) >= 10:
            logging.info("More than 10 positions opened, pending...")
            return
        else:
            for p in self.openedPositions:
                if p['status'] == 1:
                    logging.info(f"Need to place open order...{p['price']}")
                    continue
                elif p['status'] == 2:
                    res = self.ex.getOrderStatus(p['placeOrderId'])
                    if res is not None and res['code'] == 0:
                        if res['data']['status'] == 'Filled':
                            print('buy order filled, place sell order')
                            print(p)
                            p['status'] = 3 # order is Filled
                            closePrice = Decimal(p['price']) * Decimal(1.01 + self.fee * 2)
                            closePrice = self._pricePrecision(closePrice)
                            res = self.ex.placeNewOrder(self.symbol, closePrice, p['volume'], 'sell')
                            if res is not None and res['data']['action'] == 'new':
                                p['closeOrderId'] = res['data']['coid']
                                p['status'] = 4 # place close order
                                p['closedPrice'] = closePrice
                    elif res['data']['status'] == 'Cancel':
                        self.openedPositions.remove(p)
                elif p['status'] == 3:
                    logging.info("Need to place close order...")
                elif p['status'] == 4:
                    res = self.ex.getOrderStatus(p['closeOrderId'])
                    if res is not None and res['code'] == 0 and res['data']['status'] == 'Filled':
                        p['status'] = 5
                        p['avgClosedPrice'] = res['data']['avgPrice']
                        self.closedPositions.append(p)
                        self.openedPositions.remove(p)
            # process lower grid
            if len(self.openedPositions) >= 1:
                lowPrice = Decimal(self.openedPositions[-1]['price'])
                currentPrice = Decimal(orderBook['askPrice'])
                if len(self.openedPositions) < 10 \
                    and self.openedPositions[-1]['status'] >= 3 \
                    and lowPrice * Decimal(0.99 - self.fee) > currentPrice:
                    self.openPosition(orderBook)

    def openPosition(self, orderBook):
        openPrice = Decimal(orderBook['askPrice'])
        gap = (openPrice - Decimal(orderBook['bidPrice'])) / openPrice
        if gap > Decimal(0.005):
            return False
        volume = Decimal(self.amount) / openPrice
        if volume > Decimal(orderBook['askSize']):
            return False
        p = {
            'symbol': self.symbol.replace('-', '/'),
            'price': self._pricePrecision(openPrice),
            'volume': f"{volume:>.3f}",
            'status': 1, # prepare to open position
            'closedPrice': 0,
            'placeOrderId': '',
            'closeOrderId': ''
        }
        res = self.ex.placeNewOrder(self.symbol, p['price'], p['volume'], 'buy')
        if res is not None and res['code'] == 0 and res['data']['action'] == 'new':
            p['placeOrderId'] = res['data']['coid']
            p['status'] = 2 # order is new
        self.openedPositions.append(p)
        return True

    def savePositions(self):
        with open(self.stateFile, 'w') as fp:
            data = {'openedPositions': self.openedPositions, 'closedPositions': self.closedPositions}
            json.dump(data, fp)

    def printStat(self):
        stat = {'TotalOpenPositions': len(self.openedPositions), 'TotalClosePositions': len(self.closedPositions)}
        tb = pt.PrettyTable( ["Price", "Symbol", "Volume", "PlaceOrderId", "ClosedPrice", "CloseOrderId", "Status"])
        for p in self.openedPositions:
            tb.add_row([p['price'], p['symbol'], p['volume'], p['placeOrderId'], p['closedPrice'], p['closeOrderId'], p['status']])
        print(tb)
        tb = pt.PrettyTable( ["Price", "Symbol", "Volume", "PlaceOrderId", "ClosedPrice", "CloseOrderId", "Status"])
        profit = Decimal(0)
        for p in self.closedPositions:
            profit += (Decimal(p['closedPrice']) - Decimal(p['price'])) * Decimal(p['volume'])
            tb.add_row([p['price'], p['symbol'], p['volume'], p['placeOrderId'], p['closedPrice'], p['closeOrderId'], p['status']])
        print(tb)
        stat['Profit'] = f'{profit:>.5f}'
        logging.info(json.dumps(stat, indent=4))

    def _pricePrecision(self, price):
        if self.symbol == 'ETH-USDT':
            return f'{price:>.2f}'
        elif self.symbol == 'QTUM-USDT':
            return f'{price:>.3f}'
        else:
            return f'{price:>.5f}'

if __name__ == "__main__":
    apiKey = input("Input api key: ")
    secret = input("Input secret: ")
    ex = BitMax(apiKey, secret)
    symbol = input("Input coin symbol: ")
    # symbol = 'BTMX-USDT'
    if symbol.upper() not in ['ETH', 'ELF', 'BTMX']:
        logging.error(f'Invalid coin symbol: {symbol}')
    trader = GridTrader('1', ex, symbol.upper()+'-USDT', 5.1)
    count = 0
    trader.printStat()
    while True:
        trader.doPassiveTrade()
        trader.savePositions()
        count += 1
        if count % 10 == 0:
            trader.printStat()
        time.sleep(1)