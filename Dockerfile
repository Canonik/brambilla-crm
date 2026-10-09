# Stage 1: build the SPA when frontend/ exists. A missing or failing UI build never breaks the API image.
FROM node:22.12.0-alpine3.20 AS ui
WORKDIR /ui
COPY . /src
RUN set -e; \
    placeholder() { mkdir -p /ui/dist && printf '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CRM</title></head><body><p>The interface is not built in this image. The API is up at /health.</p></body></html>' > /ui/dist/index.html; }; \
    if [ -f /src/frontend/package.json ]; then \
      cp -r /src/frontend/. /ui/ && rm -rf /ui/node_modules /ui/dist; \
      if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi; \
      (npm run build && test -f /ui/dist/index.html) || { echo "UI BUILD FAILED, shipping placeholder"; placeholder; }; \
    else echo "no frontend/ in context, shipping placeholder"; placeholder; fi

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
