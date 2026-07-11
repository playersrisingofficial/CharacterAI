import time

from app.automation.oscompat import validate_command
from app.automation.verification import check_expectation
from app.core.safety import classify_step, step_requires_approval


def test_secret_store_returns_ref_not_value(client):
    r = client.post("/api/v1/secrets", json={"name": "app pw", "value": "hunter2"})
    assert r.status_code == 201
    body = r.json()
    assert body["secret_ref"].startswith("secret_")
    assert "hunter2" not in r.text
    # Listing returns refs only.
    assert body["secret_ref"] in client.get("/api/v1/secrets").json()["refs"]


def test_high_risk_actions_listed(client):
    r = client.get("/api/v1/approvals/high-risk-actions")
    assert "credential_entry" in r.json()["high_risk_actions"]


def test_step_classification():
    assert classify_step({"action": "type_secret"}) == "credential_entry"
    assert classify_step({"action": "run_command", "command": "rm -rf /"}) == "run_destructive_command"
    assert classify_step({"action": "click"}) is None
    needs, risk = step_requires_approval({"action": "type_secret"}, {})
    assert needs and risk == "credential_entry"


def test_oscompat_rejects_incompatible():
    assert validate_command("echo -e 'x'", target_os="windows").ok is False
    assert validate_command("dir C:\\", target_os="linux").ok is False
    # /dev/null translated for windows rather than rejected.
    chk = validate_command("cmd > /dev/null", target_os="windows")
    assert chk.ok and "NUL" in chk.translated


def test_verification_requires_condition():
    verified, _ = check_expectation(None, {"screen_text": "hi"})
    assert verified is False  # no declared condition -> not silently successful
    ok, _ = check_expectation({"text_visible": "hi"}, {"screen_text": "say hi there"})
    assert ok is True


def test_approval_gate_blocks_then_grants(client, sample_skill):
    # Skill whose step requires approval (type_secret -> credential_entry).
    skill = dict(sample_skill)
    skill["execution_plan"] = [
        {"step": 1, "action": "focus_window", "target": "AppLogin",
         "expect": {"window_focused": "AppLogin"}},
        {"step": 2, "action": "type_secret", "field": "password",
         "secret_ref": "{{input.password_secret_ref}}", "mode": "machine_speed"},
    ]
    sid = client.post("/api/v1/skills", json=skill).json()["skill_id"]
    ref = client.post("/api/v1/secrets", json={"name": "pw2", "value": "s3cr3t"}).json()["secret_ref"]
    tid = client.post("/api/v1/tasks", json={
        "title": "approval flow",
        "skill_refs": [{"skill_id": sid, "version": 1}],
        "input": {"username": "bob", "password_secret_ref": ref},
    }).json()["task_id"]

    # Wait until it is waiting for approval.
    deadline = time.time() + 8
    pending = []
    while time.time() < deadline:
        pending = client.get("/api/v1/approvals").json()
        if pending:
            break
        time.sleep(0.1)
    assert pending, "expected a pending approval for the secret entry"
    req_id = pending[0]["request_id"]

    client.post(f"/api/v1/approvals/{req_id}/grant")

    # Now it should be able to complete.
    deadline = time.time() + 8
    status = None
    while time.time() < deadline:
        status = client.get(f"/api/v1/tasks/{tid}").json()["status"]
        if status in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert status == "completed"
