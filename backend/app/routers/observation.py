from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ObservationAnomaly, ObservationClusterEvent, ObservationReport, ObservationRun
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
