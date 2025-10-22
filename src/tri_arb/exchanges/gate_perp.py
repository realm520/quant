"""Gate.io Perpetual Futures Exchange Adapter.

Gate.io永续合约交易所适配器，实现统一的交易接口。

API文档: https://www.gate.io/docs/developers/apiv4/zh_CN/
WebSocket文档: https://www.gate.io/docs/developers/websocket/zh_CN/
"""

import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from tri_arb.config.logging import get_logger
from tri_arb.exchanges.base import BaseExchange

logger = get_logger(__name__)


class GatePerpExchange(BaseExchange):
    """Gate.io永续合约交易所适配器.
    
    实现Gate.io永续合约的REST API调用，包括账户查询、下单等功能。
    """
    
    def __init__(
        self,
        name: str = "gate_perp",
        api_key: str | None = None,
        api_secret: str | None = None,
        base_url: str = "https://api.gateio.ws",
    ):
        """初始化Gate.io永续合约适配器.
        
        Args:
            name: 交易所名称标识
            api_key: Gate.io API密钥
            api_secret: Gate.io API密钥
            base_url: API基础URL（不含/api/v4）
        """
        super().__init__(name)
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.client: Optional[httpx.AsyncClient] = None
        
        logger.info("GatePerpExchange initialized", name=name, base_url=base_url)
    def get_name(self) -> str:
        return "gate_perp"
    
    async def connect(self):
        """建立HTTP连接."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_keepalive_connections=5),
            )
            logger.debug("HTTP client created for Gate.io")
    
    async def disconnect(self):
        """关闭HTTP连接."""
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.debug("HTTP client closed for Gate.io")
    
    def _generate_signature(
        self,
        method: str,
        url_path: str,
        query_string: str = "",
        body_string: str = "",
    ) -> tuple[str, str]:
        """生成Gate.io API签名.
        
        Gate.io签名格式（V4）：
        SIGN = HEX(HMAC_SHA512(secret, payload))
        payload = METHOD\nRESOURCE\nQUERY_STRING\nHASHED_BODY\nTIMESTAMP
        
        Args:
            method: HTTP方法 (GET/POST/DELETE)
            url_path: URL路径 (如 /api/v4/futures/usdt/accounts)
            query_string: 查询字符串 (如 contract=BTC_USDT)
            body_string: 请求体字符串（JSON）
            
        Returns:
            (timestamp, signature) 元组
        """
        timestamp = str(int(time.time()))
        
        # 计算body的SHA512哈希（十六进制小写）
        # 注意：如果body为空，仍需计算空字符串的哈希
        body_hash = hashlib.sha512(body_string.encode('utf-8')).hexdigest()
        
        # 构造待签名字符串（每部分用\n分隔）
        # 格式: METHOD\nRESOURCE\nQUERY_STRING\nHASHED_BODY\nTIMESTAMP
        # 注意：即使query_string为空，也要保留这个位置
        payload = f"{method}\n{url_path}\n{query_string}\n{body_hash}\n{timestamp}"
        
        # HMAC SHA-512签名（十六进制小写）
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()
        
        logger.debug("Gate signature details", 
                    method=method,
                    path=url_path,
                    query=query_string or "(empty)",
                    body=body_string[:50] if body_string else "(empty)",
                    body_hash=body_hash[:40] + "...",
                    timestamp=timestamp,
                    payload_preview=payload.replace('\n', '\\n')[:100],
                    signature=signature[:40] + "...")
        
        return timestamp, signature
    
    async def _request(
        self,
        method: str,
        path: str,
        params: Dict[str, Any] | None = None,
        data: Dict[str, Any] | None = None,
        authenticated: bool = False,
    ) -> httpx.Response:
        """发送HTTP请求到Gate.io API.
        
        Args:
            method: HTTP方法
            path: API路径
            params: URL参数
            data: 请求体数据
            authenticated: 是否需要认证
            
        Returns:
            HTTP响应
        """
        await self.connect()
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # 构造查询字符串
        query_string = ""
        if params:
            query_parts = [f"{k}={v}" for k, v in sorted(params.items())]
            query_string = "&".join(query_parts)
        
        # 构造请求体
        import json
        body_string = json.dumps(data) if data else ""
        
        # 添加认证头
        if authenticated:
            if not self.api_key or not self.api_secret:
                raise ValueError("API credentials required for authenticated requests")
            
            timestamp, signature = self._generate_signature(
                method=method.upper(),
                url_path=path,
                query_string=query_string,
                body_string=body_string,
            )
            
            headers.update({
                "KEY": self.api_key,
                "Timestamp": timestamp,
                "SIGN": signature,
            })
        
        # 发送请求
        full_url = f"{path}?{query_string}" if query_string else path
        
        logger.debug("Gate API request",
                    method=method,
                    url=full_url,
                    authenticated=authenticated,
                    headers={k: v[:20] + "..." if len(v) > 20 else v for k, v in headers.items()})
        
        if method.upper() == "GET":
            response = await self.client.get(full_url, headers=headers)
        elif method.upper() == "POST":
            response = await self.client.post(full_url, headers=headers, content=body_string)
        elif method.upper() == "DELETE":
            response = await self.client.delete(full_url, headers=headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        logger.debug("Gate API response",
                    status=response.status_code,
                    path=path,
                    response_text=response.text[:200] if response.status_code != 200 else "OK")
        
        if response.status_code != 200:
            logger.error("Gate API error",
                        status=response.status_code,
                        response=response.text)
        
        response.raise_for_status()
        return response
    
    async def get_balance(self) -> Dict[str, Decimal]:
        """查询账户余额.
        
        Returns:
            币种余额字典，如 {"USDT": Decimal("10000.00")}
        """
        response = await self._request(
            method="GET",
            path="/api/v4/futures/usdt/accounts",
            authenticated=True,
        )
        
        data = response.json()
        
        # Gate.io返回账户总览
        balances = {}
        if isinstance(data, dict):
            # 总权益
            total = data.get("total", "0")
            # 可用余额
            available = data.get("available", "0")
            
            balances["USDT"] = {
                "total": Decimal(total),
                "available": Decimal(available),
                "unrealised_pnl": Decimal(data.get("unrealised_pnl", "0")),
            }
        
        logger.info("Gate balance retrieved", currencies=list(balances.keys()))
        return balances
    
    async def get_positions(self, symbol: str | None = None) -> List[Dict]:
        """查询持仓.
        
        Args:
            symbol: 交易对，如"BTC/USDT"，None表示查询所有
            
        Returns:
            持仓列表
        """
        # Gate.io合约格式: BTC_USDT
        params = {}
        if symbol:
            contract = symbol.replace("/", "_").replace("-", "_").upper()
            params["contract"] = contract
        
        response = await self._request(
            method="GET",
            path="/api/v4/futures/usdt/positions",
            params=params,
            authenticated=True,
        )
        
        positions = response.json()
        
        # 转换字段为Decimal
        result = []
        for pos in positions:
            if Decimal(pos.get("size", "0")) == 0:
                continue  # 跳过零持仓
            
            result.append({
                "contract": pos.get("contract"),
                "size": Decimal(pos.get("size", "0")),
                "leverage": Decimal(pos.get("leverage", "0")),
                "margin": Decimal(pos.get("margin", "0")),
                "entry_price": Decimal(pos.get("entry_price", "0")),
                "mark_price": Decimal(pos.get("mark_price", "0")),
                "liq_price": Decimal(pos.get("liq_price", "0")),
                "unrealised_pnl": Decimal(pos.get("unrealised_pnl", "0")),
                "realised_pnl": Decimal(pos.get("realised_pnl", "0")),
                "mode": pos.get("mode"),  # single/dual
            })
        
        logger.info("Gate positions retrieved", count=len(result))
        return result
    
    async def get_open_orders(self, symbol: str | None = None) -> List[Dict]:
        """查询挂单.
        
        Args:
            symbol: 交易对，如"BTC/USDT"，None表示查询所有
            
        Returns:
            挂单列表
        """
        params = {"status": "open"}
        
        if symbol:
            contract = symbol.replace("/", "_").replace("-", "_").upper()
            params["contract"] = contract
        
        response = await self._request(
            method="GET",
            path="/api/v4/futures/usdt/orders",
            params=params,
            authenticated=True,
        )
        
        orders = response.json()
        
        # 转换字段
        result = []
        for order in orders:
            # Gate.io使用size的正负表示方向
            size_value = int(order.get("size", 0))
            side = "buy" if size_value > 0 else "sell"
            
            result.append({
                "id": str(order.get("id", "")),
                "contract": order.get("contract"),
                "size": Decimal(str(abs(size_value))),  # 转为正数
                "price": Decimal(order.get("price", "0")),
                "left": Decimal(str(abs(int(order.get("left", 0))))),
                "filled_total": Decimal(order.get("fill_price", "0")),
                "status": order.get("status"),
                "side": side,  # buy/sell
                "create_time": order.get("create_time"),
                "finish_time": order.get("finish_time"),
                "reduce_only": order.get("reduce_only", False),
                "tif": order.get("tif"),
            })
        
        logger.info("Gate open orders retrieved", count=len(result))
        return result
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Decimal | None = None,
        **kwargs
    ) -> Dict:
        """下单.
        
        Args:
            symbol: 交易对，如"BTC/USDT"
            side: 买卖方向 (buy/sell)
            order_type: 订单类型 (limit/market)
            quantity: 数量
            price: 价格（市价单可为None）
            **kwargs: 其他参数（reduce_only, position_side等）
            
        Returns:
            订单信息
        """
        # Gate.io合约格式: BTC_USDT
        contract = symbol.replace("/", "_").replace("-", "_").upper()
        
        # 构造订单数据
        order_data = {
            "contract": contract,
            "size": int(quantity) if side.lower() == "buy" else -int(quantity),
            "price": str(price) if price else "0",
            "tif": "gtc",  # good till cancelled
        }
        
        # 处理reduce_only
        if kwargs.get("reduce_only"):
            order_data["reduce_only"] = True
        
        # 处理仓位模式
        if kwargs.get("position_side"):
            # Gate.io使用size的正负表示方向
            pass
        
        response = await self._request(
            method="POST",
            path="/api/v4/futures/usdt/orders",
            data=order_data,
            authenticated=True,
        )
        
        order_info = response.json()
        
        logger.info("Gate order placed",
                   contract=contract,
                   size=order_data["size"],
                   price=order_data["price"])
        
        return order_info
    
    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """取消订单.
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            是否成功
        """
        contract = symbol.replace("/", "_").replace("-", "_").upper()
        
        response = await self._request(
            method="DELETE",
            path=f"/api/v4/futures/usdt/orders/{order_id}",
            authenticated=True,
        )
        
        logger.info("Gate order canceled", order_id=order_id, contract=contract)
        return True
    
    async def get_order_status(self, symbol: str, order_id: str) -> Dict:
        """查询订单状态.
        
        Args:
            symbol: 交易对
            order_id: 订单ID
            
        Returns:
            订单信息
        """
        response = await self._request(
            method="GET",
            path=f"/api/v4/futures/usdt/orders/{order_id}",
            authenticated=True,
        )
        
        return response.json()
    
    async def get_ticker(self, symbol: str) -> Dict:
        """获取行情ticker.
        
        Args:
            symbol: 交易对
            
        Returns:
            ticker信息
        """
        contract = symbol.replace("/", "_").replace("-", "_").upper()
        
        response = await self._request(
            method="GET",
            path=f"/api/v4/futures/usdt/tickers",
            params={"contract": contract},
            authenticated=False,
        )
        
        tickers = response.json()
        return tickers[0] if tickers else {}
    
    async def get_orderbook(self, symbol: str, limit: int = 20) -> Dict:
        """获取订单簿.
        
        Args:
            symbol: 交易对
            limit: 深度限制
            
        Returns:
            订单簿数据
        """
        contract = symbol.replace("/", "_").replace("-", "_").upper()
        
        response = await self._request(
            method="GET",
            path=f"/api/v4/futures/usdt/order_book",
            params={"contract": contract, "limit": limit},
            authenticated=False,
        )
        
        return response.json()
    
    async def get_trade_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """获取成交历史.
        
        Args:
            symbol: 交易对
            limit: 数量限制
            
        Returns:
            成交历史列表
        """
        contract = symbol.replace("/", "_").replace("-", "_").upper()
        
        response = await self._request(
            method="GET",
            path="/api/v4/futures/usdt/my_trades",
            params={"contract": contract, "limit": limit},
            authenticated=True,
        )
        
        return response.json()
    
    async def get_trading_pair_info(self, symbol: str) -> Dict:
        """获取交易对信息.
        
        Args:
            symbol: 交易对
            
        Returns:
            交易对信息
        """
        contract = symbol.replace("/", "_").replace("-", "_").upper()
        
        response = await self._request(
            method="GET",
            path=f"/api/v4/futures/usdt/contracts/{contract}",
            authenticated=False,
        )
        
        return response.json()
    
    async def subscribe_ticker(self, symbol: str):
        """订阅ticker（WebSocket，占位符）."""
        raise NotImplementedError("Gate.io WebSocket ticker subscription not implemented")
    
    async def subscribe_orderbook(self, symbol: str):
        """订阅订单簿（WebSocket，占位符）."""
        raise NotImplementedError("Gate.io WebSocket orderbook subscription not implemented")

