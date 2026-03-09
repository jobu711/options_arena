"""RepositoryBase — shared database access for repository mixins."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .database import Database

logger = logging.getLogger(__name__)


class RepositoryBase:
    """Base class providing shared database access for repository mixins."""

    _db: Database

    async def commit(self) -> None:
        """Explicitly commit the current transaction.

        Used by the scan pipeline to achieve atomic multi-step persistence:
        all four save calls use ``commit=False``, then a single ``commit()``
        ensures all-or-nothing semantics.
        """
        conn = self._db.conn
        await conn.commit()
