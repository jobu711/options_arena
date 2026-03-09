"""CLI commands: scan, health, universe (refresh/list/stats), debate.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from options_arena.cli.app import app
from options_arena.cli.progress import RichProgressCallback, setup_sigint_handler
from options_arena.cli.rendering import (
    render_batch_summary_table,
    render_debate_history,
    render_debate_panels,
    render_health_table,
    render_scan_table,
)
from options_arena.data import Database, Repository
from options_arena.models import IndicatorSignals, TickerScore
from options_arena.models.config import AppSettings
from options_arena.models.enums import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_ALIASES,
    GICSIndustryGroup,
    GICSSector,
    LLMProvider,
    MarketCapTier,
    ScanPreset,
    SignalDirection,
)
from options_arena.scan import CancellationToken, ScanPipeline, ScanResult
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    compute_indicators,
    ohlcv_to_dataframe,
)
from options_arena.scoring import recommend_contracts
from options_arena.services.cache import ServiceCache
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.fred import FredService
from options_arena.services.health import HealthService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import MarketDataService
from options_arena.services.openbb_service import OpenBBService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

if TYPE_CHECKING:
    from options_arena.agents import DebateResult
    from options_arena.models import DimensionalScores

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

# Near-zero timeout that forces the data-driven fallback path (skips AI agents)
_FALLBACK_ONLY_TIMEOUT_SEC = 0.001


def _validate_provider_config(provider: LLMProvider, settings: AppSettings) -> None:
    """Fail fast if the selected LLM provider is missing its API key.

    Raises ``typer.Exit(1)`` with a helpful error message instead of silently
    falling back to data-driven mode when the provider can't actually run.
    """
    import os  # noqa: PLC0415

    if provider == LLMProvider.ANTHROPIC:
        has_key = (
            settings.debate.anthropic_api_key is not None
            or os.environ.get("ANTHROPIC_API_KEY") is not None
        )
        if not has_key:
            err_console.print(
                "[red]Anthropic provider requires an API key. "
                "Set ANTHROPIC_API_KEY or ARENA_DEBATE__ANTHROPIC_API_KEY.[/red]"
            )
            raise typer.Exit(code=1)
    elif provider == LLMProvider.GROQ:
        has_key = settings.debate.api_key is not None or os.environ.get("GROQ_API_KEY") is not None
        if not has_key:
            err_console.print(
                "[red]Groq provider requires an API key. "
                "Set GROQ_API_KEY or ARENA_DEBATE__API_KEY.[/red]"
            )
            raise typer.Exit(code=1)


# Resolve data directory from project root (src/options_arena/cli/commands.py → parents[3])
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------


def _parse_sectors(raw: list[str]) -> list[GICSSector]:
    """Resolve raw sector strings to GICSSector enums via SECTOR_ALIASES.

    Raises ``typer.BadParameter`` with valid options on unrecognised input.
    """
    result: list[GICSSector] = []
    for item in raw:
        key = item.strip().lower()
        if key in SECTOR_ALIASES:
            result.append(SECTOR_ALIASES[key])
        else:
            # Try direct enum construction (handles canonical values)
            try:
                result.append(GICSSector(item.strip()))
            except ValueError:
                valid = sorted({a for a in SECTOR_ALIASES if " " not in a and "-" not in a})
                raise typer.BadParameter(
                    f"Unknown sector {item!r}. Valid names: {', '.join(valid)}"
                ) from None
    return result


def _parse_market_caps(raw: list[str]) -> list[MarketCapTier]:
    """Resolve raw market cap strings to MarketCapTier enums.

    Raises ``typer.BadParameter`` with valid options on unrecognised input.
    """
    result: list[MarketCapTier] = []
    for item in raw:
        key = item.strip().lower()
        try:
            result.append(MarketCapTier(key))
        except ValueError:
            valid = sorted(t.value for t in MarketCapTier)
            raise typer.BadParameter(
                f"Unknown market cap tier {item!r}. Valid tiers: {', '.join(valid)}"
            ) from None
    return list(dict.fromkeys(result))


def _parse_industry_groups(raw: list[str]) -> list[GICSIndustryGroup]:
    """Resolve raw industry group strings to GICSIndustryGroup enums via INDUSTRY_GROUP_ALIASES.

    Raises ``typer.BadParameter`` with valid options on unrecognised input.
    """
    result: list[GICSIndustryGroup] = []
    for item in raw:
        key = item.strip().lower()
        if key in INDUSTRY_GROUP_ALIASES:
            result.append(INDUSTRY_GROUP_ALIASES[key])
        else:
            try:
                result.append(GICSIndustryGroup(item.strip()))
            except ValueError:
                valid = sorted(
                    {a for a in INDUSTRY_GROUP_ALIASES if " " not in a and "&" not in a}
                )
                raise typer.BadParameter(
                    f"Unknown industry group {item!r}. Valid names: {', '.join(valid)}"
                ) from None
    return list(dict.fromkeys(result))


@app.command()
def scan(
    preset: ScanPreset = typer.Option(  # noqa: B008
        ScanPreset.SP500,
        "--preset",
        "-p",
        help=(
            "Preset universe: full (all optionable), sp500, etfs,"
            " nasdaq100, russell2000, most_active"
        ),
    ),
    top_n: int = typer.Option(50, "--top-n", "-n", help="Top N tickers for options analysis"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum composite score"),
    sector: list[str] = typer.Option(  # noqa: B008
        [], "--sector", "-s", help="Filter by GICS sector (repeatable)"
    ),
    market_cap: list[str] = typer.Option(  # noqa: B008
        [], "--market-cap", help="Market cap tier (repeatable): mega, large, mid, small, micro"
    ),
    exclude_earnings: int | None = typer.Option(
        None, "--exclude-earnings", help="Exclude tickers with earnings within N days"
    ),
    direction: SignalDirection | None = typer.Option(  # noqa: B008
        None, "--direction", help="Filter by signal direction: bullish, bearish, neutral"
    ),
    min_iv_rank: float | None = typer.Option(
        None, "--min-iv-rank", help="Minimum IV rank (0-100)"
    ),
    industry_group: list[str] = typer.Option(  # noqa: B008
        [], "--industry-group", help="Filter by GICS industry group (repeatable)"
    ),
    min_price: float | None = typer.Option(
        None, "--min-price", help="Minimum underlying stock price"
    ),
    max_price: float | None = typer.Option(
        None, "--max-price", help="Maximum underlying stock price"
    ),
    min_dte: int | None = typer.Option(
        None, "--min-dte", help="Minimum days to expiration for option contracts"
    ),
    max_dte: int | None = typer.Option(
        None, "--max-dte", help="Maximum days to expiration for option contracts"
    ),
    tickers: str | None = typer.Option(
        None, "--tickers", help="Comma-separated list of custom tickers to scan"
    ),
) -> None:
    """Run the full scan pipeline: universe -> scoring -> options -> persist."""
    sectors = _parse_sectors(sector)
    cap_tiers = _parse_market_caps(market_cap)
    industry_groups = _parse_industry_groups(industry_group)
    custom_tickers = (
        [t.strip().upper() for t in tickers.split(",") if t.strip()] if tickers else []
    )
    asyncio.run(
        _scan_async(
            preset,
            top_n,
            min_score,
            sectors,
            cap_tiers,
            exclude_earnings,
            direction,
            min_iv_rank,
            industry_groups=industry_groups,
            min_price=min_price,
            max_price=max_price,
            min_dte=min_dte,
            max_dte=max_dte,
            custom_tickers=custom_tickers,
        )
    )


async def _scan_async(
    preset: ScanPreset,
    top_n: int,
    min_score: float,
    sectors: list[GICSSector],
    market_cap_tiers: list[MarketCapTier] | None = None,
    exclude_near_earnings_days: int | None = None,
    direction_filter: SignalDirection | None = None,
    min_iv_rank: float | None = None,
    industry_groups: list[GICSIndustryGroup] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_dte: int | None = None,
    max_dte: int | None = None,
    custom_tickers: list[str] | None = None,
) -> None:
    """Run the scan pipeline with full service lifecycle management."""
    start_time = time.monotonic()

    # Config with CLI overrides (immutable copy pattern — same as API)
    settings = AppSettings()
    scan_overrides: dict[str, object] = {
        "top_n": top_n,
        "min_score": min_score,
        "sectors": sectors,
    }
    if market_cap_tiers:
        scan_overrides["market_cap_tiers"] = market_cap_tiers
    if exclude_near_earnings_days is not None:
        scan_overrides["exclude_near_earnings_days"] = exclude_near_earnings_days
    if direction_filter is not None:
        scan_overrides["direction_filter"] = direction_filter
    if min_iv_rank is not None:
        scan_overrides["min_iv_rank"] = min_iv_rank
    if industry_groups:
        scan_overrides["industry_groups"] = industry_groups
    if min_price is not None:
        scan_overrides["min_price"] = min_price
    if max_price is not None:
        scan_overrides["max_price"] = max_price
    if min_dte is not None:
        scan_overrides["min_dte"] = min_dte
    if max_dte is not None:
        scan_overrides["max_dte"] = max_dte
    if custom_tickers:
        scan_overrides["custom_tickers"] = custom_tickers

    # DTE overrides also forward to PricingConfig for contract filtering
    pricing_overrides: dict[str, object] = {}
    if min_dte is not None:
        pricing_overrides["dte_min"] = min_dte
    if max_dte is not None:
        pricing_overrides["dte_max"] = max_dte

    settings = settings.model_copy(
        update={
            "scan": settings.scan.model_copy(update=scan_overrides),
            **(
                {"pricing": settings.pricing.model_copy(update=pricing_overrides)}
                if pricing_overrides
                else {}
            ),
        }
    )

    # Infrastructure (lightweight constructors — no I/O)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    db = Database(_DATA_DIR / "options_arena.db")

    # Track services for cleanup — None until successfully constructed
    market_data: MarketDataService | None = None
    options_data: OptionsDataService | None = None
    fred: FredService | None = None
    universe_svc: UniverseService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        # Services (DI pattern)
        market_data = MarketDataService(settings.service, cache, limiter)
        options_data = OptionsDataService(
            settings.service,
            settings.pricing,
            cache,
            limiter,
            openbb_config=settings.openbb,
        )
        fred = FredService(settings.service, settings.pricing, cache)
        universe_svc = UniverseService(settings.service, cache, limiter)

        # Pipeline
        pipeline = ScanPipeline(
            settings,
            market_data,
            options_data,
            fred,
            universe_svc,
            repo,
        )

        # Cancellation token + SIGINT handler
        token = CancellationToken()
        setup_sigint_handler(token, err_console)

        # Progress bar on stderr (preserves piped stdout)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=err_console,
            transient=False,
        ) as progress:
            callback = RichProgressCallback(progress)
            result = await pipeline.run(preset, token, callback)

        # Render results
        elapsed = time.monotonic() - start_time
        _render_scan_results(result, elapsed, sectors=sectors)

    except Exception as exc:
        logger.exception("Scan pipeline failed")
        err_console.print("[red]Scan failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        # Restore default SIGINT handler
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        # Close all services that were successfully constructed
        if market_data is not None:
            await market_data.close()
        if options_data is not None:
            await options_data.close()
        if fred is not None:
            await fred.close()
        if universe_svc is not None:
            await universe_svc.close()
        await cache.close()
        await db.close()


def _render_scan_results(
    result: ScanResult,
    elapsed: float,
    sectors: list[GICSSector] | None = None,
) -> None:
    """Render scan results: table + summary + disclaimer."""
    if result.cancelled:
        err_console.print(
            f"[yellow]Scan cancelled after {result.phases_completed}/4 phases.[/yellow]"
        )

    # Show active sector filter when present
    if sectors:
        sector_names = ", ".join(s.value for s in sectors)
        console.print(f"[bold cyan]Sector filter:[/bold cyan] {sector_names}\n")

    if result.scores:
        table = render_scan_table(result)
        console.print(table)

    # Summary line
    rec_count = sum(len(contracts) for contracts in result.recommendations.values())
    console.print(
        f"\n{result.scan_run.tickers_scanned} tickers scanned, "
        f"{result.scan_run.tickers_scored} scored, "
        f"{rec_count} recommendations in {elapsed:.1f}s"
    )


# ---------------------------------------------------------------------------
# debate command
# ---------------------------------------------------------------------------


@app.command()
def debate(
    ticker: str | None = typer.Argument(None, help="Ticker symbol (omit for --batch)"),
    batch: bool = typer.Option(False, "--batch", help="Debate top tickers from latest scan"),
    batch_limit: int = typer.Option(5, "--batch-limit", help="Max tickers in batch mode"),
    history: bool = typer.Option(False, "--history", help="Show past debates"),
    fallback_only: bool = typer.Option(
        False, "--fallback-only", help="Force data-driven path (skip AI)"
    ),
    export: str | None = typer.Option(None, "--export", help="Export format: md"),
    export_dir: str = typer.Option("./reports", "--export-dir", help="Export output directory"),
    no_openbb: bool = typer.Option(False, "--no-openbb", help="Skip OpenBB enrichment"),
    no_recon: bool = typer.Option(False, "--no-recon", help="Skip intelligence fetching"),
    provider: LLMProvider = typer.Option(  # noqa: B008
        LLMProvider.GROQ, "--provider", help="LLM provider: groq (free) or anthropic"
    ),
) -> None:
    """Run AI debate on a scored ticker."""
    if batch and ticker is not None:
        err_console.print("[red]Cannot use --batch with a ticker argument.[/red]")
        raise typer.Exit(code=1)
    if batch and history:
        err_console.print("[red]Cannot use --history with --batch.[/red]")
        raise typer.Exit(code=1)
    if not batch and ticker is None:
        err_console.print("[red]Provide a TICKER or use --batch.[/red]")
        raise typer.Exit(code=1)
    if export is not None and export != "md":
        err_console.print("[red]--export must be 'md'.[/red]")
        raise typer.Exit(code=1)

    if not fallback_only:
        settings = AppSettings()
        _validate_provider_config(provider, settings)

    if batch:
        asyncio.run(
            _batch_async(
                batch_limit,
                fallback_only,
                no_openbb=no_openbb,
                no_recon=no_recon,
                provider=provider,
            )
        )
    else:
        assert ticker is not None  # validated above
        asyncio.run(
            _debate_async(
                ticker.upper(),
                history,
                fallback_only,
                export,
                export_dir,
                no_openbb=no_openbb,
                no_recon=no_recon,
                provider=provider,
            )
        )


async def _batch_async(
    batch_limit: int,
    fallback_only: bool,
    *,
    no_openbb: bool = False,
    no_recon: bool = False,
    provider: LLMProvider = LLMProvider.GROQ,
) -> None:
    """Batch debate: run debates for top-scored tickers from the latest scan."""
    settings = AppSettings()
    if provider != settings.debate.provider:
        settings.debate = settings.debate.model_copy(update={"provider": provider})
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    db = Database(_DATA_DIR / "options_arena.db")

    market_data: MarketDataService | None = None
    options_data: OptionsDataService | None = None
    fred: FredService | None = None
    openbb_svc: OpenBBService | None = None
    intelligence_svc: IntelligenceService | None = None
    fd_svc: FinancialDatasetsService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        # Load latest scan scores
        latest_scan = await repo.get_latest_scan()
        if latest_scan is None:
            err_console.print(
                "[red]No scan data found. Run: options-arena scan --preset sp500[/red]"
            )
            raise typer.Exit(code=1)

        assert latest_scan.id is not None
        scores = await repo.get_scores_for_scan(latest_scan.id)
        top_scores = sorted(scores, key=lambda s: s.composite_score, reverse=True)[:batch_limit]

        if not top_scores:
            err_console.print("[yellow]No scored tickers in latest scan.[/yellow]")
            return

        # Create services ONCE (shared across all tickers)
        market_data = MarketDataService(settings.service, cache, limiter)
        options_data = OptionsDataService(
            settings.service,
            settings.pricing,
            cache,
            limiter,
            openbb_config=settings.openbb,
        )
        fred = FredService(settings.service, settings.pricing, cache)

        if not no_openbb and settings.openbb.enabled:
            openbb_svc = OpenBBService(settings.openbb, cache, limiter)

        if not no_recon and settings.intelligence.enabled:
            intelligence_svc = IntelligenceService(settings.intelligence, cache, limiter)

        if settings.financial_datasets.enabled and settings.financial_datasets.api_key is not None:
            fd_svc = FinancialDatasetsService(
                config=settings.financial_datasets,
                cache=cache,
                limiter=limiter,
            )

        err_console.print(f"[cyan]Batch debate: {len(top_scores)} tickers[/cyan]\n")

        results: list[tuple[str, DebateResult | None, str | None]] = []
        start_time = time.monotonic()
        batch_delay = settings.debate.batch_ticker_delay

        for i, ticker_score in enumerate(top_scores, 1):
            ticker = ticker_score.ticker
            if i > 1 and batch_delay > 0:
                logger.debug(
                    "Batch inter-ticker delay: %.1fs before %s (%d/%d)",
                    batch_delay,
                    ticker,
                    i,
                    len(top_scores),
                )
                await asyncio.sleep(batch_delay)
            err_console.print(f"[cyan]Debating {ticker} ({i}/{len(top_scores)})...[/cyan]")
            try:
                result = await _debate_single(
                    ticker_score,
                    settings,
                    market_data,
                    options_data,
                    fred,
                    repo,
                    fallback_only=fallback_only,
                    openbb_svc=openbb_svc,
                    intelligence_svc=intelligence_svc,
                    fd_svc=fd_svc,
                )
                results.append((ticker, result, None))
                # Brief per-ticker result
                direction = result.thesis.direction.value.upper()
                confidence = f"{result.thesis.confidence * 100:.0f}%"
                err_console.print(f"  [dim]{ticker}: {direction} ({confidence})[/dim]")
            except Exception as exc:
                logger.exception("Batch debate failed for %s", ticker)
                results.append((ticker, None, str(exc)))
                err_console.print(f"  [red]{ticker}: FAILED ({exc})[/red]")

        # Render summary table
        elapsed = time.monotonic() - start_time
        table = render_batch_summary_table(results)
        console.print(table)

        succeeded = sum(1 for _, r, _ in results if r is not None)
        console.print(
            f"\n[dim]{succeeded}/{len(results)} debates completed in {elapsed:.1f}s[/dim]"
        )

    except KeyboardInterrupt:
        err_console.print("\n[yellow]Batch debate cancelled.[/yellow]")
        raise typer.Exit(code=130)  # noqa: B904
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("Batch debate failed")
        err_console.print("[red]Batch failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        if fd_svc is not None:
            await fd_svc.close()
        if intelligence_svc is not None:
            await intelligence_svc.close()
        if openbb_svc is not None:
            await openbb_svc.close()
        if market_data is not None:
            await market_data.close()
        if options_data is not None:
            await options_data.close()
        if fred is not None:
            await fred.close()
        await cache.close()
        await db.close()


def _export_result(
    result: DebateResult,
    ticker: str,
    fmt: str,
    export_dir: str,
) -> None:
    """Export a debate result to file. Prints status or error to stderr."""
    from datetime import date  # noqa: PLC0415

    from options_arena.reporting import export_debate_to_file  # noqa: PLC0415

    export_path = Path(export_dir) / f"debate_{ticker}_{date.today().isoformat()}.{fmt}"
    export_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        export_debate_to_file(result, export_path, fmt=fmt)
        err_console.print(f"[green]Exported: {export_path}[/green]")
    except OSError:
        logger.exception("Failed to write export file: %s", export_path)
        err_console.print(f"[red]Failed to write: {export_path}[/red]")


async def _debate_single(
    ticker_score: TickerScore,
    settings: AppSettings,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService,
    repo: Repository,
    *,
    fallback_only: bool = False,
    openbb_svc: OpenBBService | None = None,
    intelligence_svc: IntelligenceService | None = None,
    fd_svc: FinancialDatasetsService | None = None,
) -> DebateResult:
    """Run a single AI debate for one ticker. Returns result without rendering.

    Fetches live market data, recommends contracts, and runs the debate pipeline.
    The caller is responsible for service lifecycle (creation and cleanup) and
    any console output (status messages, rendering, disclaimers).

    Args:
        ticker_score: Scored ticker from a prior scan run.
        settings: Application settings (debate config, pricing config, service config).
        market_data: Pre-created market data service.
        options_data: Pre-created options data service.
        fred: Pre-created FRED service.
        repo: Database repository for debate persistence.
        fallback_only: If True, force data-driven path by using near-zero timeouts.
        openbb_svc: Optional OpenBB service for enrichment data (fundamentals, flow, sentiment).
        intelligence_svc: Optional intelligence service for analyst/insider/institutional data.

    Returns:
        DebateResult with agent responses, thesis, usage, and duration.
    """
    ticker = ticker_score.ticker

    # Fetch quote, ticker info, OHLCV, risk-free rate, and option chains concurrently
    quote_task = market_data.fetch_quote(ticker)
    info_task = market_data.fetch_ticker_info(ticker)
    ohlcv_task = market_data.fetch_ohlcv(ticker, period="1y")
    risk_free_task = fred.fetch_risk_free_rate()
    chains_task = options_data.fetch_chain_all_expirations(ticker)

    quote, ticker_info, ohlcv_list, risk_free_rate, chain_results = await asyncio.gather(
        quote_task, info_task, ohlcv_task, risk_free_task, chains_task
    )

    # Compute raw indicators from OHLCV data so the debate context gets
    # actual values (e.g., RSI=65.3) instead of percentile-ranked values
    # (e.g., RSI=99.0 meaning "higher than 99% of peers").
    # TickerScore.signals from the DB contains percentile-ranked values.
    raw_signals: IndicatorSignals
    if ohlcv_list:
        df = ohlcv_to_dataframe(ohlcv_list)
        raw_signals = compute_indicators(df, INDICATOR_REGISTRY)
    else:
        raw_signals = ticker_score.signals

    # Create a ticker score copy with raw indicator signals for the debate
    debate_score = ticker_score.model_copy(update={"signals": raw_signals})

    # Flatten all contracts across expirations
    all_contracts = [c for chain in chain_results for c in chain.contracts]

    # Enrich with options-specific indicators from the full chain
    spot = float(ticker_info.current_price)
    if all_contracts:
        from options_arena.scan.indicators import compute_options_indicators  # noqa: PLC0415

        options_signals = compute_options_indicators(all_contracts, spot)
        if options_signals.put_call_ratio is not None:
            debate_score.signals.put_call_ratio = options_signals.put_call_ratio
        if options_signals.max_pain_distance is not None:
            debate_score.signals.max_pain_distance = options_signals.max_pain_distance

    # Select best contract via scoring/contracts.py (mirrors scan pipeline Phase 3)
    contracts = recommend_contracts(
        contracts=all_contracts,
        direction=debate_score.direction,
        spot=spot,
        risk_free_rate=risk_free_rate,
        dividend_yield=ticker_info.dividend_yield,
        config=settings.pricing,
    )

    logger.info(
        "Debate %s: %d chains fetched, %d total contracts, %d recommended",
        ticker,
        len(chain_results),
        len(all_contracts),
        len(contracts),
    )

    # Fetch OpenBB enrichment data concurrently (never raises — returns None on error)
    from options_arena.models.openbb import (  # noqa: PLC0415
        FundamentalSnapshot,
        NewsSentimentSnapshot,
        UnusualFlowSnapshot,
    )

    fundamentals: FundamentalSnapshot | None = None
    flow: UnusualFlowSnapshot | None = None
    sentiment: NewsSentimentSnapshot | None = None
    if openbb_svc is not None:
        fundamentals, flow, sentiment = await asyncio.gather(
            openbb_svc.fetch_fundamentals(ticker_score.ticker),
            openbb_svc.fetch_unusual_flow(ticker_score.ticker),
            openbb_svc.fetch_news_sentiment(ticker_score.ticker),
        )

    # Fetch intelligence data (never raises -- returns None on error)
    from options_arena.models.intelligence import IntelligencePackage  # noqa: PLC0415

    intel: IntelligencePackage | None = None
    if intelligence_svc is not None:
        intel = await intelligence_svc.fetch_intelligence(ticker, spot)

    # Fetch Financial Datasets enrichment (never raises — returns None on error)
    from options_arena.models.financial_datasets import (  # noqa: PLC0415
        FinancialDatasetsPackage,
    )

    fd_package: FinancialDatasetsPackage | None = None
    if fd_svc is not None:
        fd_package = await fd_svc.fetch_package(ticker)

    # Lazy import: agents/ depends on pydantic-ai which may not be available.
    # Importing at call time keeps CLI tests (scan, health, universe) working
    # even when the optional dependency is absent.
    from options_arena.agents import run_debate  # noqa: PLC0415
    from options_arena.scoring import compute_dimensional_scores  # noqa: PLC0415

    # Force fallback mode if requested (near-zero timeout triggers data-driven path)
    config = settings.debate
    if fallback_only:
        config = settings.debate.model_copy(
            update={
                "agent_timeout": _FALLBACK_ONLY_TIMEOUT_SEC,
                "max_total_duration": _FALLBACK_ONLY_TIMEOUT_SEC,
                "min_debate_score": 0.0,
            }
        )

    # Compute dimensional scores from the debate signals for the v2 protocol
    dim_scores: DimensionalScores | None = None
    try:
        dim_scores = compute_dimensional_scores(debate_score.signals)
    except Exception:
        logger.debug("Could not compute dimensional scores for %s", ticker, exc_info=True)

    return await run_debate(
        ticker_score=debate_score,
        contracts=contracts,
        quote=quote,
        ticker_info=ticker_info,
        config=config,
        repository=repo,
        dimensional_scores=dim_scores,
        fundamentals=fundamentals,
        flow=flow,
        sentiment=sentiment,
        intelligence=intel,
        fd_package=fd_package,
    )


async def _debate_async(
    ticker: str,
    history: bool,
    fallback_only: bool,
    export: str | None = None,
    export_dir: str = "./reports",
    *,
    no_openbb: bool = False,
    no_recon: bool = False,
    provider: LLMProvider = LLMProvider.GROQ,
) -> None:
    """Run AI debate with full service lifecycle management."""
    settings = AppSettings()
    if provider != settings.debate.provider:
        settings.debate = settings.debate.model_copy(update={"provider": provider})
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    db = Database(_DATA_DIR / "options_arena.db")

    market_data: MarketDataService | None = None
    options_data: OptionsDataService | None = None
    fred: FredService | None = None
    openbb_svc: OpenBBService | None = None
    intelligence_svc: IntelligenceService | None = None
    fd_svc: FinancialDatasetsService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        # --history mode: show past debates and exit
        if history:
            debates = await repo.get_debates_for_ticker(ticker)
            if not debates:
                err_console.print(f"[yellow]No debate history for {ticker}.[/yellow]")
                return
            table = render_debate_history(debates, ticker)
            console.print(table)
            return

        # Get latest scan data for this ticker
        latest_scan = await repo.get_latest_scan()
        if latest_scan is None:
            err_console.print(
                "[red]No scan data found. Run: options-arena scan --preset sp500[/red]"
            )
            raise typer.Exit(code=1)

        assert latest_scan.id is not None
        scores = await repo.get_scores_for_scan(latest_scan.id)
        ticker_score = next((s for s in scores if s.ticker == ticker), None)
        if ticker_score is None:
            err_console.print(
                f"[red]No scan data for {ticker}. Run: options-arena scan --preset sp500[/red]"
            )
            raise typer.Exit(code=1)

        # Create services for live data fetching
        market_data = MarketDataService(settings.service, cache, limiter)
        options_data = OptionsDataService(
            settings.service,
            settings.pricing,
            cache,
            limiter,
            openbb_config=settings.openbb,
        )
        fred = FredService(settings.service, settings.pricing, cache)

        if not no_openbb and settings.openbb.enabled:
            openbb_svc = OpenBBService(settings.openbb, cache, limiter)

        if not no_recon and settings.intelligence.enabled:
            intelligence_svc = IntelligenceService(settings.intelligence, cache, limiter)

        if settings.financial_datasets.enabled and settings.financial_datasets.api_key is not None:
            fd_svc = FinancialDatasetsService(
                config=settings.financial_datasets,
                cache=cache,
                limiter=limiter,
            )

        err_console.print(f"[cyan]Fetching live data for {ticker}...[/cyan]")
        err_console.print(f"[cyan]Running debate for {ticker}...[/cyan]")

        result = await _debate_single(
            ticker_score=ticker_score,
            settings=settings,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            repo=repo,
            fallback_only=fallback_only,
            openbb_svc=openbb_svc,
            intelligence_svc=intelligence_svc,
            fd_svc=fd_svc,
        )

        # Render debate output
        render_debate_panels(console, result)

        # Token usage and duration
        total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
        console.print(
            f"\n[dim]Duration: {result.duration_ms / 1000:.1f}s | Tokens: {total_tokens}[/dim]"
        )

        # Export to file (after terminal rendering)
        if export is not None:
            _export_result(result, ticker, export, export_dir)

    except KeyboardInterrupt:
        err_console.print("\n[yellow]Debate cancelled.[/yellow]")
        raise typer.Exit(code=130)  # noqa: B904
    except typer.Exit:
        raise
    except Exception as exc:
        logger.exception("Debate command failed")
        err_console.print("[red]Debate failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        if fd_svc is not None:
            await fd_svc.close()
        if intelligence_svc is not None:
            await intelligence_svc.close()
        if openbb_svc is not None:
            await openbb_svc.close()
        if market_data is not None:
            await market_data.close()
        if options_data is not None:
            await options_data.close()
        if fred is not None:
            await fred.close()
        await cache.close()
        await db.close()


# ---------------------------------------------------------------------------
# health command
# ---------------------------------------------------------------------------


@app.command()
def health() -> None:
    """Check external service availability."""
    asyncio.run(_health_async())


async def _health_async() -> None:
    """Run all health checks and render results."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = HealthService(
        settings.service,
        openbb_config=settings.openbb,
        fd_config=settings.financial_datasets,
        cache=cache,
        limiter=limiter,
    )
    try:
        statuses = await svc.check_all()
        table = render_health_table(statuses)
        console.print(table)
        all_up = all(s.available for s in statuses)
        if not all_up:
            raise typer.Exit(code=1)
    finally:
        await svc.close()
        await cache.close()


