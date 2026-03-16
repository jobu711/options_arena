"""Tests for scoring.clustering — contract Greeks clustering via K-means."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from options_arena.models.config import MLConfig
from options_arena.models.enums import PricingModel
from options_arena.models.options import OptionGreeks
from options_arena.scoring.clustering import (
    ClusteringResult,
    ContractCluster,
    GreeksCentroid,
    cluster_contracts_by_greeks,
)
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_greeks(
    delta: float = 0.45,
    gamma: float = 0.03,
    theta: float = -0.05,
    vega: float = 0.15,
) -> OptionGreeks:
    """Build an ``OptionGreeks`` with sensible defaults."""
    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=0.01,
        pricing_model=PricingModel.BAW,
    )


def _make_contracts_with_greeks(n: int, *, diverse: bool = True) -> list:
    """Build *n* contracts with Greeks attached.

    When *diverse* is True, Greeks vary across the contracts to produce
    distinguishable clusters. When False, all contracts get identical Greeks.
    """
    contracts = []
    for i in range(n):
        if diverse:
            # Create variation across 4 archetypes
            archetype = i % 4
            jitter = (i % 3) * 0.05
            if archetype == 0:
                # High delta (directional)
                greeks = _make_greeks(
                    delta=0.80 + jitter,
                    gamma=0.01,
                    theta=-0.02,
                    vega=0.05,
                )
            elif archetype == 1:
                # High gamma
                greeks = _make_greeks(
                    delta=0.30,
                    gamma=0.10 + (i % 3) * 0.02,
                    theta=-0.04,
                    vega=0.08,
                )
            elif archetype == 2:
                # Income (most negative theta)
                greeks = _make_greeks(
                    delta=0.40,
                    gamma=0.02,
                    theta=-0.20 - jitter,
                    vega=0.06,
                )
            else:
                # Vol-play (high vega)
                greeks = _make_greeks(
                    delta=0.35,
                    gamma=0.03,
                    theta=-0.03,
                    vega=0.30 + jitter,
                )
        else:
            greeks = _make_greeks()

        contracts.append(make_option_contract(greeks=greeks))
    return contracts


# ---------------------------------------------------------------------------
# TestClusterContractsByGreeks
# ---------------------------------------------------------------------------


class TestClusterContractsByGreeks:
    """Tests for the ``cluster_contracts_by_greeks`` function."""

    def test_clusters_20_contracts_into_4_groups(self) -> None:
        """Verify 4 clusters returned from 20 contracts with valid Greeks."""
        contracts = _make_contracts_with_greeks(20)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters == 4
        assert len(result.clusters) == 4

    def test_returns_empty_with_fewer_than_10_contracts(self) -> None:
        """Verify empty ClusteringResult when <10 contracts."""
        contracts = _make_contracts_with_greeks(9)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters == 0
        assert result.clusters == []
        assert result.silhouette_score is None

    def test_returns_empty_when_sklearn_not_installed(self) -> None:
        """Verify graceful degradation without sklearn."""
        contracts = _make_contracts_with_greeks(20)

        with patch(
            "options_arena.scoring.clustering._get_kmeans",
            return_value=None,
        ):
            result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters == 0
        assert result.clusters == []

    def test_returns_empty_when_no_greeks(self) -> None:
        """Verify empty result when all contracts have greeks=None."""
        contracts = [make_option_contract() for _ in range(20)]
        # Default factory has greeks=None
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters == 0
        assert result.clusters == []

    def test_cluster_labels_are_semantic(self) -> None:
        """Verify labels are from {high-gamma, income, vol-play, directional}."""
        contracts = _make_contracts_with_greeks(20)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        expected_labels = {"high-gamma", "income", "vol-play", "directional"}
        actual_labels = {c.label for c in result.clusters}
        assert actual_labels == expected_labels

    def test_silhouette_score_in_range(self) -> None:
        """Verify silhouette_score in [-1, 1] when clustering succeeds."""
        contracts = _make_contracts_with_greeks(20)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.silhouette_score is not None
        assert -1.0 <= result.silhouette_score <= 1.0

    def test_contract_indices_cover_all_valid(self) -> None:
        """Verify union of all cluster indices equals set of valid contract indices."""
        # Mix: 15 with Greeks, 5 without
        contracts_with = _make_contracts_with_greeks(15)
        contracts_without = [make_option_contract() for _ in range(5)]
        contracts = contracts_with + contracts_without

        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        all_indices: set[int] = set()
        for cluster in result.clusters:
            all_indices.update(cluster.contract_indices)

        # Should cover indices 0-14 (the ones with Greeks)
        expected_indices = set(range(15))
        assert all_indices == expected_indices

    def test_custom_n_clusters(self) -> None:
        """Verify n_clusters=3 produces 3 clusters."""
        contracts = _make_contracts_with_greeks(20)
        result = cluster_contracts_by_greeks(contracts, n_clusters=3)

        assert result.n_clusters == 3
        assert len(result.clusters) == 3

    def test_exactly_10_contracts_boundary(self) -> None:
        """Verify clustering runs with exactly 10 contracts (boundary)."""
        contracts = _make_contracts_with_greeks(10)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters > 0
        assert len(result.clusters) > 0

    def test_n_clusters_exceeds_valid_contracts(self) -> None:
        """Verify k is automatically reduced when n_clusters > valid contracts."""
        contracts = _make_contracts_with_greeks(10)
        result = cluster_contracts_by_greeks(contracts, n_clusters=10)

        # Should reduce effective k to number of valid contracts (max 10)
        assert result.n_clusters <= 10
        assert result.n_clusters >= 2

    def test_identical_greeks_handles_gracefully(self) -> None:
        """Verify all contracts with identical Greeks do not crash."""
        contracts = _make_contracts_with_greeks(12, diverse=False)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        # Should still produce a result (silhouette may be None or degenerate)
        assert result.n_clusters > 0

    def test_scaler_not_installed(self) -> None:
        """Verify empty result when MinMaxScaler is unavailable."""
        contracts = _make_contracts_with_greeks(20)

        with patch(
            "options_arena.scoring.clustering._get_scaler",
            return_value=None,
        ):
            result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters == 0
        assert result.clusters == []

    @pytest.mark.critical
    def test_cluster_contracts_happy_path(self) -> None:
        """Critical: happy path clustering produces valid result."""
        contracts = _make_contracts_with_greeks(20)
        result = cluster_contracts_by_greeks(contracts, n_clusters=4)

        assert result.n_clusters == 4
        assert len(result.clusters) == 4
        assert result.silhouette_score is not None

        # All indices accounted for
        all_indices = set()
        for c in result.clusters:
            all_indices.update(c.contract_indices)
        assert len(all_indices) == 20


# ---------------------------------------------------------------------------
# TestClusteringResult
# ---------------------------------------------------------------------------


class TestClusteringResult:
    """Tests for the ``ClusteringResult`` model."""

    def test_frozen_model(self) -> None:
        """Verify ClusteringResult is frozen."""
        result = ClusteringResult(clusters=[], n_clusters=0, silhouette_score=None)
        with pytest.raises(ValidationError):
            result.n_clusters = 5  # type: ignore[misc]

    def test_empty_construction(self) -> None:
        """Verify ClusteringResult(clusters=[], n_clusters=0, silhouette_score=None)."""
        result = ClusteringResult(clusters=[], n_clusters=0, silhouette_score=None)
        assert result.clusters == []
        assert result.n_clusters == 0
        assert result.silhouette_score is None

    def test_json_roundtrip(self) -> None:
        """Verify model survives JSON serialization."""
        centroid = GreeksCentroid(delta=0.5, gamma=0.03, theta=-0.05, vega=0.15)
        cluster = ContractCluster(
            label="directional",
            contract_indices=[0, 1, 2],
            centroid=centroid,
        )
        original = ClusteringResult(
            clusters=[cluster],
            n_clusters=1,
            silhouette_score=0.75,
        )
        json_str = original.model_dump_json()
        restored = ClusteringResult.model_validate_json(json_str)
        assert restored == original

    def test_silhouette_rejects_nan(self) -> None:
        """Verify NaN silhouette_score is rejected."""
        with pytest.raises(ValidationError, match="silhouette_score must be finite"):
            ClusteringResult(clusters=[], n_clusters=0, silhouette_score=float("nan"))

    def test_silhouette_rejects_inf(self) -> None:
        """Verify Inf silhouette_score is rejected."""
        with pytest.raises(ValidationError, match="silhouette_score must be finite"):
            ClusteringResult(clusters=[], n_clusters=0, silhouette_score=float("inf"))


# ---------------------------------------------------------------------------
# TestGreeksCentroid
# ---------------------------------------------------------------------------


class TestGreeksCentroid:
    """Tests for the ``GreeksCentroid`` model."""

    def test_construction(self) -> None:
        """Verify GreeksCentroid accepts valid floats."""
        centroid = GreeksCentroid(delta=0.45, gamma=0.03, theta=-0.05, vega=0.15)
        assert centroid.delta == pytest.approx(0.45)
        assert centroid.gamma == pytest.approx(0.03)
        assert centroid.theta == pytest.approx(-0.05)
        assert centroid.vega == pytest.approx(0.15)

    def test_frozen(self) -> None:
        """Verify GreeksCentroid is frozen."""
        centroid = GreeksCentroid(delta=0.45, gamma=0.03, theta=-0.05, vega=0.15)
        with pytest.raises(ValidationError):
            centroid.delta = 0.5  # type: ignore[misc]

    def test_rejects_nan(self) -> None:
        """Verify NaN values are rejected."""
        with pytest.raises(ValidationError, match="centroid value must be finite"):
            GreeksCentroid(delta=float("nan"), gamma=0.03, theta=-0.05, vega=0.15)

    def test_rejects_inf(self) -> None:
        """Verify Inf values are rejected."""
        with pytest.raises(ValidationError, match="centroid value must be finite"):
            GreeksCentroid(delta=0.45, gamma=float("inf"), theta=-0.05, vega=0.15)


# ---------------------------------------------------------------------------
# TestContractCluster
# ---------------------------------------------------------------------------


class TestContractCluster:
    """Tests for the ``ContractCluster`` model."""

    def test_frozen(self) -> None:
        """Verify ContractCluster is frozen."""
        centroid = GreeksCentroid(delta=0.45, gamma=0.03, theta=-0.05, vega=0.15)
        cluster = ContractCluster(label="directional", contract_indices=[0, 1], centroid=centroid)
        with pytest.raises(ValidationError):
            cluster.label = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestConfigFlag
# ---------------------------------------------------------------------------


class TestConfigFlag:
    """Tests for MLConfig clustering configuration flags."""

    def test_enable_clustering_default_false(self) -> None:
        """Verify MLConfig.enable_clustering defaults to False."""
        config = MLConfig()
        assert config.enable_clustering is False

    def test_contract_n_clusters_default(self) -> None:
        """Verify MLConfig.contract_n_clusters defaults to 4."""
        config = MLConfig()
        assert config.contract_n_clusters == 4

    def test_contract_n_clusters_valid_range(self) -> None:
        """Verify validator accepts values in [2, 10]."""
        config_low = MLConfig(contract_n_clusters=2)
        assert config_low.contract_n_clusters == 2

        config_high = MLConfig(contract_n_clusters=10)
        assert config_high.contract_n_clusters == 10

    def test_contract_n_clusters_rejects_below_range(self) -> None:
        """Verify validator rejects n_clusters < 2."""
        with pytest.raises(ValidationError, match="contract_n_clusters must be in"):
            MLConfig(contract_n_clusters=1)

    def test_contract_n_clusters_rejects_above_range(self) -> None:
        """Verify validator rejects n_clusters > 10."""
        with pytest.raises(ValidationError, match="contract_n_clusters must be in"):
            MLConfig(contract_n_clusters=11)
