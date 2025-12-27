"""
Triangular arbitrage path finding algorithm.

Uses DFS with depth limit of 3 to discover closed-loop trading paths.
Based on specs/004-xt-get-ticker/contracts/monitor_api.md.
"""

from collections import defaultdict

import structlog

from tri_arb.models.arbitrage import TradingPath
from tri_arb.models.exchange import Ticker


logger = structlog.get_logger(__name__)


def find_arbitrage_paths(
    tickers: list[Ticker], base_currencies: list[str] | None = None
) -> list[TradingPath]:
    """
    Find all possible triangular arbitrage paths from ticker data.

    Uses DFS algorithm with depth limit of 3 to find closed-loop paths.

    Args:
        tickers: List of market tickers with price data
        base_currencies: Optional whitelist of starting currencies (None = all)

    Returns:
        List of valid triangular trading paths (closed loops)

    Raises:
        ValueError: If tickers is empty or contains invalid data

    Performance: < 100ms for 500 pairs (NFR-002)
    """
    if not tickers:
        raise ValueError("Tickers list cannot be empty")

    # Build adjacency graph: currency -> list of (target_currency, pair_symbol)
    graph: dict[str, list[tuple[str, str]]] = defaultdict(list)
    invalid_symbols = 0

    for ticker in tickers:
        # Parse trading pair (e.g., "BTC/USDT" -> base="BTC", quote="USDT")
        try:
            base, quote = ticker.symbol.split("/")
        except ValueError:
            # Skip invalid ticker symbols
            invalid_symbols += 1
            continue

        # 为每个交易对添加双向边，支持买卖两个方向
        # 这使得同一组交易对可以产生正向和反向套利路径
        # 例如: BTC/USDT 会创建 BTC→USDT 和 USDT→BTC 两条边
        graph[base].append((quote, ticker.symbol))  # 卖出方向: 卖出 base 得到 quote
        graph[quote].append((base, ticker.symbol))  # 买入方向: 用 quote 买入 base

    # Log graph statistics
    node_count = len(graph)
    edge_count = len(tickers) - invalid_symbols
    degree_distribution = {
        currency: len(neighbors) for currency, neighbors in graph.items()
    }
    avg_degree = sum(degree_distribution.values()) / node_count if node_count > 0 else 0

    # Find hub currencies (degree >= 10)
    hubs = sorted(
        [(curr, deg) for curr, deg in degree_distribution.items() if deg >= 10],
        key=lambda x: x[1],
        reverse=True,
    )[
        :5
    ]  # Top 5 hubs

    logger.info(
        "graph_built",
        nodes=node_count,
        edges=edge_count,
        avg_degree=f"{avg_degree:.1f}",
        top_hubs=[f"{curr}({deg})" for curr, deg in hubs],
        invalid_symbols=invalid_symbols,
    )

    # Get all possible starting currencies
    if base_currencies:
        start_currencies = [c for c in base_currencies if c in graph]
    else:
        start_currencies = list(graph.keys())

    # Find all triangular paths using DFS
    paths: list[TradingPath] = []
    paths_per_start: dict[str, int] = {}

    for start in start_currencies:
        initial_path_count = len(paths)

        # DFS with depth limit of 3
        _dfs_find_paths(
            graph=graph,
            current=start,
            start=start,
            visited_pairs=set(),
            path_pairs=[],
            depth=0,
            max_depth=3,
            paths=paths,
        )

        # Track paths found from this start
        paths_found = len(paths) - initial_path_count
        if paths_found > 0:
            paths_per_start[start] = paths_found

    # 路径去重：同一组交易对的不同起点路径只保留一个
    # 例如: (USDT→BTC→ETH→USDT) 和 (BTC→ETH→USDT→BTC) 是相同的交易对集合
    paths_before_dedup = len(paths)
    unique_paths = _deduplicate_paths(paths)
    paths_after_dedup = len(unique_paths)

    # Log path discovery statistics
    effective_starts = len(paths_per_start)

    # Top 5 starting currencies by path count
    top_starts = sorted(paths_per_start.items(), key=lambda x: x[1], reverse=True)[:5]

    logger.info(
        "path_discovery_complete",
        total_starts_tried=len(start_currencies),
        effective_starts=effective_starts,
        paths_before_dedup=paths_before_dedup,
        paths_after_dedup=paths_after_dedup,
        dedup_rate=(
            f"{(1 - paths_after_dedup/paths_before_dedup)*100:.1f}%"
            if paths_before_dedup > 0
            else "N/A"
        ),
        top_starts=[f"{curr}({count})" for curr, count in top_starts],
    )

    return unique_paths


