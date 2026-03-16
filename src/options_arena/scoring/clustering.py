"""Contract Greeks clustering via K-means.

Groups option contracts into semantically labelled clusters based on their Greeks
(delta, gamma, theta, vega). Uses min-max normalized feature vectors and K-means
clustering from scikit-learn (optional dependency). Degrades gracefully when sklearn
is not installed or when there are insufficient contracts.

Semantic labels are assigned by centroid analysis:
    - Highest |gamma| centroid -> "high-gamma"
    - Most negative theta centroid -> "income"
    - Highest vega centroid -> "vol-play"
    - Highest |delta| centroid -> "directional"

Functions:
    cluster_contracts_by_greeks -- Main entry point for Greeks-based clustering.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.options import OptionContract

logger = logging.getLogger(__name__)

# Minimum number of contracts with valid Greeks required for clustering.
_MIN_CONTRACTS: int = 10

# Semantic labels in priority order for centroid assignment.
_LABEL_HIGH_GAMMA: str = "high-gamma"
_LABEL_INCOME: str = "income"
_LABEL_VOL_PLAY: str = "vol-play"
_LABEL_DIRECTIONAL: str = "directional"

_ALL_LABELS: frozenset[str] = frozenset(
    {_LABEL_HIGH_GAMMA, _LABEL_INCOME, _LABEL_VOL_PLAY, _LABEL_DIRECTIONAL}
)


def _get_kmeans() -> type | None:
    """Return ``sklearn.cluster.KMeans`` class, or ``None`` if not installed."""
    try:
        from sklearn.cluster import KMeans

        return KMeans  # type: ignore[no-any-return]
    except ImportError:
        return None


def _get_scaler() -> type | None:
    """Return ``sklearn.preprocessing.MinMaxScaler`` class, or ``None`` if not installed."""
    try:
        from sklearn.preprocessing import MinMaxScaler

        return MinMaxScaler  # type: ignore[no-any-return]
    except ImportError:
        return None


def _get_silhouette_score() -> Callable[..., Any] | None:
    """Return ``sklearn.metrics.silhouette_score`` function, or ``None`` if not installed."""
    try:
        from sklearn.metrics import silhouette_score

        return silhouette_score  # type: ignore[no-any-return]
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GreeksCentroid(BaseModel):
    """Centroid of a contract cluster in Greeks space.

    Stores the mean delta, gamma, theta, and vega for contracts in a cluster.
    Values are in the original (un-normalized) Greeks scale.
    """

    model_config = ConfigDict(frozen=True)

    delta: float
    gamma: float
    theta: float
    vega: float

    @field_validator("delta", "gamma", "theta", "vega")
    @classmethod
    def _validate_finite(cls, v: float) -> float:
        """Ensure centroid values are finite."""
        if not math.isfinite(v):
            raise ValueError(f"centroid value must be finite, got {v}")
        return v


class ContractCluster(BaseModel):
    """A cluster of option contracts grouped by Greeks similarity.

    Attributes:
        label: Semantic label (e.g. "high-gamma", "income", "vol-play", "directional").
        contract_indices: Indices into the original contracts list for cluster members.
        centroid: Mean Greeks values for this cluster (original scale).
    """

    model_config = ConfigDict(frozen=True)

    label: str
    contract_indices: list[int]
    centroid: GreeksCentroid


class ClusteringResult(BaseModel):
    """Result of Greeks-based contract clustering.

    Attributes:
        clusters: List of contract clusters with semantic labels.
        n_clusters: Number of clusters (0 when clustering was skipped).
        silhouette_score: Clustering quality metric in [-1, 1], or None when
            clustering was skipped or silhouette could not be computed.
    """

    model_config = ConfigDict(frozen=True)

    clusters: list[ContractCluster]
    n_clusters: int
    silhouette_score: float | None = None

    @field_validator("silhouette_score")
    @classmethod
    def _validate_silhouette(cls, v: float | None) -> float | None:
        """Ensure silhouette score is finite when present."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"silhouette_score must be finite, got {v}")
        return v


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _empty_result() -> ClusteringResult:
    """Return an empty ``ClusteringResult`` for graceful degradation."""
    return ClusteringResult(clusters=[], n_clusters=0, silhouette_score=None)


