"""WhistleDrop application entry point."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models  # noqa: F401  (registers tables on Base)
from app.auth.service import ensure_moderator
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers import auth, moderator, reports
from app.schemas.common import ApiResponse
from app.utils.errors import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("whistledrop")

settings = get_settings()
DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

DESCRIPTION = """
Report wrongdoing **without an account and without revealing who you are**.

**Reporters** submit a report and receive a secret *case code* (e.g. `WD-7K4P9X2M`).
That code is the only thing needed to check the report's status later.

**Moderators** log in, review reports and move them through
`SUBMITTED → UNDER_REVIEW → RESOLVED | DISMISSED`.

### Response format
Success: `{"success": true, "data": {...}}`
Error: `{"success": false, "error": {"code": "...", "message": "...", "details": ...}}`

### Authentication
Call `POST /api/auth/login`, then click **Authorize** and paste the `access_token`.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.moderator_username and settings.moderator_password:
        with SessionLocal() as db:
            if ensure_moderator(db, settings.moderator_username, settings.moderator_password):
                logger.info("Moderator account '%s' created.", settings.moderator_username)
    else:
        logger.warning("No moderator account configured. Run: python -m app.create_moderator --username <name>")
    yield


app = FastAPI(
    title="WhistleDrop — Anonymous Reporting Platform",
    description=DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,  # tokens travel in the Authorization header, not cookies
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"  # report data must not be cached
    if request.url.path.startswith("/dashboard"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
    return response


# ---------- consistent error responses ----------

def _error(status_code: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    body = {"success": False, "error": {"code": code, "message": message, "details": details}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError):
    return _error(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError):
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return _error(400, "malformed_json", "The request body is not valid JSON.")
    # Only the field and the message are returned, never the submitted value.
    details = [
        {"field": ".".join(str(part) for part in e["loc"][1:]) or str(e["loc"][0]), "message": e["msg"]}
        for e in errors
    ]
    return _error(422, "validation_error", "The request is invalid.", details)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_: Request, exc: StarletteHTTPException):
    messages = {404: "Not found.", 405: "Method not allowed."}
    return _error(exc.status_code, f"http_{exc.status_code}", messages.get(exc.status_code, str(exc.detail)))


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception):
    logger.error("Unhandled error: %s", type(exc).__name__)  # no stack trace to clients, no request data in logs
    return _error(500, "internal_error", "Something went wrong on our side.")


# ---------- routes ----------

app.include_router(reports.router)
app.include_router(auth.router)
app.include_router(moderator.router)


@app.get("/api/health", tags=["System"], summary="Health check", response_model=ApiResponse[dict])
def health():
    return {"success": True, "data": {"status": "ok"}}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard/")


app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")
