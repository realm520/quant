from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy import and_



Base = declarative_base()


class BtmxGridConfig(Base):
    __tablename__ = 'btmx_grid_config_table'
    cid = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(128), nullable=False)
    upperLimit = Column(String(128), nullable=False)
    baseAmount = Column(String(128), nullable=False)


class BtmxGridTable(Base):
    __tablename__ = 'btmx_grid_table'
    pid = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(128), nullable=False)
    openCoid = Column(String(32), index=True)
    openPrice = Column(String(128), nullable=False)
    closeCoid = Column(String(32), index=True, default="")
    closePrice = Column(String(128), nullable=False)
    volume = Column(String(128), nullable=False)
    status = Column(Integer, nullable=False)


class BtmxOrderHistory(Base):
    __tablename__ = 'btmx_order_history'
    coid = Column(String(32), primary_key=True)
    accountCategory = Column(String(128), default="")
    accountId = Column(String(128), default="")
    avgPrice = Column(String(128), default="")
    baseAsset = Column(String(128), default="")
    quoteAsset = Column(String(128), default="")
    btmxCommission = Column(String(128), default="")
    execId = Column(String(128), default="")
    fee = Column(String(128), default="")
    feeAsset = Column(String(128), default="")
    filledQty = Column(String(128), default="")
    notional = Column(String(128), default="")
    orderPrice = Column(String(128), default="")
    orderQty = Column(String(128), default="")
    orderType = Column(String(128), default="")
    sendingTime = Column(String(128), default="")
    side = Column(String(128), default="")
    status = Column(String(128), default="")
    symbol = Column(String(128), default="")
    time = Column(String(128), default="")
    userId = Column(String(128), default="")

    def __repr__(self):
        return f"<BtmxOrderHistory(coid='{self.coid}'>"


class BtmxCompletedPosition(Base):
    __tablename__ = 'btmx_completed_position'
    pid = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(128), nullable=False)
    openOrderId = Column(String(128), unique=True, nullable=False)
    closeOrderId = Column(String(128), unique=True, nullable=False)
    profit = Column(String(128), nullable=False)

    def __repr__(self):
        return f"<BtmxCompletedPosition(pid='{self.pid}'>"


engine = create_engine(
            'sqlite:///grid_trade.db',
            echo=True,
            poolclass=SingletonThreadPool,
            connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


if __name__ == '__main__':
    session = Session()
    session.add(BtmxOrderHistory(coid="12121212", baseAsset="BTMX"))
    session.add(BtmxCompletedPosition(
        symbol='BTMX-USDT',
        openOrderId="12121212",
        closeOrderId="12121212"))
    session.commit()