def _assign_labels(
    centroids_raw: list[list[float]],
    n_clusters: int,
) -> list[str]:
    """Assign semantic labels to clusters based on centroid analysis.

    Label assignment priority (greedy, no duplicates):
        1. Highest |gamma| -> "high-gamma"
        2. Most negative theta -> "income"
        3. Highest vega -> "vol-play"
        4. Highest |delta| -> "directional"

    When n_clusters < 4, only the first n_clusters labels are assigned.
    When n_clusters > 4, extra clusters get labels like "cluster-4", "cluster-5", etc.

    Args:
        centroids_raw: Centroid values in original scale. Each centroid is
            [delta, gamma, theta, vega].
        n_clusters: Number of clusters.

    Returns:
        List of labels, one per cluster.
    """
    labels: list[str | None] = [None] * n_clusters
    assigned: set[int] = set()

    # Feature index mapping: 0=delta, 1=gamma, 2=theta, 3=vega
    # Priority order of label assignment rules
    rules: list[tuple[str, int, bool, bool]] = [
        # (label, feature_idx, use_abs, negate_for_max)
        (_LABEL_HIGH_GAMMA, 1, True, False),  # highest |gamma|
        (_LABEL_INCOME, 2, False, True),  # most negative theta (negate -> max)
        (_LABEL_VOL_PLAY, 3, False, False),  # highest vega
        (_LABEL_DIRECTIONAL, 0, True, False),  # highest |delta|
    ]

    for label, feat_idx, use_abs, negate in rules:
        best_idx: int | None = None
        best_val: float = float("-inf")
        for i in range(n_clusters):
            if i in assigned:
                continue
            val = centroids_raw[i][feat_idx]
            if use_abs:
                val = abs(val)
            if negate:
                val = -val
            if val > best_val:
                best_val = val
                best_idx = i
        if best_idx is not None:
            labels[best_idx] = label
            assigned.add(best_idx)

    # Fill remaining unlabelled clusters (when n_clusters > 4)
    for i in range(n_clusters):
        if labels[i] is None:
            labels[i] = f"cluster-{i}"

    return [lbl if lbl is not None else f"cluster-{i}" for i, lbl in enumerate(labels)]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def cluster_contracts_by_greeks(
    contracts: list[OptionContract],
    n_clusters: int = 4,
) -> ClusteringResult:
    """Cluster option contracts by their Greeks using K-means.

    Extracts (delta, gamma, theta, vega) from contracts with non-None Greeks,
    applies min-max normalization, and runs K-means clustering. Clusters are
    labelled semantically based on centroid analysis.

    Args:
        contracts: List of option contracts (may include contracts without Greeks).
        n_clusters: Number of clusters to form (default 4, must be in [2, 10]).

    Returns:
        ``ClusteringResult`` with semantic cluster labels and silhouette score.
        Returns an empty result when:
        - Fewer than ``_MIN_CONTRACTS`` contracts have valid Greeks.
        - scikit-learn is not installed.
        - K-means fails for any reason.
    """
    KMeans = _get_kmeans()  # noqa: N806
    Scaler = _get_scaler()  # noqa: N806
    silhouette_fn = _get_silhouette_score()

    if KMeans is None or Scaler is None:
        logger.debug("sklearn not available — skipping contract clustering")
        return _empty_result()

    # Extract contracts with valid Greeks and track original indices
    valid_indices: list[int] = []
    feature_rows: list[list[float]] = []

    for i, contract in enumerate(contracts):
        if contract.greeks is None:
            continue
        g = contract.greeks
        # Guard against non-finite values in Greeks
        vals = [g.delta, g.gamma, g.theta, g.vega]
        if all(math.isfinite(v) for v in vals):
            valid_indices.append(i)
            feature_rows.append(vals)

    if len(feature_rows) < _MIN_CONTRACTS:
        logger.debug(
            "Only %d contracts with valid Greeks (need %d) — skipping clustering",
            len(feature_rows),
            _MIN_CONTRACTS,
        )
        return _empty_result()

    # Reduce k if more clusters requested than valid contracts
    effective_k = min(n_clusters, len(feature_rows))
    if effective_k < 2:
        return _empty_result()

    try:
        import numpy as np

        X = np.array(feature_rows, dtype=np.float64)  # noqa: N806

        # Min-max normalize features
        scaler = Scaler()
        X_scaled = scaler.fit_transform(X)  # noqa: N806

        # Fit K-means
        kmeans = KMeans(n_clusters=effective_k, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(X_scaled)

        # Compute silhouette score (requires >= 2 distinct labels)
        sil_score: float | None = None
        unique_labels = set(int(lbl) for lbl in cluster_labels)
        if silhouette_fn is not None and len(unique_labels) >= 2:
            try:
                raw_sil: float = silhouette_fn(X_scaled, cluster_labels)
                if math.isfinite(raw_sil):
                    sil_score = float(raw_sil)
            except Exception:  # noqa: BLE001
                logger.debug("Silhouette score computation failed", exc_info=True)

        # Build per-cluster index lists — only for populated cluster IDs.
        # KMeans can produce fewer distinct labels than n_clusters with
        # duplicate/identical samples (scikit-learn ConvergenceWarning).
        populated_ids = sorted({int(label) for label in cluster_labels})
        cluster_index_map: dict[int, list[int]] = {k: [] for k in populated_ids}
        for row_idx, cluster_id in enumerate(cluster_labels):
            cluster_index_map[int(cluster_id)].append(valid_indices[row_idx])

        actual_k = len(populated_ids)

        # Compute centroids in original (un-normalized) scale
        centroids_raw: list[list[float]] = []
        for k in populated_ids:
            member_rows = [
                feature_rows[row_idx]
                for row_idx, cid in enumerate(cluster_labels)
                if int(cid) == k
            ]
            centroid = [float(np.mean([r[feat] for r in member_rows])) for feat in range(4)]
            centroids_raw.append(centroid)

        # Assign semantic labels
        semantic_labels = _assign_labels(centroids_raw, actual_k)

        # Build ContractCluster models
        clusters: list[ContractCluster] = []
        for i, k in enumerate(populated_ids):
            centroid_vals = centroids_raw[i]
            clusters.append(
                ContractCluster(
                    label=semantic_labels[i],
                    contract_indices=sorted(cluster_index_map[k]),
                    centroid=GreeksCentroid(
                        delta=centroid_vals[0],
                        gamma=centroid_vals[1],
                        theta=centroid_vals[2],
                        vega=centroid_vals[3],
                    ),
                )
            )

        return ClusteringResult(
            clusters=clusters,
            n_clusters=actual_k,
            silhouette_score=sil_score,
        )

    except Exception:  # noqa: BLE001
        logger.warning("Contract clustering failed", exc_info=True)
        return _empty_result()
