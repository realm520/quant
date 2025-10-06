"""Health check system for monitoring component status.

Provides health check functions for database, cache, logging,
and metrics systems.
"""

from datetime import datetime, timezone
from typing import Dict, List

from tri_arb.config.logging import get_logger
from tri_arb.data.cache import cache_manager
from tri_arb.data.database import db_manager
from tri_arb.utils.metrics import metrics_server

logger = get_logger(__name__)


class HealthStatus:
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheck:
    """Health check result container.

    Attributes:
        name: Component name
        status: Health status
        message: Status message
        details: Additional details
        checked_at: Timestamp of check
    """

    def __init__(
        self,
        name: str,
        status: str,
        message: str = "",
        details: Dict = None,
    ) -> None:
        """Initialize health check result.

        Args:
            name: Component name
            status: Health status
            message: Status message
            details: Additional details
        """
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.checked_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
        }


async def check_database() -> HealthCheck:
    """Check database health.

    Returns:
        HealthCheck result for database
    """
    logger.debug("Checking database health")

    try:
        # Check if database is initialized
        if not db_manager._initialized:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Database not initialized",
                details={"initialized": False},
            )

        # Try a simple query
        async with db_manager.connection() as conn:
            await conn.execute("SELECT 1")

        return HealthCheck(
            name="database",
            status=HealthStatus.HEALTHY,
            message="Database operational",
            details={
                "initialized": True,
                "db_path": str(db_manager.db_path),
                "pool_size": db_manager.pool_size,
            },
        )

    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return HealthCheck(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Database error: {str(e)}",
            details={"error": str(e)},
        )


async def check_cache() -> HealthCheck:
    """Check cache health.

    Returns:
        HealthCheck result for cache
    """
    logger.debug("Checking cache health")

    try:
        # Get cache stats
        stats = await cache_manager.get_stats()

        # Check cache sizes
        ttl_size = stats.get("ttl_cache", {}).get("size", 0)
        ttl_max = stats.get("ttl_cache", {}).get("max_size", 0)
        lru_size = stats.get("lru_cache", {}).get("size", 0)
        lru_max = stats.get("lru_cache", {}).get("max_size", 0)

        # Determine status based on utilization
        utilization = max(
            ttl_size / ttl_max if ttl_max > 0 else 0,
            lru_size / lru_max if lru_max > 0 else 0,
        )

        if utilization > 0.9:
            status = HealthStatus.DEGRADED
            message = "Cache near capacity"
        else:
            status = HealthStatus.HEALTHY
            message = "Cache operational"

        return HealthCheck(
            name="cache",
            status=status,
            message=message,
            details={
                "stats": stats,
                "utilization": f"{utilization:.1%}",
            },
        )

    except Exception as e:
        logger.error("Cache health check failed", error=str(e))
        return HealthCheck(
            name="cache",
            status=HealthStatus.UNHEALTHY,
            message=f"Cache error: {str(e)}",
            details={"error": str(e)},
        )


async def check_logging() -> HealthCheck:
    """Check logging system health.

    Returns:
        HealthCheck result for logging
    """
    logger.debug("Checking logging health")

    try:
        # Test logging by writing a test message
        test_logger = get_logger("health_check")
        test_logger.debug("Health check test message")

        return HealthCheck(
            name="logging",
            status=HealthStatus.HEALTHY,
            message="Logging operational",
            details={"configured": True},
        )

    except Exception as e:
        return HealthCheck(
            name="logging",
            status=HealthStatus.UNHEALTHY,
            message=f"Logging error: {str(e)}",
            details={"error": str(e)},
        )


async def check_metrics() -> HealthCheck:
    """Check metrics system health.

    Returns:
        HealthCheck result for metrics
    """
    logger.debug("Checking metrics health")

    try:
        # Check if metrics server is running
        is_running = metrics_server.is_running()

        if is_running:
            status = HealthStatus.HEALTHY
            message = "Metrics server operational"
        else:
            status = HealthStatus.DEGRADED
            message = "Metrics server not started"

        return HealthCheck(
            name="metrics",
            status=status,
            message=message,
            details={
                "running": is_running,
                "port": metrics_server.port,
            },
        )

    except Exception as e:
        logger.error("Metrics health check failed", error=str(e))
        return HealthCheck(
            name="metrics",
            status=HealthStatus.UNHEALTHY,
            message=f"Metrics error: {str(e)}",
            details={"error": str(e)},
        )


async def check_all() -> Dict[str, HealthCheck]:
    """Run all health checks.

    Returns:
        Dictionary mapping component names to health check results
    """
    logger.info("Running all health checks")

    checks = {
        "database": await check_database(),
        "cache": await check_cache(),
        "logging": await check_logging(),
        "metrics": await check_metrics(),
    }

    logger.info(
        "Health checks complete",
        results={name: check.status for name, check in checks.items()},
    )

    return checks


async def get_overall_status(checks: Dict[str, HealthCheck]) -> str:
    """Determine overall system status from individual checks.

    Args:
        checks: Dictionary of health check results

    Returns:
        Overall system status
    """
    statuses = [check.status for check in checks.values()]

    if any(status == HealthStatus.UNHEALTHY for status in statuses):
        return HealthStatus.UNHEALTHY
    elif any(status == HealthStatus.DEGRADED for status in statuses):
        return HealthStatus.DEGRADED
    else:
        return HealthStatus.HEALTHY


async def get_health_report() -> Dict:
    """Get comprehensive health report.

    Returns:
        Dictionary with health report including all component checks
    """
    checks = await check_all()
    overall_status = await get_overall_status(checks)

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {name: check.to_dict() for name, check in checks.items()},
    }
