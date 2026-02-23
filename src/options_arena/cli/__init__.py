"""Options Arena -- CLI entry point.

Importing ``app`` registers all commands via side-effect imports.
The ``commands`` module must be imported so that ``@app.command()``
decorators fire and attach scan, health, and universe commands to ``app``.
"""

# Side-effect import: registers @app.command() decorators on the shared `app`.
import options_arena.cli.commands as _commands  # noqa: F401, E402
from options_arena.cli.app import app

__all__ = ["app"]
