"""Async SQLite lifecycle and migration runner.

``Database`` manages the aiosqlite connection: opening with WAL mode and foreign
keys, running sequential numbered migrations from ``data/migrations/``, and closing
cleanly.  Pure infrastructure — no business logic.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# Default migrations directory: project root / data / migrations
# From src/options_arena/data/database.py → parents[3] → project root
_DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "data" / "migrations"


class Database:
    """Async SQLite database with WAL mode and sequential migration runner.

    Parameters
    ----------
    db_path
        Path to SQLite file, or ``":memory:"`` for in-memory databases (tests).
    migrations_dir
        Directory containing numbered ``*.sql`` migration files.  Defaults to
        ``<project_root>/data/migrations/``.
    """

    def __init__(
        self,
        db_path: Path | str,
        migrations_dir: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._migrations_dir = migrations_dir or _DEFAULT_MIGRATIONS_DIR
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Return the live connection.  Raises ``RuntimeError`` if not connected."""
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._conn

    async def connect(self) -> None:
        """Open connection, configure pragmas, and run pending migrations."""
        if self._conn is not None:
            logger.debug("Database already connected, skipping reconnect")
            return

        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row

        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        logger.debug("Opened database at %s (WAL mode, FK enabled)", self._db_path)

        # Create schema_version tracking table before reading migrations
        await self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        await self._conn.commit()

        await self._run_migrations()

    async def close(self) -> None:
        """Close the connection.  Idempotent — safe to call multiple times."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")

    async def _run_migrations(self) -> None:
        """Apply pending migrations from the migrations directory."""
        conn = self.conn

        if not self._migrations_dir.is_dir():
            logger.debug("No migrations directory at %s", self._migrations_dir)
            return

        migration_files = sorted(
            (p for p in self._migrations_dir.glob("*.sql") if p.stem.split("_")[0].isdigit()),
            key=lambda p: int(p.stem.split("_")[0]),
        )

        for path in migration_files:
            version = int(path.stem.split("_")[0])

            # Check if already applied
            async with conn.execute(
                "SELECT version FROM schema_version WHERE version = ?",
                (version,),
            ) as cursor:
                if await cursor.fetchone() is not None:
                    logger.debug("Migration %03d already applied, skipping", version)
                    continue

            # Apply migration
            sql_content = path.read_text(encoding="utf-8")
            await conn.executescript(sql_content)

            # Record the applied migration
            applied_at = datetime.now(UTC).isoformat()
            await conn.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (version, applied_at),
            )
            await conn.commit()
            logger.info("Applied migration %03d: %s", version, path.name)
