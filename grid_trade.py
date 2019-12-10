import json
import time
import logging
import logging.handlers
import prettytable as pt
from decimal import Decimal
from queue import Queue
from btmx import BitMax
from models import BtmxCompletedPosition, BtmxTradeHistory, Session
from btmx_ws import BtmxWsThread


for name in logging.Logger.manager.loggerDict.keys():
    logger = logging.getLogger(name)
    # print(f'name = {name}, logger = {logger}')
    logger.setLevel(logging.WARNING)
logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s",
                    datefmt = '%Y-%m-%d  %H:%M:%S %a'
                    )
fhDebug = logging.handlers.TimedRotatingFileHandler('grid-trade.debug.log', when="H", interval=1, backupCount=24)
formatter = logging.Formatter("%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s")
fhDebug.setFormatter(formatter)
# fhDebug.setLevel(logging.DEBUG)
logger = logging.getLogger()
logger.addHandler(fhDebug)


class GridTrader(object):
    def __init__(self, sid, ex, symbol, amount, db):
        self.sid = sid
        self.stateFile = f'./grid_trade_{symbol}_{sid}.json'
        self.ex = ex
        self.symbol = symbol
        self.amount = amount
        self.stopPrice = Decimal(0)
        self.totalUsdt = 100
        self.openedPositions = []
        self.fee = 0.001
        self.lastPrice = Decimal(0)
        self.db = db
        self.count = 0
        try:
            with open(self.stateFile, 'r') as fp:
                state = json.load(fp)
                if 'openedPositions' in state:
                    self.openedPositions = state['openedPositions']
                if 'stopPrice' in state:
                    self.stopPrice = Decimal(state['stopPrice'])
        except Exception as e:
            pass

    def save2Db(self, position):
        logging.info(f"Save position: {json.dumps(position)}")
        resp = self.ex.getOrderStatus(position['closeOrderId'])
        if resp['code'] != 0:
            logging.error(f"Fail to get order status: {resp['code']}")
        o = resp['data']
        profit = Decimal(o['filledQty']) * Decimal(o['avgPrice']) - Decimal(o['fee'])
        db.add(BtmxTradeHistory(
            coid=o['coid'],
            accountCategory=o['accountCategory'],
            accountId=o['accountId'],
            avgPrice=o['avgPrice'],
            baseAsset=o['baseAsset'],
            quoteAsset=o['quoteAsset'],
            btmxCommission=o['btmxCommission'],
            execId=o['execId'],
            fee=o['fee'],
            feeAsset=o['feeAsset'],
            filledQty=o['filledQty'],
            notional=o['notional'],
            orderPrice=o['orderPrice'],
            orderQty=o['orderQty'],
            orderType=o['orderType'],
            sendingTime=o['sendingTime'],
            side=o['side'],
            status=o['status'],
            symbol=o['symbol'],
            time=o['time'],
            userId=o['userId']
        ))
        resp = self.ex.getOrderStatus(position['placeOrderId'])
        if resp['code'] != 0:
            logging.error(f"Fail to get order status: {resp['code']}")
        o = resp['data']
        profit -= Decimal(o['filledQty']) * Decimal(o['avgPrice']) + Decimal(o['fee'])
        db.add(BtmxTradeHistory(
            coid=o['coid'],
            accountCategory=o['accountCategory'],
            accountId=o['accountId'],
            avgPrice=o['avgPrice'],
            baseAsset=o['baseAsset'],
            quoteAsset=o['quoteAsset'],
            btmxCommission=o['btmxCommission'],
            execId=o['execId'],
            fee=o['fee'],
            feeAsset=o['feeAsset'],
            filledQty=o['filledQty'],
            notional=o['notional'],
            orderPrice=o['orderPrice'],
            orderQty=o['orderQty'],
            orderType=o['orderType'],
            sendingTime=o['sendingTime'],
            side=o['side'],
            status=o['status'],
            symbol=o['symbol'],
            time=o['time'],
            userId=o['userId']
        ))
        db.add(BtmxCompletedPosition(
            symbol=position['symbol'], 
            openOrderId=position['placeOrderId'], 
            closeOrderId=position['closeOrderId'],
            profit=f"{profit:.8f}"))
        db.commit()

    def updateOrder(self, order):
        for p in self.openedPositions:
            if p['status'] == 4 and p['closeOrderId'] == order['coid'] and order['status'] == 'Filled':
                p['status'] = 5
                p['avgClosedPrice'] = order['ap']
                self.save2Db(p)
                self.openedPositions.remove(p)
                return True
        return False

    def doPassiveTrade(self, orderBook):
        if orderBook['symbol'] != self.symbol:
            return False
        # orderBook = self.ex.level1OrderBook(self.symbol)
        # if orderBook is None:
        #     return
        self.lastPrice = orderBook['bidPrice']
        logging.info(f'Tick: {json.dumps(orderBook)}')
        if len(self.openedPositions) == 0:
            self.openPosition(orderBook)
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
                        elif res['data']['status'] == 'Canceled':
                            self.openedPositions.remove(p)
                elif p['status'] == 3:
                    logging.info("Need to place close order...")
            # process lower grid
            if len(self.openedPositions) >= 1:
                lowPrice = Decimal(self.openedPositions[-1]['price'])
                currentPrice = Decimal(orderBook['askPrice'])
                if self.openedPositions[-1]['status'] >= 3 \
                    and lowPrice * Decimal(0.99 - self.fee) > currentPrice:
                    if len(self.openedPositions) < 40:
                        self.openPosition(orderBook)
                    else:
                        logging.info("More than 40 positions opened, pending...")
        if self.count % 60 == 0:
            self.printStat()
        self.count += 1
        return True

    def openPosition(self, orderBook):
        openPrice = Decimal(orderBook['askPrice'])
        if self.stopPrice > Decimal(0) and self.stopPrice < openPrice:
            logging.info(f'Over the price limit: {self.stopPrice} / {openPrice}')
            return
        gap = (openPrice - Decimal(orderBook['bidPrice'])) / openPrice
        if gap > Decimal(0.005):
            return False
        amplify = Decimal(1) + Decimal(0.2) * Decimal(int(len(self.openedPositions) / 20))
        volume = Decimal(self.amount) * amplify / openPrice
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
            data = {'openedPositions': self.openedPositions, 'stopPrice': f'{self.stopPrice:.5f}'}
            json.dump(data, fp)

    def printStat(self):
        closedPosition = self.db.query(BtmxCompletedPosition).filter_by(symbol=self.symbol.replace('-', '/'))
        stat = {'TotalOpenPositions': len(self.openedPositions), 'TotalClosePositions': 0}
        lowPrice = Decimal(self.openedPositions[-1]['price']) * Decimal(0.99 - self.fee) if len(self.openedPositions) > 0 else Decimal("0.001")
        stat['nextOpenPrice'] = f'{lowPrice:>.5f}'
        tb = pt.PrettyTable( ["Price", "Symbol", "Volume", "PlaceOrderId", "ClosedPrice", "CloseOrderId", "Status"])
        cost = Decimal(0)
        fLoss = Decimal(0)
        for p in self.openedPositions:
            tb.add_row([p['price'], p['symbol'], p['volume'], p['placeOrderId'], p['closedPrice'], p['closeOrderId'], p['status']])
            cost += Decimal(p['price']) * Decimal(p['volume'])
            fLoss += (Decimal(self.lastPrice) - Decimal(p['price'])) * Decimal(p['volume'])
        print(tb)
        profit = Decimal(0)
        for p in closedPosition:
            profit += Decimal(p.profit)
        stat['Profit'] = f'{profit:>.5f}'
        stat['Cost'] = f'{cost:>.5f}'
        stat['FloatingLoss'] = f'{fLoss:>.5f}'
        logging.info(json.dumps(stat, indent=4))

    def _pricePrecision(self, price):
        if self.symbol in ['ETH-USDT', 'BCH-USDT']:
            return f'{price:>.2f}'
        elif self.symbol == 'QTUM-USDT':
            return f'{price:>.3f}'
        else:
            return f'{price:>.5f}'


if __name__ == "__main__":
    apiKey = input("Input api key: ")
    secret = input("Input secret: ")
    ex = BitMax(apiKey, secret)
    symbols = ['BTMX-USDT', 'ETH-USDT', 'ELF-USDT', 'BCH-USDT', 'QTUM-USDT']
    db = Session()
    q = Queue()
    traders = [GridTrader('1', ex, s, 5.1, db) for s in symbols]
    threads = [BtmxWsThread(apiKey, secret, s, ex.account_group, q) for s in symbols]
    [t.start() for t in threads]
    count = 0
    while True:
        data = q.get()
        for t in traders:
            if 'm' in data:
                if t.updateOrder(data):
                    break
            else:
                if t.doPassiveTrade(data):
                    break
            t.savePositions()
    count += 1
    # time.sleep(1)

