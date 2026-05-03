from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from typing import Awaitable, Callable

from app.database import get_connection, init_database
from app.models.schemas import HeatmapResponse, ObservationAnomaly, ObservationClusterEvent, ObservationReport, ObservationRun
from app.services.heatmap_service import get_heatmap

CLUSTER_MIN_USD = 100_000_000
CLUSTER_MIN_SCORE = 0.70
CLUSTER_MIN_CONFIDENCE = 0.50


def create_observation_run(symbol: str, interval_seconds: int, notes: str | None = None) -> int:
    init_database()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO observation_runs (started_at, symbol, interval_seconds, status, notes)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (int(time.time()), symbol.upper(), interval_seconds, notes),
        )
        connection.commit()
        return int(cursor.lastrowid)


def finish_observation_run(run_id: int, status: str, notes: str | None = None) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE observation_runs SET ended_at = ?, status = ?, notes = COALESCE(?, notes) WHERE id = ?",
            (int(time.time()), status, notes, run_id),
        )
        connection.commit()


def record_observation_snapshot(run_id: int, response: HeatmapResponse) -> int:
    clusters = extract_clusters(response)
    anomalies = detect_anomalies(run_id, response)
    max_cluster = max(clusters, key=lambda cluster: cluster.estimated_liq_usd, default=None)
    max_score = max((bucket.total_score for bucket in response.buckets), default=0.0)
    max_confidence = max((bucket.confidence for bucket in response.buckets), default=0.0)
    total_oi = sum((weight.open_interest_usd or 0.0) for weight in response.exchange_weights)
    metadata = {
        "exchange_weights": [weight.model_dump() for weight in response.exchange_weights],
        "data_freshness_ms": response.data_freshness_ms,
        "generated_at": response.generated_at,
    }
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO observation_snapshots (
                run_id, ts, symbol, model, current_price, source, fallback, exchanges_used,
                total_open_interest_usd, max_cluster_usd, max_cluster_side,
                max_cluster_price_min, max_cluster_price_max, max_score, max_confidence,
                warnings_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                int(time.time()),
                response.symbol,
                response.model,
                response.last_price_usd,
                response.source,
                1 if response.fallback else 0,
                json.dumps(response.exchanges_used),
                total_oi,
                max_cluster.estimated_liq_usd if max_cluster else 0.0,
                max_cluster.direction if max_cluster else None,
                max_cluster.price_min if max_cluster else None,
                max_cluster.price_max if max_cluster else None,
                max_score,
                max_confidence,
                json.dumps(response.warnings),
                json.dumps(metadata, separators=(",", ":")),
            ),
        )
        snapshot_id = int(cursor.lastrowid)
        for cluster in clusters:
            _insert_cluster(connection, cluster.model_copy(update={"run_id": run_id}))
        for anomaly in anomalies:
            _insert_anomaly(connection, anomaly)
        connection.commit()
        return snapshot_id


def extract_clusters(response: HeatmapResponse) -> list[ObservationClusterEvent]:
    clusters: list[ObservationClusterEvent] = []
    bucket_width = _bucket_width(response)
    for bucket in response.buckets:
        candidates = [
            ("long_liquidation_cluster", bucket.long_liq_usd, bucket.price_bucket < response.last_price_usd),
            ("short_liquidation_cluster", bucket.short_liq_usd, bucket.price_bucket > response.last_price_usd),
        ]
        both_usd = min(bucket.long_liq_usd, bucket.short_liq_usd)
        if both_usd >= CLUSTER_MIN_USD:
            candidates.append(("both_sides_cluster", both_usd, True))
        for direction, estimated_usd, direction_ok in candidates:
            if not direction_ok:
                continue
            if estimated_usd < CLUSTER_MIN_USD or bucket.total_score < CLUSTER_MIN_SCORE or bucket.confidence < CLUSTER_MIN_CONFIDENCE:
                continue
            price_min = bucket.price_bucket - bucket_width / 2
            price_max = bucket.price_bucket + bucket_width / 2
            clusters.append(
                ObservationClusterEvent(
                    run_id=0,
                    ts=int(time.time()),
                    symbol=response.symbol,
                    model=response.model,
                    direction=direction,
                    price_min=price_min,
                    price_max=price_max,
                    estimated_liq_usd=estimated_usd,
                    score=bucket.total_score,
                    confidence=bucket.confidence,
                    exchanges_used=response.exchanges_used,
                    message_hash=_cluster_hash(response.symbol, response.model, direction, price_min, price_max),
                )
            )
    return clusters