def _normalize_path(path: TradingPath) -> frozenset[str]:
    """
    将路径规范化为交易对集合，用于去重。

    同一组交易对的不同起点路径会被规范化为相同的集合。
    例如:
    - USDT→BTC→ETH→USDT (BTC/USDT, ETH/BTC, ETH/USDT)
    - BTC→ETH→USDT→BTC (ETH/BTC, ETH/USDT, BTC/USDT)
    - ETH→USDT→BTC→ETH (ETH/USDT, BTC/USDT, ETH/BTC)
    以上三条路径会被规范化为同一个集合: {BTC/USDT, ETH/BTC, ETH/USDT}

    Args:
        path: 交易路径

    Returns:
        交易对集合（frozenset）
    """
    return frozenset(path.trading_pairs)


def _deduplicate_paths(paths: list[TradingPath]) -> list[TradingPath]:
    """
    对路径列表进行去重，移除使用相同交易对集合的重复路径。

    去重策略:
    - 使用交易对集合作为唯一键
    - 对于重复的路径，保留第一个发现的路径

    Args:
        paths: 原始路径列表

    Returns:
        去重后的路径列表
    """
    seen_pairs: set[frozenset[str]] = set()
    unique_paths: list[TradingPath] = []

    for path in paths:
        pair_set = _normalize_path(path)
        if pair_set not in seen_pairs:
            seen_pairs.add(pair_set)
            unique_paths.append(path)

    return unique_paths


def _dfs_find_paths(
    graph: dict[str, list[tuple[str, str]]],
    current: str,
    start: str,
    visited_pairs: set[str],
    path_pairs: list[str],
    depth: int,
    max_depth: int,
    paths: list[TradingPath],
) -> None:
    """
    DFS helper to find triangular arbitrage paths.

    Args:
        graph: Adjacency graph of currencies
        current: Current currency in the path
        start: Starting currency (must return here)
        visited_pairs: Set of already visited trading pairs
        path_pairs: Current path of trading pair symbols
        depth: Current depth in DFS
        max_depth: Maximum allowed depth (3 for triangular)
        paths: Output list to append found paths
    """
    # Base case: reached max depth
    if depth == max_depth:
        # Check if we're back at start (closed loop)
        if current == start and len(path_pairs) == 3:
            try:
                # Type assertion: we validated len == 3
                pairs_tuple = (path_pairs[0], path_pairs[1], path_pairs[2])
                trading_path = TradingPath(
                    start_currency=start, trading_pairs=pairs_tuple
                )
                # Verify it's a closed loop
                if trading_path.is_closed_loop:
                    paths.append(trading_path)
            except ValueError:
                # Invalid path, skip
                pass
        return

    # Explore neighbors
    if current not in graph:
        return

    for next_currency, pair_symbol in graph[current]:
        # Avoid revisiting same pair in same path
        if pair_symbol in visited_pairs:
            continue

        # Add to path
        visited_pairs.add(pair_symbol)
        path_pairs.append(pair_symbol)

        # Recurse
        _dfs_find_paths(
            graph=graph,
            current=next_currency,
            start=start,
            visited_pairs=visited_pairs,
            path_pairs=path_pairs,
            depth=depth + 1,
            max_depth=max_depth,
            paths=paths,
        )

        # Backtrack
        path_pairs.pop()
        visited_pairs.remove(pair_symbol)
