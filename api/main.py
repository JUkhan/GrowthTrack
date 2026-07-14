"""FastAPI application entrypoint (inbound adapter).

Run with: ``uvicorn api.main:app``
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.health import router as health_router

app = FastAPI(title="GrowthTrack API")

# Only relevant for local dev: the Vite dev server (5173) calls this API
# (8000) directly — a different origin. In staging/production the frontend
# is served by Nginx same-origin with the API (docker/nginx/nginx.conf), so
# CORS never applies there; allowing the dev origin unconditionally is safe.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