def detect_anomalies(run_id: int, response: HeatmapResponse) -> list[ObservationAnomaly]:
    anomalies: list[ObservationAnomaly] = []
    ts = int(time.time())

    def add(severity: str, anomaly_type: str, message: str, exchange: str | None = None, raw_json: dict | None = None) -> None:
        anomalies.append(
            ObservationAnomaly(
                run_id=run_id,
                ts=ts,
                symbol=response.symbol,
                severity=severity,
                anomaly_type=anomaly_type,
                exchange=exchange,
                message=message,
                raw_json=raw_json or {},
            )
        )

    if response.fallback:
        add("warning", "fallback", "heatmap response used mock fallback")
    for warning in response.warnings:
        add("warning", "response_warning", warning)
        if ":" in warning:
            add("warning", "exchange_api_failure", warning, exchange=warning.split(":", 1)[0])
    if not math.isfinite(response.last_price_usd) or response.last_price_usd <= 0:
        add("critical", "invalid_current_price", "current price is missing or invalid")
    if not response.buckets:
        add("critical", "empty_heatmap", "heatmap bucket list is empty")
    total_oi = sum((weight.open_interest_usd or 0.0) for weight in response.exchange_weights)
    if total_oi <= 0:
        add("warning", "non_positive_total_open_interest", "total open interest USD is non-positive")
    for weight in response.exchange_weights:
        if not math.isfinite(weight.weight):
            add("critical", "invalid_exchange_weight", "exchange weight is not finite", exchange=weight.exchange)
        if weight.weight >= 0.90 and len(response.exchange_weights) > 1:
            add("warning", "dominant_exchange_weight", f"{weight.exchange} weight is {weight.weight:.1%}", exchange=weight.exchange)
    oi_values = [(weight.exchange, weight.open_interest_usd or 0.0) for weight in response.exchange_weights if (weight.open_interest_usd or 0.0) > 0]
    if len(oi_values) > 1:
        median_like = sorted(value for _, value in oi_values)[len(oi_values) // 2]
        for exchange, value in oi_values:
            if exchange in {"gate", "mexc"} and median_like > 0 and value / median_like >= 20:
                add("warning", "extreme_open_interest_usd", f"{exchange} open_interest_usd is extreme vs peers", exchange=exchange)
    for bucket in response.buckets:
        if not math.isfinite(bucket.total_score) or not 0 <= bucket.total_score <= 1:
            add("critical", "invalid_score", "bucket score outside 0..1")
        if not math.isfinite(bucket.confidence) or not 0 <= bucket.confidence <= 1:
            add("critical", "invalid_confidence", "bucket confidence outside 0..1")
    return anomalies


async def run_observation(
    symbol: str,
    interval_seconds: int,
    duration_hours: float,
    heatmap_fetcher: Callable[[str, int], Awaitable[HeatmapResponse]] | None = None,
    iterations: int | None = None,
) -> int:
    run_id = create_observation_run(symbol, interval_seconds)
    fetcher = heatmap_fetcher or _default_fetcher
    max_iterations = iterations or max(1, int(duration_hours * 3600 / interval_seconds))
    try:
        for index in range(max_iterations):
            for model in (1, 2, 3):
                try:
                    record_observation_snapshot(run_id, await fetcher(symbol, model))
                except Exception as exc:
                    _record_job_anomaly(run_id, symbol, "warning", "observation_fetch_failed", str(exc))
            if index < max_iterations - 1:
                await asyncio.sleep(interval_seconds)
        finish_observation_run(run_id, "completed")
    except KeyboardInterrupt:
        finish_observation_run(run_id, "stopped")
    except Exception as exc:
        finish_observation_run(run_id, "failed", str(exc))
        raise
    return run_id


async def _default_fetcher(symbol: str, model: int) -> HeatmapResponse:
    return await get_heatmap(symbol=symbol, model=model, currency="USD", response_range="90d", source="live")


def generate_observation_report(run_id: int | str = "latest") -> ObservationReport:
    resolved_run_id = resolve_run_id(run_id)
    with get_connection() as connection:
        run = connection.execute("SELECT * FROM observation_runs WHERE id = ?", (resolved_run_id,)).fetchone()
        snapshots = connection.execute("SELECT * FROM observation_snapshots WHERE run_id = ? ORDER BY ts", (resolved_run_id,)).fetchall()
        clusters = connection.execute("SELECT * FROM observation_cluster_events WHERE run_id = ? ORDER BY estimated_liq_usd DESC", (resolved_run_id,)).fetchall()
        anomalies = connection.execute("SELECT * FROM observation_anomalies WHERE run_id = ? ORDER BY ts DESC", (resolved_run_id,)).fetchall()
    if run is None:
        raise ValueError(f"observation run not found: {run_id}")
    period_start = run["started_at"]
    period_end = run["ended_at"] or int(time.time())
    report_json = _build_report_json(run, snapshots, clusters, anomalies)
    markdown = _build_report_markdown(report_json)
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO observation_reports (run_id, created_at, period_start, period_end, report_json, report_markdown)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (resolved_run_id, int(time.time()), period_start, period_end, json.dumps(report_json, separators=(",", ":")), markdown),
        )
        connection.commit()
        report_id = int(cursor.lastrowid)
    return ObservationReport(id=report_id, run_id=resolved_run_id, created_at=int(time.time()), period_start=period_start, period_end=period_end, report_json=report_json, report_markdown=markdown)


