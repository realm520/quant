"""Prometheus metrics collection and export.

Provides metrics instrumentation using prometheus-client for
monitoring system performance and trading activity.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from tri_arb.config.logging import get_logger
from tri_arb.config.settings import settings

logger = get_logger(__name__)

# Request metrics
requests_total = Counter(
    "tri_arb_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status"],
)

requests_duration = Histogram(
    "tri_arb_requests_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Trading metrics
opportunities_detected = Counter(
    "tri_arb_opportunities_detected_total",
    "Total number of arbitrage opportunities detected",
    ["path"],
)

opportunities_viable = Counter(
    "tri_arb_opportunities_viable_total",
    "Total number of viable arbitrage opportunities",
    ["path"],
)

orders_placed = Counter(
    "tri_arb_orders_placed_total",
    "Total number of orders placed",
    ["exchange", "side", "status"],
)

orders_filled = Counter(
    "tri_arb_orders_filled_total",
    "Total number of orders filled",
    ["exchange", "side"],
)

trades_executed = Counter(
    "tri_arb_trades_executed_total",
    "Total number of trades executed",
    ["exchange", "pair"],
)

trades_volume = Histogram(
    "tri_arb_trades_volume",
    "Trade volume distribution",
    ["exchange", "pair"],
    buckets=(10, 100, 1000, 10000, 100000, 1000000),
)

# Profit metrics
profit_realized = Counter(
    "tri_arb_profit_realized_total",
    "Total realized profit",
    ["currency"],
)

profit_unrealized = Gauge(
    "tri_arb_profit_unrealized",
    "Current unrealized profit",
    ["currency"],
)

# Position metrics
active_positions = Gauge(
    "tri_arb_active_positions",
    "Number of active positions",
    ["exchange", "pair"],
)

position_exposure = Gauge(
    "tri_arb_position_exposure",
    "Total position exposure",
    ["exchange", "currency"],
)

# Error metrics
errors_total = Counter(
    "tri_arb_errors_total",
    "Total number of errors",
    ["type", "component"],
)

exchange_errors = Counter(
    "tri_arb_exchange_errors_total",
    "Total number of exchange errors",
    ["exchange", "error_type"],
)

# System metrics
cache_hits = Counter(
    "tri_arb_cache_hits_total",
    "Total number of cache hits",
    ["cache_type"],
)

cache_misses = Counter(
    "tri_arb_cache_misses_total",
    "Total number of cache misses",
    ["cache_type"],
)

database_queries = Counter(
    "tri_arb_database_queries_total",
    "Total number of database queries",
    ["operation"],
)

database_query_duration = Histogram(
    "tri_arb_database_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Exchange metrics
exchange_latency = Histogram(
    "tri_arb_exchange_latency_seconds",
    "Exchange API latency in seconds",
    ["exchange", "endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

exchange_rate_limits = Gauge(
    "tri_arb_exchange_rate_limits_remaining",
    "Remaining rate limit quota",
    ["exchange"],
)


class MetricsServer:
    """Prometheus metrics HTTP server.

    Starts HTTP server to expose metrics for Prometheus scraping.
    """

    def __init__(self, port: int = settings.metrics_port) -> None:
        """Initialize metrics server.

        Args:
            port: Port to listen on for metrics requests
        """
        self.port = port
        self._server_started = False
        logger.info("MetricsServer initialized", port=port)

    def start(self) -> None:
        """Start the metrics HTTP server.

        Starts Prometheus metrics server on configured port.
        """
        if self._server_started:
            logger.warning("Metrics server already started")
            return

        if not settings.enable_metrics:
            logger.info("Metrics disabled in configuration")
            return

        try:
            start_http_server(self.port)
            self._server_started = True
            logger.info("Metrics server started", port=self.port)
        except Exception as e:
            logger.error("Failed to start metrics server", error=str(e))
            raise

    def is_running(self) -> bool:
        """Check if metrics server is running.

        Returns:
            True if server is started, False otherwise
        """
        return self._server_started


# Global metrics server instance
metrics_server = MetricsServer()


# Helper functions for common metric operations


def record_request(method: str, endpoint: str, status: int, duration: float) -> None:
    """Record API request metrics.

    Args:
        method: HTTP method
        endpoint: API endpoint
        status: HTTP status code
        duration: Request duration in seconds
    """
    requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    requests_duration.labels(method=method, endpoint=endpoint).observe(duration)


def record_opportunity(path: str, viable: bool) -> None:
    """Record arbitrage opportunity detection.

    Args:
        path: Arbitrage path
        viable: Whether opportunity is viable for execution
    """
    opportunities_detected.labels(path=path).inc()
    if viable:
        opportunities_viable.labels(path=path).inc()


def record_order(exchange: str, side: str, status: str) -> None:
    """Record order placement.

    Args:
        exchange: Exchange name
        side: Order side (buy/sell)
        status: Order status
    """
    orders_placed.labels(exchange=exchange, side=side, status=status).inc()
    if status == "filled":
        orders_filled.labels(exchange=exchange, side=side).inc()


def record_error(error_type: str, component: str) -> None:
    """Record error occurrence.

    Args:
        error_type: Type of error
        component: Component where error occurred
    """
    errors_total.labels(type=error_type, component=component).inc()
