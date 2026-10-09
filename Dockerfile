# Stage 1: build the SPA. A failing UI build must never break the API image.
FROM node:22.12.0-alpine3.20 AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi
COPY frontend/ ./
RUN npm run build || (echo "UI BUILD FAILED, shipping placeholder" && mkdir -p dist && printf '<!doctype html><title>CRM</title><p>UI build failed. API is up at /health.</p>' > dist/index.html)

# Stage 2: the service.
FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
COPY server/ server/
COPY --from=ui /ui/dist frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "if [ -f server/main.py ]; then M=server.main:app; else M=server.app.main:app; fi; exec uvicorn $M --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