# ---------------------------------------------------------------------------
# universe subcommands
# ---------------------------------------------------------------------------

universe_app = typer.Typer(
    help="Manage the optionable ticker universe.",
    no_args_is_help=True,
)
app.add_typer(universe_app, name="universe")


@universe_app.command()
def refresh() -> None:
    """Force re-fetch CBOE universe and S&P 500 constituents."""
    asyncio.run(_refresh_async())


async def _refresh_async() -> None:
    """Fetch universe data from all sources and report counts."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        tickers = await svc.fetch_optionable_tickers()
        sp500 = await svc.fetch_sp500_constituents()
        console.print(
            f"[green]Universe refreshed:[/green] {len(tickers)} optionable tickers, "
            f"{len(sp500)} S&P 500 constituents"
        )
    finally:
        await svc.close()
        await cache.close()


@universe_app.command("list")
def list_tickers(
    sector: str | None = typer.Option(None, "--sector", help="Filter by GICS sector"),
    preset: ScanPreset = typer.Option(  # noqa: B008
        ScanPreset.SP500, "--preset", help="Scan preset"
    ),
) -> None:
    """Display tickers matching filters."""
    asyncio.run(_list_async(sector, preset))


async def _list_async(sector: str | None, preset: ScanPreset) -> None:
    """List tickers for the given preset, optionally filtered by sector."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        if preset == ScanPreset.SP500:
            constituents = await svc.fetch_sp500_constituents()
            tickers_with_sector = [(c.ticker, c.sector) for c in constituents]
            if sector:
                resolved = _parse_sectors([s.strip() for s in sector.split(",")])
                resolved_values = {g.value for g in resolved}
                tickers_with_sector = [
                    (t, s) for t, s in tickers_with_sector if s in resolved_values
                ]
            console.print(
                f"[bold]{len(tickers_with_sector)} tickers[/bold] (preset={preset.value})"
            )
            for ticker, sec in sorted(tickers_with_sector):
                console.print(f"  {ticker:<8} {sec}")
        elif preset == ScanPreset.ETFS:
            etf_tickers = await svc.fetch_etf_tickers()
            console.print(f"[bold]{len(etf_tickers)} ETF tickers[/bold] (preset={preset.value})")
            for i in range(0, len(etf_tickers), 8):
                row = etf_tickers[i : i + 8]
                console.print("  " + "  ".join(f"{t:<8}" for t in row))
        else:
            tickers = await svc.fetch_optionable_tickers()
            console.print(
                f"[bold]{len(tickers)} optionable tickers[/bold] (preset={preset.value})"
            )
            for i in range(0, len(tickers), 8):
                row = tickers[i : i + 8]
                console.print("  " + "  ".join(f"{t:<8}" for t in row))
    finally:
        await svc.close()
        await cache.close()


