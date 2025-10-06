"""Typer CLI application structure.

Main CLI application with command groups and global options.
For MVP scaffold, this provides the basic CLI structure with
placeholder commands.
"""

from typing import Optional

import typer

from tri_arb.config.logging import configure_logging, get_logger
from tri_arb.config.settings import settings

# Configure logging at module level
configure_logging()
logger = get_logger(__name__)


def version_callback(value: bool) -> None:
    """Handle version flag."""
    if value:
        typer.echo("tri-arb version 0.1.0")
        raise typer.Exit()


# Create main Typer app
app = typer.Typer(
    name="tri-arb",
    help="Triangle Arbitrage Trading System",
    add_completion=False,
    no_args_is_help=True,
)


# Global callback for version and common options
@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose output",
    ),
) -> None:
    """Triangle Arbitrage Trading System CLI.

    This is a placeholder CLI for MVP scaffold.
    Actual trading functionality will be implemented in future iterations.
    """
    if verbose:
        logger.info("Verbose mode enabled")

    # Store common options in context
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


# Command registration will be done via imports in commands/__init__.py
# This allows commands to be registered when they are imported

logger.info("CLI app initialized", app_name=settings.app_name)
