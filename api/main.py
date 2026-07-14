"""FastAPI application entrypoint (inbound adapter).

Run with: ``uvicorn api.main:app``
"""

from fastapi import FastAPI

from api.routes.health import router as health_router

app = FastAPI(title="GrowthTrack API")

app.include_router(health_router)
