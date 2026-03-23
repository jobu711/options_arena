"""Repository — typed CRUD for all persistence domains.

Composed via mixins — each domain in its own file.
MRO: Repository -> ScanMixin -> DebateMixin -> AnalyticsMixin -> MetadataMixin -> RepositoryBase
"""

from __future__ import annotations

import logging

from ._agency import AgencyMixin, AgencyQueryRow
from ._analytics import AnalyticsMixin
from ._debate import DebateMixin, DebateRow
from ._learning import LearningMixin
from ._metadata import MetadataMixin
from ._recommendation import RecommendationMixin, RecommendationRow
from ._scan import ScanMixin
from ._spreads import SpreadsMixin
from .database import Database

logger = logging.getLogger(__name__)

# Re-export data-layer row types so existing imports from .repository still work
__all__ = ["AgencyQueryRow", "DebateRow", "RecommendationRow", "Repository"]


class Repository(
    ScanMixin,
    DebateMixin,
    AnalyticsMixin,
    MetadataMixin,
    SpreadsMixin,
    AgencyMixin,
    RecommendationMixin,
    LearningMixin,
):
    """Typed CRUD for all persistence domains.

    Composed via mixins — each domain in its own file.
    MRO: Repository -> ScanMixin -> DebateMixin -> AnalyticsMixin
      -> MetadataMixin -> SpreadsMixin -> AgencyMixin
      -> RecommendationMixin -> LearningMixin -> RepositoryBase

    Parameters
    ----------
    db
        A connected ``Database`` instance.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
