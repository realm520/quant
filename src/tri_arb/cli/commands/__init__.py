"""CLI commands module.

This module registers all CLI commands with the main Typer app.
Commands are automatically imported and registered when this module is loaded.
"""

from tri_arb.cli.commands import monitor  # noqa: F401
from tri_arb.cli.commands import account  # noqa: F401
from tri_arb.cli.commands import market  # noqa: F401
from tri_arb.cli.commands import order  # noqa: F401
from tri_arb.cli.commands import leverage  # noqa: F401

__all__ = ["monitor", "account", "market", "order", "leverage"]
