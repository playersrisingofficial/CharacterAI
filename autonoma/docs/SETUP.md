# Setup Guide

## Requirements
- Python 3.11+
- (Optional) Node 20+ to build the React SPA
- (Optional) Docker 24+ for containerized deployment

## Local install
```bash
cd autonoma/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000        # add --reload for development
```
Configuration is via environment variables — see [`.env.example`](../.env.example).
Nothing is required to start; defaults are safe (simulated automation backend,
ephemeral vault key, no cost ceiling).

## Automation backends
| Backend | Selected by | Behavior |
|---|---|---|
| `simulated` (default) | `AUTONOMA_AUTOMATION_BACKEND=simulated` | No real OS input. Models timing, verification, retries, and the virtual screen so everything is runnable headless (CI/Docker). |
| `desktop` | `AUTONOMA_AUTOMATION_BACKEND=desktop` + `pip install pyautogui` | Drives real mouse/keyboard. Requires a display. Inherits the same verification/OS-command safety semantics. |

## Secret vault
Set a strong master key to persist encrypted secrets across restarts:
```bash
export AUTONOMA_VAULT_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
```
Without it, a process-local key is generated and secrets do not survive a
restart. If the `cryptography` package is installed it is used automatically;
otherwise an authenticated stream cipher derived from the master key is used.

## Docker
```bash
cd autonoma
cp .env.example .env
docker compose up --build
```
- App: http://localhost:8000/
- Data (SQLite + vault) persists in the `autonoma-data` volume.
- The image runs the `simulated` backend by default. Real desktop automation
  from inside a container is generally not appropriate; run the `desktop`
  backend on the target host instead (see below).

### Local / Hybrid inference model storage
API-Based mode needs no local model storage. For **Local** or **Hybrid** mode,
mount your model weights and point the app at them:
```yaml
# docker-compose.yml
    volumes:
      - ./models:/models:ro
    environment:
      AUTONOMA_MODELS_DIR: /models
      AUTONOMA_LOCAL_INFERENCE_ENDPOINT: http://host.docker.internal:11434
```
The health endpoint actively probes `AUTONOMA_LOCAL_INFERENCE_ENDPOINT` and
reports it offline if unreachable (never an assumed-up flag).

## Desktop worker (real automation)
Because desktop automation controls the physical cursor/keyboard, run it on the
machine you want automated:
```bash
AUTONOMA_AUTOMATION_BACKEND=desktop pip install pyautogui
AUTONOMA_AUTOMATION_BACKEND=desktop uvicorn app.main:app --port 8000
```
The cloud/container deployment can host the API and dashboard while a local
worker performs input; both speak the same API.

## React SPA (optional)
```bash
cd autonoma/frontend
npm install
npm run build          # outputs to frontend/dist
```
Copy `frontend/dist` to `backend/app/static/dist` (or let the Dockerfile do it)
and the backend serves the SPA at `/` instead of the zero-build dashboard.
During development, `npm run dev` proxies `/api` and WebSockets to `:8000`.

## Tests
```bash
cd autonoma/backend
pip install pytest
pytest
```
