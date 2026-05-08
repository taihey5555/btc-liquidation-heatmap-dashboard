from __future__ import annotations

import json
import math
import time
from typing import Awaitable, Callable

from app.database import get_connection, init_database
from app.models.schemas import TopClustersResponse, TopClusterZone
from app.services.signal_service import get_top_clusters_signal


ClusterFetcher = Callable[..., Awaitable[TopClustersResponse]]


async def generate_bot_threshold_report(
    symbol: str = "BTCUSDT",
    lookback_hours: int = 24,
    source: str = "live",
    model: int = 3,
    ranges: list[str] | None = None,
    limit: int = 20,
    min_intensity: float = 0.0,
    persist: bool = False,
    cluster_fetcher: ClusterFetcher | None = None,
) -> dict:
    init_database()
    normalized_symbol = symbol.upper()
    normalized_ranges = [item.lower() for item in (ranges or ["24h", "3d"])]
    fetcher = cluster_fetcher or get_top_clusters_signal
    clusters = await fetcher(
        symbol=normalized_symbol,
        model=model,
        ranges=normalized_ranges,
        source=source,
        limit=limit,
        min_intensity=min_intensity,
    )
    db_summary = _database_summary(normalized_symbol, lookback_hours)
    threshold_candidates = _threshold_candidates(clusters, db_summary)
    report = {
        "symbol": normalized_symbol,
        "lookback_hours": lookback_hours,
        "source": clusters.source,
        "fallback": clusters.fallback,
        "generated_at": int(time.time()),
        "current_price": clusters.current_price,
        "ranges": clusters.ranges,
        "exchanges_used": clusters.exchanges_used,
        "warnings": clusters.warnings,
        "data_health": db_summary,
        "cluster_summary": _cluster_summary(clusters),
        "threshold_candidates": threshold_candidates,
        "recommended_profile": "balanced",
        "markdown": "",
    }
    report["markdown"] = _report_markdown(report)
    if persist:
        report["observation_report_id"] = _persist_report(report)
    return report


def _database_summary(symbol: str, lookback_hours: int) -> dict:
    now_ms = int(time.time() * 1000)
    since_ms = now_ms - lookback_hours * 60 * 60 * 1000
    with get_connection() as connection:
        market = connection.execute(
            "SELECT COUNT(*) AS count, MIN(ts) AS first_ts, MAX(ts) AS last_ts, COUNT(DISTINCT exchange) AS exchanges FROM market_snapshots WHERE symbol = ? AND ts >= ?",
            (symbol, since_ms),
        ).fetchone()
        deltas = connection.execute(
            """
            SELECT COUNT(*) AS count,
                   SUM(CASE WHEN side = 'long' THEN 1 ELSE 0 END) AS long_count,
                   SUM(CASE WHEN side = 'short' THEN 1 ELSE 0 END) AS short_count,
                   MAX(oi_delta_usd) AS max_delta_usd,
                   AVG(score) AS avg_score,
                   AVG(confidence) AS avg_confidence
            FROM oi_delta_buckets
            WHERE symbol = ? AND ts >= ?
            """,
            (symbol, since_ms),
        ).fetchone()
        liquidations = connection.execute(
            """
            SELECT COUNT(*) AS count,
                   SUM(CASE WHEN side = 'long_liquidated' THEN 1 ELSE 0 END) AS long_liquidated_count,
                   SUM(CASE WHEN side = 'short_liquidated' THEN 1 ELSE 0 END) AS short_liquidated_count,
                   COALESCE(SUM(notional_usd), 0) AS total_notional_usd,
                   COALESCE(MAX(notional_usd), 0) AS max_notional_usd
            FROM liquidation_events
            WHERE symbol = ? AND ts >= ?
            """,
            (symbol, since_ms),
        ).fetchone()
    market_count = int(market["count"] or 0)
    expected_per_exchange = max(1, int(lookback_hours * 60))
    expected_total = expected_per_exchange * 5
    coverage = min(1.0, market_count / expected_total)
    return {
        "market_snapshots": market_count,
        "market_snapshot_coverage": round(coverage, 4),
        "market_exchanges_seen": int(market["exchanges"] or 0),
        "market_first_ts": market["first_ts"],
        "market_last_ts": market["last_ts"],
        "oi_delta_buckets": int(deltas["count"] or 0),
        "oi_delta_long_count": int(deltas["long_count"] or 0),
        "oi_delta_short_count": int(deltas["short_count"] or 0),
        "oi_delta_max_usd": float(deltas["max_delta_usd"] or 0),
        "oi_delta_avg_score": float(deltas["avg_score"] or 0),
        "oi_delta_avg_confidence": float(deltas["avg_confidence"] or 0),
        "liquidation_events": int(liquidations["count"] or 0),
        "long_liquidated_count": int(liquidations["long_liquidated_count"] or 0),
        "short_liquidated_count": int(liquidations["short_liquidated_count"] or 0),
        "liquidation_total_notional_usd": float(liquidations["total_notional_usd"] or 0),
        "liquidation_max_notional_usd": float(liquidations["max_notional_usd"] or 0),
    }