def list_observation_runs() -> list[ObservationRun]:
    init_database()
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM observation_runs ORDER BY started_at DESC LIMIT 50").fetchall()
    return [_run_from_row(row) for row in rows]


def get_observation_run(run_id: int | str) -> ObservationRun:
    resolved = resolve_run_id(run_id)
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM observation_runs WHERE id = ?", (resolved,)).fetchone()
    if row is None:
        raise ValueError(f"observation run not found: {run_id}")
    return _run_from_row(row)


def get_latest_report() -> ObservationReport | None:
    init_database()
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM observation_reports ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
    return _report_from_row(row) if row else None


def list_anomalies(run_id: int | str = "latest") -> list[ObservationAnomaly]:
    resolved = resolve_run_id(run_id)
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM observation_anomalies WHERE run_id = ? ORDER BY ts DESC LIMIT 500", (resolved,)).fetchall()
    return [_anomaly_from_row(row) for row in rows]


def list_clusters(run_id: int | str = "latest") -> list[ObservationClusterEvent]:
    resolved = resolve_run_id(run_id)
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM observation_cluster_events WHERE run_id = ? ORDER BY ts DESC LIMIT 500", (resolved,)).fetchall()
    return [_cluster_from_row(row) for row in rows]


def resolve_run_id(run_id: int | str) -> int:
    if run_id != "latest":
        return int(run_id)
    init_database()
    with get_connection() as connection:
        row = connection.execute("SELECT id FROM observation_runs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()
    if row is None:
        raise ValueError("no observation runs found")
    return int(row["id"])


def _insert_cluster(connection, cluster: ObservationClusterEvent) -> None:
    connection.execute(
        """
        INSERT INTO observation_cluster_events (
            run_id, ts, symbol, model, direction, price_min, price_max,
            estimated_liq_usd, score, confidence, exchanges_used, message_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            cluster.run_id,
            cluster.ts,
            cluster.symbol,
            cluster.model,
            cluster.direction,
            cluster.price_min,
            cluster.price_max,
            cluster.estimated_liq_usd,
            cluster.score,
            cluster.confidence,
            json.dumps(cluster.exchanges_used),
            cluster.message_hash,
        ),
    )


def _insert_anomaly(connection, anomaly: ObservationAnomaly) -> None:
    connection.execute(
        """
        INSERT INTO observation_anomalies (run_id, ts, symbol, severity, anomaly_type, exchange, message, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (anomaly.run_id, anomaly.ts, anomaly.symbol, anomaly.severity, anomaly.anomaly_type, anomaly.exchange, anomaly.message, json.dumps(anomaly.raw_json)),
    )


def _record_job_anomaly(run_id: int, symbol: str, severity: str, anomaly_type: str, message: str) -> None:
    with get_connection() as connection:
        _insert_anomaly(connection, ObservationAnomaly(run_id=run_id, ts=int(time.time()), symbol=symbol, severity=severity, anomaly_type=anomaly_type, message=message))
        connection.commit()


def _cluster_hash(symbol: str, model: int, direction: str, price_min: float, price_max: float) -> str:
    zone = f"{round(price_min / 100) * 100}-{round(price_max / 100) * 100}"
    return hashlib.sha256(f"{symbol}|{model}|{direction}|{zone}".encode("utf-8")).hexdigest()


def _bucket_width(response: HeatmapResponse) -> float:
    prices = sorted({bucket.price_bucket for bucket in response.buckets})
    if len(prices) < 2:
        return 250
    return max(100, min(500, prices[1] - prices[0]))


def _build_report_json(run, snapshots, clusters, anomalies) -> dict:
    fallback_count = sum(1 for row in snapshots if row["fallback"])
    model_counts = Counter(row["model"] for row in snapshots)
    weight_totals: dict[str, list[float]] = defaultdict(list)
    for row in snapshots:
        metadata = json.loads(row["metadata_json"] or "{}")
        for weight in metadata.get("exchange_weights", []):
            weight_totals[weight["exchange"]].append(weight["weight"])
    avg_weights = {exchange: sum(values) / len(values) for exchange, values in weight_totals.items() if values}
    top_clusters = [
        {
            "direction": row["direction"],
            "price_min": row["price_min"],
            "price_max": row["price_max"],
            "estimated_liq_usd": row["estimated_liq_usd"],
            "score": row["score"],
            "confidence": row["confidence"],
        }
        for row in clusters[:10]
    ]
    hash_counts = Counter(row["message_hash"] for row in clusters)
    persistent_zones = [{"message_hash": key, "count": count} for key, count in hash_counts.most_common(10)]
    scores = [row["max_score"] for row in snapshots]
    confidences = [row["max_confidence"] for row in snapshots]
    return {
        "run_id": run["id"],
        "symbol": run["symbol"],
        "status": run["status"],
        "snapshot_count": len(snapshots),
        "fallback_count": fallback_count,
        "average_exchange_weights": avg_weights,
        "top_clusters": top_clusters,
        "persistent_zones": persistent_zones,
        "score_distribution": _distribution(scores),
        "confidence_distribution": _distribution(confidences),
        "model_counts": dict(model_counts),
        "anomaly_count": len(anomalies),
        "anomalies": [{"severity": row["severity"], "type": row["anomaly_type"], "message": row["message"]} for row in anomalies[:50]],
        "telegram_threshold_candidates": {
            "min_estimated_liq_usd": CLUSTER_MIN_USD,
            "min_score": CLUSTER_MIN_SCORE,
            "min_confidence": CLUSTER_MIN_CONFIDENCE,
            "suppress_when_fallback": True,
        },
    }


def _build_report_markdown(report: dict) -> str:
    return "\n".join(
        [
            f"# Observation Report Run {report['run_id']}",
            "",
            f"- Symbol: {report['symbol']}",
            f"- Status: {report['status']}",
            f"- Snapshots: {report['snapshot_count']}",
            f"- Fallbacks: {report['fallback_count']}",
            f"- Anomalies: {report['anomaly_count']}",
            "",
            "## Telegram Threshold Candidates",
            f"- Estimated liquidation USD >= {report['telegram_threshold_candidates']['min_estimated_liq_usd']:,}",
            f"- Score >= {report['telegram_threshold_candidates']['min_score']}",
            f"- Confidence >= {report['telegram_threshold_candidates']['min_confidence']}",
            "- Suppress or label alerts when fallback=true",
        ]
    )


def _distribution(values: list[float]) -> dict:
    if not values:
        return {"min": 0, "max": 0, "avg": 0}
    return {"min": min(values), "max": max(values), "avg": sum(values) / len(values)}


def _run_from_row(row) -> ObservationRun:
    return ObservationRun(id=row["id"], started_at=row["started_at"], ended_at=row["ended_at"], symbol=row["symbol"], interval_seconds=row["interval_seconds"], status=row["status"], notes=row["notes"])


def _cluster_from_row(row) -> ObservationClusterEvent:
    return ObservationClusterEvent(run_id=row["run_id"], id=row["id"], ts=row["ts"], symbol=row["symbol"], model=row["model"], direction=row["direction"], price_min=row["price_min"], price_max=row["price_max"], estimated_liq_usd=row["estimated_liq_usd"], score=row["score"], confidence=row["confidence"], exchanges_used=json.loads(row["exchanges_used"] or "[]"), message_hash=row["message_hash"])


def _anomaly_from_row(row) -> ObservationAnomaly:
    return ObservationAnomaly(run_id=row["run_id"], id=row["id"], ts=row["ts"], symbol=row["symbol"], severity=row["severity"], anomaly_type=row["anomaly_type"], exchange=row["exchange"], message=row["message"], raw_json=json.loads(row["raw_json"] or "{}"))


def _report_from_row(row) -> ObservationReport:
    return ObservationReport(id=row["id"], run_id=row["run_id"], created_at=row["created_at"], period_start=row["period_start"], period_end=row["period_end"], report_json=json.loads(row["report_json"]), report_markdown=row["report_markdown"])