@universe_app.command()
def sectors() -> None:
    """List all 11 GICS sectors with S&P 500 ticker counts."""
    asyncio.run(_sectors_async())


async def _sectors_async() -> None:
    """Fetch S&P 500 constituents, group by sector, display Rich table."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        constituents = await svc.fetch_sp500_constituents()
        from options_arena.services.universe import build_sector_map  # noqa: PLC0415

        sector_map = build_sector_map(constituents)

        # Count tickers per sector
        counts: dict[GICSSector, int] = {}
        for gics_sector in sector_map.values():
            counts[gics_sector] = counts.get(gics_sector, 0) + 1

        # Build Rich table sorted by count descending
        table = Table(title="GICS Sectors (S&P 500)")
        table.add_column("Sector", style="bold white")
        table.add_column("Tickers", justify="right", style="cyan")

        for gics_sector, count in sorted(counts.items(), key=lambda x: -x[1]):
            table.add_row(gics_sector.value, str(count))

        total = sum(counts.values())
        table.add_section()
        table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")

        console.print(table)
    finally:
        await svc.close()
        await cache.close()


@universe_app.command()
def stats() -> None:
    """Show universe size, sector breakdown, S&P 500 count."""
    asyncio.run(_stats_async())


async def _stats_async() -> None:
    """Compute and display universe statistics with sector breakdown."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        tickers = await svc.fetch_optionable_tickers()
        sp500 = await svc.fetch_sp500_constituents()

        console.print("[bold]Universe Statistics[/bold]")
        console.print(f"  Optionable tickers: {len(tickers)}")
        console.print(f"  S&P 500 constituents: {len(sp500)}")

        # Sector breakdown
        sectors: dict[str, int] = {}
        for c in sp500:
            sectors[c.sector] = sectors.get(c.sector, 0) + 1

        if sectors:
            console.print("\n[bold]S&P 500 Sector Breakdown[/bold]")
            for sec, count in sorted(sectors.items(), key=lambda x: -x[1]):
                console.print(f"  {sec:<35} {count:>3}")
    finally:
        await svc.close()
        await cache.close()


