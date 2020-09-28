import json
import time
import copy
import logging
import logging.handlers
import prettytable as pt
from decimal import Decimal
from queue import Queue
from btmx import BitMax
from models import BtmxCompletedPosition, BtmxOrderHistory, BtmxGridConfig
from models import BtmxGridTable, Session
from btmx_ws import BtmxWsThread


for name in logging.Logger.manager.loggerDict.keys():
    logger = logging.getLogger(name)
    # print(f'name = {name}, logger = {logger}')
    logger.setLevel(logging.WARNING)
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s',
                    datefmt='%Y-%m-%d  %H:%M:%S %a'
                    )
fhDebug = logging.handlers.TimedRotatingFileHandler('grid-trade.debug.log', when="H", interval=1, backupCount=24)
formatter = logging.Formatter("%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s")
fhDebug.setFormatter(formatter)
fhDebug.setLevel(logging.DEBUG)
logger = logging.getLogger()
logger.addHandler(fhDebug)


class GridTrader(object):
    def __init__(self, sid, ex, symbol, db):
        self.sid = sid
        # self.stateFile = f'./grid_trade_{symbol}_{sid}.json'
        self.ex = ex
        self.symbol = symbol
        self.stopPrice = Decimal(0)
        self.openedPositions = []
        self.fee = 0.001
        self.lastTick = None
        self.db = db
        self.count = 0
        config = self.db.query(BtmxGridConfig).filter_by(symbol=self.symbol).first()
        if config is None:
            logging.exception(f"Fail to load configuration.")
            raise Exception(f"Cannot start grid trader for {self.symbol}")
        else:
            self.stopPrice = Decimal(config.upperLimit)
            self.amount = Decimal(config.baseAmount)
        self.refreshOpenPositions()
        self.checkOrderStatus()

    def refreshOpenPositions(self):
        self.openedPositions = self.db.query(BtmxGridTable)\
            .filter_by(symbol=self.symbol.replace('-', '/'))\
            .order_by(BtmxGridTable.pid).all()

    def save2Db(self, position):
        logging.info(f"Save position: {json.dumps(position)}")
        resp = self.ex.getOrderStatus(position['closeOrderId'])
        if resp['code'] != 0:
            logging.error(f"Fail to get order status: {resp}")
        o = resp['data']
        profit = Decimal(o['filledQty']) * Decimal(o['avgPrice']) - Decimal(o['fee'])
        self.db.query(BtmxOrderHistory).filter_by(coid=o['coid']).delete()
        self.db.add(BtmxOrderHistory(
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
        self.db.query(BtmxOrderHistory).filter_by(coid=o['coid']).delete()
        self.db.add(BtmxOrderHistory(
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
        self.db.query(BtmxCompletedPosition).filter_by(openOrderId=position['placeOrderId']).delete()
        self.db.add(BtmxCompletedPosition(
            symbol=position['symbol'], 
            openOrderId=position['placeOrderId'], 
            closeOrderId=position['closeOrderId'],
            profit=f"{profit:.8f}"))
        self.db.commit()

    def checkLastOrder(self):
        if len(self.openPositions) == 0:
            return
        order = self.openedPositions[-1]
        if order.status == 1:
            logging.info(f"Remove order in status 1: {order}")
            self.db.query(BtmxGridTable).filter_by(pid=order.pid).delete()
            self.refreshOpenPositions()
        elif order.status == 2:
            res = self.ex.getOrderStatus(order.openCoid)
            if res is not None and res['code'] == 0:
                if res['data']['status'] == 'Filled':
                    logging.info('buy order filled, place sell order')
                    order.status = 3  # order is Filled
                    closePrice = Decimal(order.price) * Decimal(1.01 + self.fee * 2)
                    closePrice = self._pricePrecision(closePrice)
                    res = self.ex.placeNewOrder(self.symbol, closePrice, order.volume, 'sell')
                    if res is not None and res['data']['action'] == 'new':
                        order.closeCoid = res['data']['coid']
                        order.status = 4  # place close order
                        order.closedPrice = closePrice
                elif res['data']['status'] == 'Canceled':
                    self.db.query(BtmxGridTable).filter_by(pid=order.pid).delete()
                    self.refreshOpenPositions()
                elif res['data']['status'] == 'New':
                    if (Decimal(self.lastTick['bidPrice']) - Decimal(res['data']['orderPrice'])) / Decimal(res['data']['orderPrice']) > Decimal(0.02):
                        self.ex.cancelOrder(order.placeOrderId, order['symbol'])
        self.db.commit()

    def checkOrderStatus(self):
        needRecheck = False
        removedPositions = []
        for p in self.openedPositions:
            logging.debug(p['status'])
            if p['status'] == 1:
                logging.info(f"Need to place open order...{p['price']}")
                continue
            elif p['status'] == 2:
                res = self.ex.getOrderStatus(p['placeOrderId'])
                if res is not None and res['code'] == 0:
                    if res['data']['status'] == 'Filled':
                        logging.info('buy order filled, place sell order')
                        p['status'] = 3  # order is Filled
                        closePrice = Decimal(p['price']) * Decimal(1.01 + self.fee * 2)
                        closePrice = self._pricePrecision(closePrice)
                        res = self.ex.placeNewOrder(self.symbol, closePrice, p['volume'], 'sell')
                        if res is not None and res['data']['action'] == 'new':
                            p['closeOrderId'] = res['data']['coid']
                            p['status'] = 4  # place close order
                            p['closedPrice'] = closePrice
                    elif res['data']['status'] == 'Canceled':
                        removedPositions.append(p)
            elif p['status'] == 3:
                logging.info("Need to place close order...")
            elif p['status'] == 4:
                res = self.ex.getOrderStatus(p['closeOrderId'])
                logging.debug(f"closing order status: {res}")
                if res is not None and res['code'] == 0:
                    if res['data']['status'] == 'Filled':
                        p['status'] = 5
                        p['avgClosedPrice'] = res['data']['avgPrice']
                        self.save2Db(p)
                        removedPositions.append(p)
                    elif res['data']['status'] == 'Canceled':
                        p['status'] = 2
                        needRecheck = True
        for p in removedPositions:
            self.openedPositions.remove(p)
        if needRecheck:
            self.checkOrderStatus()
            self.savePositions()

    def updateOrder(self, order):
        logging.debug(f"order updated: {order}")
        #logging.debug(self.symbol.replace('-', '/'))
        if self.symbol.replace('-', '/') != order['s']:
            return False
        for p in self.openedPositions:
            if p['placeOrderId'] == order['coid']:
                logging.debug(p['placeOrderId'])
                if p['status'] == 2 and order['status'] == 'Filled':
                    logging.debug('buy order filled, place sell order')
                    p['status'] = 3  # order is Filled
                    closePrice = Decimal(p['price']) * Decimal(1.01 + self.fee * 2)
                    closePrice = self._pricePrecision(closePrice)
                    res = self.ex.placeNewOrder(
                            self.symbol, closePrice, p['volume'], 'sell')
                    if res is not None and res['data']['action'] == 'new':
                        p['closeOrderId'] = res['data']['coid']
                        p['status'] = 4  # place close order
                        p['closedPrice'] = closePrice
                elif p['status'] == 2 and order['status'] == 'Canceled':
                    self.openedPositions.remove(p)
            elif p['closeOrderId'] == order['coid']:
                if p['status'] == 4 and order['status'] == 'Filled':
                    p['status'] = 5
                    p['avgClosedPrice'] = order['ap']
                    self.save2Db(p)
                    self.openedPositions.remove(p)
        return True

    def doPassiveTrade(self, orderBook):
        if orderBook['symbol'] != self.symbol:
            return False
        self.lastTick = copy.deepcopy(orderBook)
        logging.debug(f'Tick: {json.dumps(orderBook)}')
        if len(self.openedPositions) == 0:
            self.openPosition(orderBook)

        # process lower grid
        if len(self.openedPositions) >= 1:
            lowPrice = Decimal(self.openedPositions[-1]['price'])
            currentPrice = Decimal(orderBook['askPrice'])
            if self.openedPositions[-1]['status'] >= 3 \
                and lowPrice * Decimal(0.99 - self.fee) > currentPrice:
                if len(self.openedPositions) < 80:
                    self.openPosition(orderBook)
                else:
                    logging.info("More than 80 positions opened, pending...")
            elif self.openedPositions[-1]['status'] >= 3:
                pass
        if self.count % 60 == 0 and self.count > 0:
            self.checkLastOrder()
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
            'status': 1,  # prepare to open position
            'closedPrice': openPrice * Decimal(1.01 + self.fee * 2),
            'placeOrderId': '',
            'closeOrderId': ''
        }
        res = self.ex.placeNewOrder(
                self.symbol, p['price'], p['volume'], 'buy')
        if res is not None and res['code'] == 0 and \
                res['data']['action'] == 'new':
            p['placeOrderId'] = res['data']['coid']
            p['status'] = 2  # order is new
            newPosition = BtmxGridTable(
                symbol=self.symbol.replace('-', '/'),
                openCoid=res['data']['coid'],
                openPrice=self._pricePrecision(openPrice),
                volume=f"{volume:>.3f}",
                closePrice=openPrice * Decimal(1.01 + self.fee * 2),
                status=2
            )
            self.db.add(newPosition)
            self.db.flush()
            self.openedPositions.append(newPosition)
            return True
        else:
            logging.warning(f"Place open order failure: {res}")
            return False

    def savePositions(self):
        with open(self.stateFile, 'w') as fp:
            data = {'openedPositions': self.openedPositions, 'positionAmount': f"{self.amount:.5f}", 'stopPrice': f'{self.stopPrice:.5f}'}
            json.dump(data, fp)

    def printStat(self):
        closedPosition = self.db.query(BtmxCompletedPosition).filter_by(symbol=self.symbol.replace('-', '/')).all()
        stat = {'TotalOpenPositions': len(self.openedPositions), 'TotalClosePositions': len(closedPosition)}
        lowPrice = Decimal(self.openedPositions[-1]['price']) * Decimal(0.99 - self.fee) if len(self.openedPositions) > 0 else Decimal("0.001")
        stat['nextOpenPrice'] = f'{lowPrice:>.5f}'
        tb = pt.PrettyTable(["Price", "Symbol", "Volume", "PlaceOrderId", "ClosedPrice", "CloseOrderId", "Status"])
        cost = Decimal(0)
        fLoss = Decimal(0)
        for p in self.openedPositions:
            tb.add_row([p['price'], p['symbol'], p['volume'], p['placeOrderId'], p['closedPrice'], p['closeOrderId'], p['status']])
            cost += Decimal(p['price']) * Decimal(p['volume'])
            fLoss += (Decimal(self.lastTick['bidPrice']) - Decimal(p['price'])) * Decimal(p['volume'])
        print(tb)
        profit = Decimal(0)
        for p in closedPosition:
            profit += Decimal(p.profit)
        stat['Profit'] = f'{profit:>.5f}'
        stat['Cost'] = f'{cost:>.5f}'
        stat['FloatingLoss'] = f'{fLoss:>.5f}'
        stat['lastTickTime'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.lastTick['recvTime']))
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
    #symbols = ['BTMX-USDT', 'ETH-USDT', 'ELF-USDT', 'BCH-USDT', 'QTUM-USDT']
    symbols = ['ONT-USDT']
    db = Session()
    q = Queue()
    traders = [GridTrader('1', ex, s, db) for s in symbols]
    threads = [BtmxWsThread(apiKey, secret, s, ex.account_group, q) for s in symbols]
    [t.start() for t in threads]
    count = 0
    while True:
        data = q.get()
        for i, t in enumerate(traders):
            if 'm' in data:
                if data['m'] == "order":
                    if t.updateOrder(data):
                        break
                elif data['m'] == "threadStop":
                    if threads[i].symbol == data['s']:
                        logging.warning(f"thread stop, restart... {symbols[i]}")
                        threads[i].join()
                        threads[i] = BtmxWsThread(apiKey, secret, symbols[i], ex.account_group, q)
                        threads[i].start()
                        logging.warning(f"new thread started")
            else:
                if t.doPassiveTrade(data):
                    break
        t.savePositions()
    count += 1
    # time.sleep(1)