def _cluster_summary(response: TopClustersResponse) -> dict:
    zones = [*response.top_clusters, *response.nearest_long_liq_below, *response.nearest_short_liq_above]
    unique = _unique_zones(zones)
    upside = [zone for zone in unique if zone.side == "short" or zone.distance_pct > 0]
    downside = [zone for zone in unique if zone.side == "long" or zone.distance_pct < 0]
    return {
        "top_cluster_count": len(response.top_clusters),
        "nearest_long_count": len(response.nearest_long_liq_below),
        "nearest_short_count": len(response.nearest_short_liq_above),
        "upside_score": _side_score(upside),
        "downside_score": _side_score(downside),
        "strongest_clusters": [_zone_to_dict(zone) for zone in response.top_clusters[:10]],
        "nearest_long_liq_below": [_zone_to_dict(zone) for zone in response.nearest_long_liq_below[:5]],
        "nearest_short_liq_above": [_zone_to_dict(zone) for zone in response.nearest_short_liq_above[:5]],
    }


def _threshold_candidates(response: TopClustersResponse, db_summary: dict) -> dict:
    zones = _unique_zones([*response.top_clusters, *response.nearest_long_liq_below, *response.nearest_short_liq_above])
    intensities = sorted(zone.relative_intensity for zone in zones if _finite(zone.relative_intensity))
    confidences = sorted(zone.confidence for zone in zones if _finite(zone.confidence))
    notionals = sorted(zone.estimated_liq_usd for zone in zones if _finite(zone.estimated_liq_usd) and zone.estimated_liq_usd > 0)
    distances = sorted(abs(zone.distance_pct) for zone in zones if _finite(zone.distance_pct))
    p50_intensity = _percentile(intensities, 0.50, 0.35)
    p75_intensity = _percentile(intensities, 0.75, 0.55)
    p25_confidence = _percentile(confidences, 0.25, 0.55)
    p50_notional = _percentile(notionals, 0.50, 300_000_000)
    nearest_distance = _percentile(distances, 0.35, 2.0)
    data_quality = _data_quality_score(db_summary, response)

    balanced_min_intensity = _round_step(_clamp(p50_intensity * 0.72, 0.22, 0.50), 0.01)
    balanced_min_confidence = _round_step(_clamp(p25_confidence, 0.55, 0.82), 0.01)
    balanced_min_notional = _round_notional(_clamp(p50_notional * 0.42, 150_000_000, 1_500_000_000))
    balanced_max_distance = _round_step(_clamp(nearest_distance * 1.35, 0.8, 4.0), 0.1)

    return {
        "data_quality_score": data_quality,
        "recommended_env": {
            "LIQ_HEATMAP_MODEL": "3",
            "LIQ_HEATMAP_RANGES": ",".join(response.ranges or ["24h", "3d"]),
            "LIQ_HEATMAP_MIN_INTENSITY": f"{balanced_min_intensity:.2f}",
            "LIQ_HEATMAP_LIMIT": "10",
        },
        "profiles": {
            "aggressive": {
                "min_intensity": _round_step(max(0.16, balanced_min_intensity - 0.08), 0.01),
                "min_confidence": _round_step(max(0.45, balanced_min_confidence - 0.08), 0.01),
                "min_estimated_liq_usd": _round_notional(max(100_000_000, balanced_min_notional * 0.65)),
                "max_distance_pct": _round_step(min(5.0, balanced_max_distance + 0.8), 0.1),
                "expected_behavior": "通知は多め。検証用に使う。",
            },
            "balanced": {
                "min_intensity": balanced_min_intensity,
                "min_confidence": balanced_min_confidence,
                "min_estimated_liq_usd": balanced_min_notional,
                "max_distance_pct": balanced_max_distance,
                "expected_behavior": "最初にbotへ入れる推奨値。",
            },
            "conservative": {
                "min_intensity": _round_step(min(0.75, balanced_min_intensity + 0.12), 0.01),
                "min_confidence": _round_step(min(0.9, balanced_min_confidence + 0.08), 0.01),
                "min_estimated_liq_usd": _round_notional(balanced_min_notional * 1.6),
                "max_distance_pct": _round_step(max(0.6, balanced_max_distance - 0.6), 0.1),
                "expected_behavior": "通知を絞る。本番寄りの監視に使う。",
            },
        },
        "bot_filter_logic": {
            "suppress_when_fallback": True,
            "prefer_ranges": ["24h", "3d"],
            "prefer_model": 3,
            "ignore_consumed_score_above": 0.75,
            "watch_both_sides_when_upside_downside_score_gap_below": 0.12,
        },
    }


