"""FastAPI application entrypoint (inbound adapter).

Run with: ``uvicorn api.main:app``
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth.routes import router as auth_router
from api.dashboard.routes import router as dashboard_router
from api.notifications.routes import message_templates_router, notifications_router
from api.recipients.routes import recipient_lists_router
from api.recipients.routes import teams_router as recipients_teams_router
from api.recipients.routes import users_router as recipients_users_router
from api.routes.health import router as health_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="GrowthTrack API")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Every REST error response uses one envelope: {error: {code, message, details}}
    (Architecture spine, Consistency Conventions)."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code, message, details = detail["code"], detail.get("message", ""), detail.get("details")
    else:
        code, message, details = "http_error", str(detail), None
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Request-body validation failures (422) use the same error envelope."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )

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
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(recipients_users_router)
app.include_router(recipients_teams_router)
app.include_router(recipient_lists_router)
app.include_router(message_templates_router)
app.include_router(notifications_router)
