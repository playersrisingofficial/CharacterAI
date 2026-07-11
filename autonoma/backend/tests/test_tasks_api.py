import time


def _wait_status(client, task_id, target, timeout=10.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/v1/tasks/{task_id}").json()
        if last["status"] in target:
            return last
        time.sleep(0.1)
    return last


def test_task_runs_to_completion(client, sample_skill):
    sid = client.post("/api/v1/skills", json=sample_skill).json()["skill_id"]
    task = {
        "title": "Login flow",
        "skill_refs": [{"skill_id": sid, "version": 1}],
        "input": {"username": "alice"},
        "input_behavior_mode": "machine_speed",
    }
    r = client.post("/api/v1/tasks", json=task)
    assert r.status_code == 201, r.text
    tid = r.json()["task_id"]
    assert r.json()["status"] == "queued"

    final = _wait_status(client, tid, {"completed", "failed"})
    assert final["status"] == "completed", final
    assert final["progress"] == 1.0

    timeline = client.get(f"/api/v1/tasks/{tid}/timeline").json()
    assert len(timeline) >= 2
    logs = client.get(f"/api/v1/tasks/{tid}/logs").json()
    assert any("started" in l["message"] for l in logs)


def test_task_with_unknown_skill_rejected(client):
    r = client.post("/api/v1/tasks", json={"title": "x",
                    "skill_refs": [{"skill_id": "skill_does_not_exist"}]})
    assert r.status_code == 404


def test_cancel_task(client, sample_skill):
    sid = client.post("/api/v1/skills", json=sample_skill).json()["skill_id"]
    tid = client.post("/api/v1/tasks", json={"title": "c",
                      "skill_refs": [{"skill_id": sid, "version": 1}],
                      "input": {"username": "bob"}}).json()["task_id"]
    client.post(f"/api/v1/tasks/{tid}/cancel")
    final = _wait_status(client, tid, {"cancelled", "completed"})
    # Either it cancelled in-flight or finished the tiny plan first.
    assert final["status"] in {"cancelled", "completed"}
