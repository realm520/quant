"""
Arbitrage opportunity monitor.

Main class for scanning and monitoring triangular arbitrage opportunities.
Based on specs/004-xt-get-ticker/contracts/monitor_api.md.
"""

import asyncio
import signal
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from types import FrameType
from typing import Any, Protocol

import structlog

from tri_arb.arbitrage.amount_recommender import calculate_recommended_amount
from tri_arb.arbitrage.calculator import calculate_profit_rate
from tri_arb.arbitrage.config import MonitorConfig
from tri_arb.arbitrage.exceptions import NetworkError
from tri_arb.arbitrage.path_finder import find_arbitrage_paths
from tri_arb.models.arbitrage import ArbitrageOpportunity
from tri_arb.models.exchange import Ticker


class ExchangeProtocol(Protocol):
    """Protocol for exchange adapter interface."""

    async def get_ticker(
        self, symbol: str | None = None
    ) -> list[Ticker]: ...  # noqa: E704


logger = structlog.get_logger(__name__)


class ArbitrageMonitor:
    """
    Triangular arbitrage opportunity monitor.

    Scans markets for profitable arbitrage paths and reports opportunities.
    """

    def __init__(self, config: MonitorConfig, exchange_name: str):
        """
        Initialize arbitrage monitor.

        Args:
            config: Monitor configuration
            exchange_name: Name of exchange to monitor (e.g., "xt")
        """
        self.config = config
        self.exchange_name = exchange_name
        self._exchange: ExchangeProtocol | None = None
        self._shutdown_requested = False

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum: int, frame: FrameType | None) -> None:
        """Handle shutdown signals (SIGINT, SIGTERM)."""
        logger.info("shutdown_signal_received", signal=signum)
        self._shutdown_requested = True

    async def scan_once(self) -> list[ArbitrageOpportunity]:
        """
        Execute a single market scan for arbitrage opportunities.

        Returns:
            List of ArbitrageOpportunity sorted by profit rate (descending)

        Raises:
            NetworkError: If network request fails after retries

        Performance: < 1 second (NFR-001)
        """
        start_time = datetime.utcnow()

        logger.info("scan_started", mode="once")

        # Fetch all tickers
        tickers = await self._fetch_tickers()

        logger.info("tickers_fetched", count=len(tickers), exchange=self.exchange_name)

        # Filter invalid prices
        valid_tickers = self._filter_valid_tickers(tickers)

        if len(valid_tickers) < len(tickers):
            logger.warning(
                "invalid_tickers_filtered",
                total=len(tickers),
                valid=len(valid_tickers),
                invalid=len(tickers) - len(valid_tickers),
            )

        # Find arbitrage paths
        base_currencies = (
            self.config.base_currency_whitelist
            if self.config.base_currency_whitelist
            else None
        )

        paths = find_arbitrage_paths(
            tickers=valid_tickers, base_currencies=base_currencies
        )

        logger.info("paths_found", count=len(paths))

        # Calculate profit rates for all paths
        opportunities: list[ArbitrageOpportunity] = []
        ticker_dict = {t.symbol: t for t in valid_tickers}
        fee_rate = Decimal(
            str(self.config.fee_rate_per_trade / 100)
        )  # Convert % to decimal

        for path in paths:
            try:
                profit_rate, price_details = await calculate_profit_rate(
                    path=path, tickers=ticker_dict, fee_rate=fee_rate
                )

                # Filter by profit threshold
                if profit_rate >= Decimal(str(self.config.min_profit_threshold)):
                    # Calculate recommended amount based on liquidity and profit
                    recommended_amount = calculate_recommended_amount(
                        path=path,
                        tickers=ticker_dict,
                        profit_rate=profit_rate,
                        max_amount=Decimal(str(self.config.max_recommended_amount)),
                        min_amount=Decimal(str(self.config.min_recommended_amount)),
                        liquidity_usage_rate=Decimal(
                            str(self.config.liquidity_usage_rate)
                        ),
                    )

                    opportunity = ArbitrageOpportunity(
                        path=path,
                        expected_profit_rate=profit_rate,
                        prices=price_details,
                        recommended_amount=recommended_amount,
                        discovered_at=datetime.utcnow(),
                        status="new",
                    )
                    opportunities.append(opportunity)

            except (KeyError, ValueError) as e:
                logger.warning(
                    "path_calculation_failed", path=path.trading_pairs, error=str(e)
                )
                continue

        # Sort by profit rate descending
        opportunities.sort(key=lambda x: x.expected_profit_rate, reverse=True)

        duration = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            "scan_completed",
            opportunities_found=len(opportunities),
            duration_seconds=duration,
        )

        return opportunities

    async def scan_realtime(self) -> AsyncGenerator[list[ArbitrageOpportunity], None]:
        """
        Continuous scanning mode with periodic refresh.

        Yields:
            List of ArbitrageOpportunity for each scan iteration

        Raises:
            ValueError: If run_mode is not 'realtime'
            NetworkError: If network request fails after retries
        """
        if self.config.run_mode != "realtime":
            raise ValueError(
                f"scan_realtime requires run_mode='realtime', got: {self.config.run_mode}"
            )

        logger.info(
            "realtime_scan_started",
            refresh_interval=self.config.refresh_interval_seconds,
        )

        iteration = 0

        while not self._shutdown_requested:
            iteration += 1

            logger.info("scan_iteration_started", iteration=iteration)

            # Perform scan
            opportunities = await self.scan_once()

            # Yield results
            yield opportunities

            # Wait for next interval
            if not self._shutdown_requested:
                logger.info(
                    "waiting_for_next_scan",
                    seconds=self.config.refresh_interval_seconds,
                )
                await asyncio.sleep(self.config.refresh_interval_seconds)

        logger.info("realtime_scan_stopped", total_iterations=iteration)

    async def _fetch_tickers(self) -> list[Ticker]:
        """
        Fetch all market tickers from exchange.

        Returns:
            List of Ticker objects

        Raises:
            NetworkError: If fetch fails after retries
        """
        # This will be implemented when exchange integration is added
        # For now, raise an error indicating exchange not connected
        if self._exchange is None:
            raise NetworkError(
                "Exchange not connected. Set _exchange before calling scan methods."
            )

        # Call exchange.get_ticker(symbol=None) to get all tickers
        try:
            tickers = await self._exchange.get_ticker(symbol=None)
            return tickers
        except Exception as e:
            logger.error("ticker_fetch_failed", error=str(e))
            raise NetworkError(f"Failed to fetch tickers: {e}") from e

    def _filter_valid_tickers(self, tickers: list[Ticker]) -> list[Ticker]:
        """
        Filter out invalid ticker prices.

        Invalid conditions:
        - bid <= 0
        - ask <= 0
        - bid >= ask (inverted spread)

        Args:
            tickers: Raw ticker list

        Returns:
            List of valid tickers
        """
        valid = []

        for ticker in tickers:
            if ticker.bid <= 0 or ticker.ask <= 0:
                logger.warning(
                    "invalid_price_zero_or_negative",
                    symbol=ticker.symbol,
                    bid=str(ticker.bid),
                    ask=str(ticker.ask),
                )
                continue

            if ticker.bid >= ticker.ask:
                logger.warning(
                    "invalid_price_inverted_spread",
                    symbol=ticker.symbol,
                    bid=str(ticker.bid),
                    ask=str(ticker.ask),
                )
                continue

            valid.append(ticker)

        return valid
