"""Strategy mining models for Options Arena.

Three frozen Pydantic v2 models for the strategy mining pipeline:
  StrategyCondition — single dimensional condition (field, operator, value).
  StrategyRule      — mined pattern with conditions, stats, and approval status.
  AgentMemory       — long-term agent memory entries.

All snapshot models use ``frozen=True``. All float validators check ``math.isfinite()``.
All datetime fields enforce UTC.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import ConditionOperator, RuleStatus


class StrategyCondition(BaseModel):
    """A single dimensional condition within a strategy rule.

    Examples: ``field="sector", operator="eq", value="Information Technology"``
    or ``field="iv_rank", operator="gte", value=75.0``.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    operator: ConditionOperator
    value: float | str


class StrategyRule(BaseModel):
    """A mined strategy pattern with conditions, performance stats, and status.

    Rules start as ``CANDIDATE``, require human approval to become ``APPROVED``,
    and only approved rules are injected into desk agent prompts.
    """

    model_config = ConfigDict(frozen=True)

    rule_id: str
    pattern: str
    conditions: list[StrategyCondition]
    win_rate: float
    avg_return: float
    sample_size: int
    status: RuleStatus = RuleStatus.CANDIDATE
    created_at: datetime
    confidence: float = 0.5
    last_validated: datetime | None = None
    validation_count: int = 0

    @field_validator("win_rate")
    @classmethod
    def _validate_win_rate(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"win_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("avg_return")
    @classmethod
    def _validate_avg_return(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"avg_return must be finite, got {v}")
        return v

    @field_validator("sample_size")
    @classmethod
    def _validate_sample_size(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"sample_size must be >= 0, got {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("last_validated")
    @classmethod
    def _validate_last_validated(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("last_validated must be UTC")
        return v

    @field_validator("validation_count")
    @classmethod
    def _validate_validation_count(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"validation_count must be >= 0, got {v}")
        return v


class AgentMemory(BaseModel):
    """Long-term memory entry for a desk agent.

    Stores learned patterns, contextual knowledge, or strategy observations
    scoped by agent and scope type.
    """

    model_config = ConfigDict(frozen=True)

    memory_id: str
    agent_name: str
    scope: str
    scope_type: str
    content: str
    sample_size: int = 0
    win_rate: float = 0.0
    created_at: datetime

    @field_validator("win_rate")
    @classmethod
    def _validate_win_rate(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"win_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("sample_size")
    @classmethod
    def _validate_sample_size(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"sample_size must be >= 0, got {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v
