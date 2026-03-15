"""Repository — typed CRUD for all persistence domains.

Composed via mixins — each domain in its own file.
MRO: Repository -> ScanMixin -> DebateMixin -> AnalyticsMixin -> MetadataMixin -> RepositoryBase
"""

from __future__ import annotations

import logging

from ._analytics import AnalyticsMixin
from ._debate import DebateMixin, DebateRow
from ._metadata import MetadataMixin
from ._scan import ScanMixin
from ._spreads import SpreadsMixin
from .database import Database

logger = logging.getLogger(__name__)

# Re-export DebateRow so existing imports from .repository still work
__all__ = ["DebateRow", "Repository"]


class Repository(ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin, SpreadsMixin):
    """Typed CRUD for all persistence domains.

    Composed via mixins — each domain in its own file.
    MRO: Repository -> ScanMixin -> DebateMixin -> AnalyticsMixin
      -> MetadataMixin -> SpreadsMixin -> RepositoryBase

    Parameters
    ----------
    db
        A connected ``Database`` instance.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
