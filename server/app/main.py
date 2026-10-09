import logging
import threading
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config, db
from .errors import ApiError, api_error_handler
from .routers import admin, associations, exports, imports, lists, objects, owners, pipelines, properties

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("crm")

app = FastAPI(title="Brambilla CRM", version=config.API_VERSION, docs_url="/__docs", redoc_url=None, openapi_url="/__openapi.json")

PUBLIC_PATHS = {"/health", "/__docs", "/__openapi.json"}


def is_api_path(path: str) -> bool:
    return path.startswith("/crm/") or path.startswith("/__") or path.startswith("/api/") or path.startswith("/health")


class RateCounter:
    def __init__(self):
        self.lock = threading.Lock()
        self.window_start = time.time()
        self.count = 0
        self.daily = 0

    def hit(self) -> tuple[int, int]:
        with self.lock:
            now = time.time()
            if now - self.window_start >= config.RATE_LIMIT_WINDOW_MS / 1000:
                self.window_start = now
                self.count = 0
            self.count += 1
            self.daily += 1
            return self.count, self.daily

    def reset(self):
        with self.lock:
            self.window_start = time.time()
            self.count = 0
            self.daily = 0


rate = RateCounter()


@app.middleware("http")
async def auth_and_limits(request: Request, call_next):
    path = request.url.path
    public = path in PUBLIC_PATHS or path.startswith("/crm/v3/exports/download/") or request.method == "OPTIONS" or (request.method in ("GET", "HEAD") and not is_api_path(path))
    if not public:
        auth = request.headers.get("authorization", "")
        ok = False
        if auth.lower().startswith("bearer "):
            ok = auth[7:].strip() == config.API_TOKEN
        if not ok:
            body = {"status": "error", "message": "Authentication credentials not found. This API supports OAuth 2.0 authentication and you can find more details at https://developers.hubspot.com/docs/methods/auth/oauth-overview", "correlationId": "00000000-0000-0000-0000-000000000000", "category": "INVALID_AUTHENTICATION"}
            return JSONResponse(status_code=401, content=body)
    count, daily = rate.hit()
    if count > config.RATE_LIMIT_MAX and not public and not path.startswith("/__"):
        body = {"status": "error", "message": "You have reached your ten_secondly_rolling limit.", "errorType": "RATE_LIMIT", "correlationId": "00000000-0000-0000-0000-000000000000", "policyName": "TEN_SECONDLY_ROLLING", "category": "RATE_LIMITS"}
        resp = JSONResponse(status_code=429, content=body)
    else:
        resp = await call_next(request)
    resp.headers["X-HubSpot-RateLimit-Daily"] = "1000000"
    resp.headers["X-HubSpot-RateLimit-Daily-Remaining"] = str(max(0, 1000000 - daily))
    resp.headers["X-HubSpot-RateLimit-Interval-Milliseconds"] = str(config.RATE_LIMIT_WINDOW_MS)
    resp.headers["X-HubSpot-RateLimit-Max"] = str(config.RATE_LIMIT_MAX)
    resp.headers["X-HubSpot-RateLimit-Remaining"] = str(max(0, config.RATE_LIMIT_MAX - count))
    resp.headers["X-HubSpot-RateLimit-Secondly"] = str(config.RATE_LIMIT_MAX // 10)
    resp.headers["X-HubSpot-RateLimit-Secondly-Remaining"] = str(max(0, config.RATE_LIMIT_MAX // 10 - count))
    return resp


app.add_exception_handler(ApiError, api_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    err = ApiError(400, "Invalid input JSON: " + "; ".join(str(e.get("msg")) for e in exc.errors()[:3]), "VALIDATION_ERROR")
    return JSONResponse(status_code=400, content=err.body())


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content=ApiError(404, "resource not found", "OBJECT_NOT_FOUND").body())
    if exc.status_code == 405:
        return JSONResponse(status_code=405, content=ApiError(405, "method not allowed", "METHOD_NOT_ALLOWED").body())
    return JSONResponse(status_code=exc.status_code, content=ApiError(exc.status_code, str(exc.detail), "ERROR").body())


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content=ApiError(500, "internal error", "INTERNAL_ERROR").body())


@app.on_event("startup")
def _startup():
    for attempt in range(30):
        try:
            db.init_schema()
            break
        except Exception as e:  # pragma: no cover
            log.warning("db not ready (%s), retrying", e)
            time.sleep(2)
    from .migration.importer import resume_pending
    resume_pending()


app.include_router(admin.router)
app.include_router(objects.router, prefix="/crm/v3/objects")
app.include_router(objects.router, prefix=f"/crm/objects/{config.API_VERSION}")
app.include_router(associations.router)
app.include_router(properties.router, prefix="/crm/v3/properties")
app.include_router(properties.router, prefix=f"/crm/properties/{config.API_VERSION}")
app.include_router(pipelines.router)
app.include_router(lists.router)
app.include_router(owners.router)
app.include_router(exports.router)
app.include_router(imports.router)


# ------------------------------------------------------------------ UI (SPA or placeholder)
import os
from fastapi.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles

_PLACEHOLDER = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Brambilla CRM</title>
<style>body{font-family:system-ui,sans-serif;margin:3rem;color:#222}nav a{margin-right:1rem}</style></head>
<body><h1>Brambilla CRM</h1><p>The interface is being deployed. API is available under <code>/crm/v3</code>.</p>
<nav><a href="/companies">Companies</a><a href="/contacts">Contacts</a><a href="/deals">Deals</a><a href="/tickets">Tickets</a><a href="/dormant">Dormant customers</a><a href="/assistant">Assistant</a></nav>
</body></html>"""


def _dist_dir() -> str | None:
    d = config.FRONTEND_DIST
    if d and os.path.isfile(os.path.join(d, "index.html")):
        return d
    return None


_dist = _dist_dir()
if _dist and os.path.isdir(os.path.join(_dist, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str, request: Request):
    path = "/" + full_path
    if is_api_path(path):
        return JSONResponse(status_code=404, content=ApiError(404, "resource not found", "OBJECT_NOT_FOUND").body())
    dist = _dist_dir()
    if dist:
        candidate = os.path.normpath(os.path.join(dist, full_path))
        if full_path and candidate.startswith(dist) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(dist, "index.html"), media_type="text/html")
    return HTMLResponse(_PLACEHOLDER)
