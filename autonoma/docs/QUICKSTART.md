# Quickstart

## 1. Run the backend

### Local
```bash
cd autonoma/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Docker
```bash
cd autonoma
cp .env.example .env
docker compose up --build
```

Dashboard: **http://localhost:8000/** · API docs: **http://localhost:8000/docs**

## 2. Seed example data
```bash
BASE=http://localhost:8000 ./examples/seed.sh
```
Creates `LoginToApp` + `FillContactForm` skills, stores a demo secret (you get a
`secret_ref`, never the raw value), and starts a login task.

## 3. Watch it run
Open the dashboard. You'll see:
- **Task Monitor** — live cards with status, current step, skill/version, behavior
  mode, last/next action, progress.
- **Agents** — status, roles, and which agent holds the input lock.
- **Approvals** — the login task pauses at `login_submit`; approve it to continue.
- **Live Audit & Activity Feed** — every step, verified ✓ or ⚠unverified, streamed
  over WebSocket.

## 4. Try the controls
- Change **Agents** to 2–3 to enable multi-agent coordination (input lock + queue).
- Designate a **watchdog**: `POST /api/v1/agents/agent_003/watchdog {"assign": true}`.
- Switch **Inference Mode** and watch the Hardware Requirements panel recompute.
- Switch **Input mode** (human-like ↔ machine-speed) before creating a task.

## 5. Create your own skill
```bash
curl -X POST http://localhost:8000/api/v1/skills \
  -H 'Content-Type: application/json' \
  --data-binary @examples/skills/fill_contact_form.json
```
Then create a task referencing `skill_id + version`. See [API.md](API.md).

## Common environment toggles
| Variable | Effect |
|---|---|
| `AUTONOMA_AUTOMATION_BACKEND=desktop` | Use real mouse/keyboard (needs display + `pip install pyautogui`) |
| `AUTONOMA_VAULT_KEY=...` | Persist encrypted secrets across restarts |
| `AUTONOMA_SESSION_COST_CEILING=5.0` | Cap per-session API spend at $5 |
| `AUTONOMA_WORK_DIR=/path/to/project` | Scope any file-access skill to one folder |
| `AUTONOMA_SIM_STEP_SECONDS=0.1` | Speed up the simulated backend for demos/tests |