def _data_quality_score(db_summary: dict, response: TopClustersResponse) -> float:
    coverage = float(db_summary.get("market_snapshot_coverage") or 0)
    exchange_score = min(1.0, len(response.exchanges_used) / 5)
    delta_score = min(1.0, (db_summary.get("oi_delta_buckets") or 0) / 300)
    liquidation_score = min(1.0, (db_summary.get("liquidation_events") or 0) / 50)
    fallback_penalty = 0.35 if response.fallback else 0.0
    warning_penalty = min(0.2, len(response.warnings) * 0.04)
    return round(_clamp(coverage * 0.35 + exchange_score * 0.25 + delta_score * 0.25 + liquidation_score * 0.15 - fallback_penalty - warning_penalty, 0, 1), 4)


def _persist_report(report: dict) -> int:
    run_id = _create_report_run(report)
    markdown = report["markdown"]
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO observation_reports (run_id, created_at, period_start, period_end, report_json, report_markdown)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                report["generated_at"],
                int(time.time()) - int(report["lookback_hours"]) * 60 * 60,
                int(time.time()),
                json.dumps(report, separators=(",", ":")),
                markdown,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def _create_report_run(report: dict) -> int:
    now = int(time.time())
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO observation_runs (started_at, ended_at, symbol, interval_seconds, status, notes)
            VALUES (?, ?, ?, ?, 'completed', ?)
            """,
            (
                now - int(report["lookback_hours"]) * 60 * 60,
                now,
                report["symbol"],
                0,
                f"bot threshold report {report['lookback_hours']}h",
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def _report_markdown(report: dict) -> str:
    balanced = report["threshold_candidates"]["profiles"]["balanced"]
    cluster_summary = report["cluster_summary"]
    lines = [
        f"# Bot Threshold Report {report['symbol']} {report['lookback_hours']}h",
        "",
        f"- Source: {report['source']} fallback={report['fallback']}",
        f"- Current price: ${report['current_price']:,.0f}",
        f"- Data quality: {report['threshold_candidates']['data_quality_score']:.2f}",
        f"- Market snapshots: {report['data_health']['market_snapshots']}",
        f"- OI delta buckets: {report['data_health']['oi_delta_buckets']}",
        f"- Liquidation events: {report['data_health']['liquidation_events']}",
        "",
        "## Recommended Balanced Thresholds",
        f"- min_intensity: {balanced['min_intensity']}",
        f"- min_confidence: {balanced['min_confidence']}",
        f"- min_estimated_liq_usd: ${balanced['min_estimated_liq_usd']:,.0f}",
        f"- max_distance_pct: {balanced['max_distance_pct']}%",
        "",
        "## Cluster Bias",
        f"- Upside score: {cluster_summary['upside_score']:.3f}",
        f"- Downside score: {cluster_summary['downside_score']:.3f}",
        "",
        "## Notes",
        "- This is a signal/filter report only. It does not add trading execution.",
        "- Start with the balanced profile, then compare notification logs against actual price reactions.",
    ]
    if report["warnings"]:
        lines.extend(["", "## Warnings", *[f"- {warning}" for warning in report["warnings"]]])
    return "\n".join(lines)


def _unique_zones(zones: list[TopClusterZone]) -> list[TopClusterZone]:
    seen: set[tuple[str, int, str, int]] = set()
    unique: list[TopClusterZone] = []
    for zone in zones:
        key = (zone.range, int(round(zone.price)), zone.side, int(round(zone.distance_pct * 10)))
        if key in seen:
            continue
        seen.add(key)
        unique.append(zone)
    return unique


def _side_score(zones: list[TopClusterZone]) -> float:
    if not zones:
        return 0.0
    score = sum(zone.relative_intensity * zone.confidence * (1.0 - min(0.85, zone.consumed_score * 0.5)) for zone in zones[:10])
    return round(score / min(10, len(zones)), 4)


def _zone_to_dict(zone: TopClusterZone) -> dict:
    return {
        "range": zone.range,
        "model": zone.model,
        "price": zone.price,
        "side": zone.side,
        "distance_pct": zone.distance_pct,
        "relative_intensity": zone.relative_intensity,
        "confidence": zone.confidence,
        "consumed_score": zone.consumed_score,
        "total_score": zone.total_score,
        "estimated_liq_usd": zone.estimated_liq_usd,
    }


def _percentile(values: list[float], percentile: float, default: float) -> float:
    if not values:
        return default
    index = int(round((len(values) - 1) * percentile))
    return values[max(0, min(index, len(values) - 1))]


def _round_notional(value: float) -> int:
    step = 50_000_000
    return int(round(value / step) * step)


def _round_step(value: float, step: float) -> float:
    return round(round(value / step) * step, 4)


def _finite(value: float) -> bool:
    return math.isfinite(value)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
