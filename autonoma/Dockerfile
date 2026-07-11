# --- Optional frontend build stage (React/Vite SPA) -------------------------
# The backend serves a zero-build static dashboard by default, so this stage is
# only needed if you want the full SPA. If the build fails or is absent, an
# empty dist/ is produced and the backend falls back to the static dashboard.
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/ ./
RUN npm install --no-audit --no-fund 2>/dev/null && npm run build 2>/dev/null || true
RUN mkdir -p /fe/dist

# --- Backend runtime --------------------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/ ./backend/
# Copy the built SPA into the static dir (empty dir if the SPA was not built).
COPY --from=frontend /fe/dist ./backend/app/static/dist

ENV AUTONOMA_DATA_DIR=/data \
    AUTONOMA_AUTOMATION_BACKEND=simulated \
    PYTHONPATH=/app/backend
VOLUME ["/data"]
EXPOSE 8000

# Healthcheck hits the actively-probed liveness endpoint.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)" || exit 1

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
