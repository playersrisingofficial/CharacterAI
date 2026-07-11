#!/usr/bin/env bash
# Seed a running Autonoma instance with example skills, a secret, and a task.
# Usage: BASE=http://127.0.0.1:8000 ./examples/seed.sh
set -euo pipefail
BASE="${BASE:-http://127.0.0.1:8000}"
HERE="$(cd "$(dirname "$0")" && pwd)"

json() { python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }

echo "Creating LoginToApp skill..."
SID=$(curl -s -X POST "$BASE/api/v1/skills" -H 'Content-Type: application/json' \
  --data-binary @"$HERE/skills/login_to_app.json" | json "['skill_id']")
echo "  skill_id=$SID"

echo "Creating FillContactForm skill..."
curl -s -X POST "$BASE/api/v1/skills" -H 'Content-Type: application/json' \
  --data-binary @"$HERE/skills/fill_contact_form.json" >/dev/null

echo "Storing a demo password secret (returns a reference, never the value)..."
REF=$(curl -s -X POST "$BASE/api/v1/secrets" -H 'Content-Type: application/json' \
  -d '{"name":"app pw","value":"demo-password"}' | json "['secret_ref']")
echo "  secret_ref=$REF"

echo "Creating a login task (will pause for approval at login_submit)..."
TID=$(curl -s -X POST "$BASE/api/v1/tasks" -H 'Content-Type: application/json' \
  -d "{\"title\":\"Log into desktop app\",\"skill_refs\":[{\"skill_id\":\"$SID\",\"version\":1}],
       \"input\":{\"username\":\"example_user\",\"password_secret_ref\":\"$REF\"},
       \"input_behavior_mode\":\"human_like\"}" | json "['task_id']")
echo "  task_id=$TID"
echo
echo "Open the dashboard at $BASE/ — approve the pending high-risk action to continue."