@universe_app.command()
def index(
    force: bool = typer.Option(
        False, "--force", help="Re-index all tickers regardless of staleness"
    ),
    concurrency: int = typer.Option(
        5, "--concurrency", min=1, help="Max concurrent yfinance calls"
    ),
    max_age: int = typer.Option(30, "--max-age", min=0, help="Max age in days before re-indexing"),
) -> None:
    """Bulk-index CBOE tickers to build metadata cache."""
    asyncio.run(_index_async(force=force, concurrency=concurrency, max_age=max_age))


async def _index_async(*, force: bool, concurrency: int, max_age: int) -> None:
    """Fetch yfinance data for stale/missing CBOE tickers and persist to metadata table."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    universe_svc = UniverseService(settings.service, cache, limiter)
    market_data = MarketDataService(settings.service, cache, limiter)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    await db.connect()
    repo = Repository(db)

    try:
        # 1. Fetch CBOE ticker list
        all_tickers = await universe_svc.fetch_optionable_tickers()
        console.print(f"[bold]CBOE universe:[/bold] {len(all_tickers)} optionable tickers")

        # 2. Determine which tickers need indexing
        if force:
            tickers_to_index = all_tickers
        else:
            # Get tickers already in DB with fresh metadata
            universe_set = set(all_tickers)
            stale = universe_set.intersection(await repo.get_stale_tickers(max_age_days=max_age))
            # Also include tickers NOT in the metadata table at all
            coverage = await repo.get_metadata_coverage()
            if coverage.total == 0:
                # No metadata at all — index everything
                tickers_to_index = all_tickers
            else:
                all_metadata = await repo.get_all_ticker_metadata()
                indexed_tickers = {m.ticker for m in all_metadata}
                missing = universe_set - indexed_tickers
                tickers_to_index = sorted(missing | stale)

        if not tickers_to_index:
            console.print("[green]All tickers are fresh — nothing to index.[/green]")
            return

        console.print(
            f"[cyan]Indexing {len(tickers_to_index)} tickers "
            f"(concurrency={concurrency}, max_age={max_age}d, force={force})[/cyan]"
        )

        # 3. Process tickers with concurrency control
        sem = asyncio.Semaphore(concurrency)
        success_count = 0
        fail_count = 0

        from options_arena.services.universe import map_yfinance_to_metadata  # noqa: PLC0415

        async def _process_ticker(ticker: str) -> bool:
            """Fetch ticker info, map to metadata, persist. Returns True on success."""
            async with sem:
                try:
                    ticker_info = await market_data.fetch_ticker_info(ticker)
                    metadata = map_yfinance_to_metadata(ticker_info)
                    await repo.upsert_ticker_metadata(metadata)
                    return True
                except Exception:
                    logger.warning("Failed to index %s", ticker, exc_info=True)
                    return False

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=Console(stderr=True),
            transient=False,
        ) as progress:
            task_id = progress.add_task("[cyan]Indexing tickers", total=len(tickers_to_index))

            # Process in batches via gather for concurrency
            tasks = []
            for ticker in tickers_to_index:
                tasks.append(_process_ticker(ticker))

            # Gather all tasks but update progress as each completes
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    fail_count += 1
                    logger.warning("Unexpected gather error: %s", result)
                elif result:
                    success_count += 1
                else:
                    fail_count += 1
                progress.update(task_id, advance=1)

        # 4. Final coverage report
        final_coverage = await repo.get_metadata_coverage()
        table = Table(title="Metadata Coverage")
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right", style="cyan")

        table.add_row("Total indexed", str(final_coverage.total))
        table.add_row("With sector", str(final_coverage.with_sector))
        table.add_row("With industry group", str(final_coverage.with_industry_group))
        table.add_row(
            "Sector coverage",
            f"{final_coverage.coverage * 100:.1f}%",
        )
        table.add_section()
        table.add_row("Indexed this run", str(success_count))
        table.add_row("Failed this run", str(fail_count))

        console.print(table)

    finally:
        await market_data.close()
        await universe_svc.close()
        await cache.close()
        await db.close()


# ---------------------------------------------------------------------------
# serve command
# ---------------------------------------------------------------------------


def _kill_stale_port_holder(host: str, port: int) -> None:
    """Detect and kill a stale process holding the serve port.

    On Windows, unclean shutdowns (terminal closed, process killed) can leave
    the old server process alive. This checks the port before uvicorn tries to
    bind and kills the stale holder to prevent ``[Errno 10048]``.
    """
    import socket  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        # Port is free — nothing to do
        return
    except OSError:
        pass  # Port in use — find and kill the holder
    finally:
        sock.close()

    if sys.platform != "win32":
        err_console.print(
            f"[yellow]Port {port} is in use. Kill the existing process and retry.[/yellow]"
        )
        raise typer.Exit(code=1)

    # Windows: use netstat to find the PID
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pid: int | None = None
        for line in result.stdout.splitlines():
            # Match LISTENING on our host:port
            if f"{host}:{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = int(parts[-1])
                break

        if pid is None:
            err_console.print(
                f"[yellow]Port {port} is in use but could not identify the process.[/yellow]"
            )
            raise typer.Exit(code=1)

        err_console.print(
            f"[yellow]Port {port} held by stale process (PID {pid}). Killing...[/yellow]"
        )
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            timeout=5,
        )
        err_console.print(f"[green]Killed PID {pid}. Starting server.[/green]")
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        err_console.print(f"[red]Failed to free port {port}: {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address"),
    port: int = typer.Option(8000, "--port", help="Port number"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open browser automatically"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (dev mode)"),
) -> None:
    """Start the FastAPI web server and serve the Vue SPA."""
    import ipaddress  # noqa: PLC0415

    import uvicorn  # noqa: PLC0415

    def _is_loopback(value: str) -> bool:
        if value == "localhost":
            return True
        try:
            return ipaddress.ip_address(value).is_loopback
        except ValueError:
            return False

    if not _is_loopback(host):
        err_console.print("[red]--host must be a loopback address (127.0.0.1 or localhost).[/red]")
        raise typer.Exit(code=1)

    # Kill stale process holding the port (common on Windows after unclean shutdown)
    _kill_stale_port_holder(host, port)

    if not no_open:
        import threading  # noqa: PLC0415
        import time  # noqa: PLC0415
        import webbrowser  # noqa: PLC0415

        def _open_browser() -> None:
            time.sleep(1.5)  # Wait for uvicorn to start
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run(
        "options_arena.api.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )
