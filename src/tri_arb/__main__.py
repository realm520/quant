"""Main entry point for tri-arb CLI application.

This module serves as the entry point when the package is run as:
    python -m tri_arb
or via the installed command:
    tri-arb

Handles uvloop installation and CLI app invocation.
"""

import sys

import uvloop

from tri_arb.cli.app import app
from tri_arb.config.logging import configure_logging, get_logger

# Configure logging at startup
configure_logging()
logger = get_logger(__name__)


def main() -> None:
    """Main entry point for the CLI application.

    Sets up uvloop event loop policy and invokes the Typer app.
    """
    try:
        # Install uvloop for better async performance
        uvloop.install()
        logger.info("uvloop event loop policy installed")

        # Import CLI commands to register them
        # This ensures all commands are available when app() is called
        from tri_arb.cli.commands import config, start, status  # noqa: F401

        logger.info("CLI commands registered")

        # Run the Typer app
        app()

    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Application error", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
