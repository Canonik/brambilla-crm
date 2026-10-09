import json
import os


def _env(*names: str, default: str | None = None) -> str | None:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default


DATABASE_URL = _env("DATABASE_URL", "POSTGRES_URL", default="postgresql://brambilla:brambilla@127.0.0.1:5433/brambilla")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

API_TOKEN = _env("CRM_TOKEN", "API_TOKEN", "HUBSPOT_TOKEN", "TOKEN", default="dev-token")
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY", default="")
OPENROUTER_MODEL = _env("OPENROUTER_MODEL", default="openai/gpt-6-luna")
OPENROUTER_URL = _env("OPENROUTER_URL", default="https://openrouter.ai/api/v1/chat/completions")
API_VERSION = "2026-09"
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", "RAILWAY_PUBLIC_DOMAIN", default="")
if PUBLIC_BASE_URL and not PUBLIC_BASE_URL.startswith("http"):
    PUBLIC_BASE_URL = "https://" + PUBLIC_BASE_URL

_default_ui = {
    "companies": "/companies",
    "contacts": "/contacts",
    "deals": "/deals",
    "tickets": "/tickets",
    "lists": "/dormant",
    "assistant": "/assistant",
}
FRONTEND_DIST = _env("FRONTEND_DIST", default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")))
try:
    UI_ROUTES = json.loads(_env("UI_ROUTES_JSON", default="") or "null") or _default_ui
except Exception:
    UI_ROUTES = _default_ui

RATE_LIMIT_MAX = int(_env("RATE_LIMIT_MAX", default="2000"))
RATE_LIMIT_WINDOW_MS = 10_000
POOL_MIN = int(_env("DB_POOL_MIN", default="2"))
POOL_MAX = int(_env("DB_POOL_MAX", default="24"))
