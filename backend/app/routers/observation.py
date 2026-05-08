from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ObservationAnomaly, ObservationClusterEvent, ObservationReport, ObservationRun
from app.services.bot_threshold_report import generate_bot_threshold_report
from app.services.observation import (
    generate_observation_report,
    get_latest_report,
    get_observation_run,
    list_anomalies,
    list_clusters,
    list_observation_runs,
)

router = APIRouter(prefix="/api/observation", tags=["observation"])


@router.get("/runs", response_model=list[ObservationRun])
def read_observation_runs() -> list[ObservationRun]:
    return list_observation_runs()


@router.get("/runs/{run_id}", response_model=ObservationRun)
def read_observation_run(run_id: int) -> ObservationRun:
    try:
        return get_observation_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/reports/latest", response_model=ObservationReport | None)
def read_latest_observation_report() -> ObservationReport | None:
    return get_latest_report()


@router.get("/reports/bot-thresholds")
async def read_bot_threshold_report(
    symbol: str = Query(default="BTCUSDT"),
    lookback_hours: int = Query(default=24, ge=1, le=168),
    source: str = Query(default="live"),
    model: int = Query(default=3, ge=1, le=3),
    ranges: str = Query(default="24h,3d"),
) -> dict:
    selected_ranges = [item.strip() for item in ranges.split(",") if item.strip()]
    return await generate_bot_threshold_report(
        symbol=symbol,
        lookback_hours=lookback_hours,
        source=source,
        model=model,
        ranges=selected_ranges,
        persist=False,
    )


@router.post("/reports/bot-thresholds")
async def create_bot_threshold_report(
    symbol: str = Query(default="BTCUSDT"),
    lookback_hours: int = Query(default=24, ge=1, le=168),
    source: str = Query(default="live"),
    model: int = Query(default=3, ge=1, le=3),
    ranges: str = Query(default="24h,3d"),
) -> dict:
    selected_ranges = [item.strip() for item in ranges.split(",") if item.strip()]
    return await generate_bot_threshold_report(
        symbol=symbol,
        lookback_hours=lookback_hours,
        source=source,
        model=model,
        ranges=selected_ranges,
        persist=True,
    )


@router.post("/reports/{run_id}", response_model=ObservationReport)
def create_observation_report(run_id: str) -> ObservationReport:
    try:
        return generate_observation_report(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/anomalies", response_model=list[ObservationAnomaly])
def read_observation_anomalies(run_id: str = Query(default="latest")) -> list[ObservationAnomaly]:
    try:
        return list_anomalies(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/clusters", response_model=list[ObservationClusterEvent])
def read_observation_clusters(run_id: str = Query(default="latest")) -> list[ObservationClusterEvent]:
    try:
        return list_clusters(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
