from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_database
from app.routers import exchanges, heatmap, liquidations, observation

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(heatmap.router)
app.include_router(exchanges.router)
app.include_router(liquidations.router)
app.include_router(observation.router)

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "mock"}
