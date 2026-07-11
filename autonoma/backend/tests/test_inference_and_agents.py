def test_inference_options_and_requirements(client):
    r = client.get("/api/v1/inference-mode/options?agents=2")
    assert r.status_code == 200
    body = r.json()
    modes = {m["mode"] for m in body["modes"]}
    assert modes == {"local", "api_based", "hybrid"}
    # Requirements scale with agent count.
    one = client.get("/api/v1/inference-mode/requirements?mode=local&agents=1").json()
    three = client.get("/api/v1/inference-mode/requirements?mode=local&agents=3").json()
    assert three["min_ram_gb"] > one["min_ram_gb"]


def test_disallowed_endpoint_type_rejected(client):
    r = client.post("/api/v1/inference-mode", json={
        "inference_mode": "api_based",
        "api_config": {"provider": "x", "model": "y", "endpoint_type": "computer_use"},
    })
    assert r.status_code == 400
    assert "bypass" in r.text.lower() or "disallowed" in r.text.lower()


def test_multimodal_endpoint_allowed(client):
    r = client.post("/api/v1/inference-mode", json={
        "inference_mode": "api_based",
        "api_config": {"provider": "x", "model": "y",
                       "endpoint_type": "multimodal_completion", "requires_network": True},
    })
    assert r.status_code == 200
    assert r.json()["inference_mode"] == "api_based"


def test_agent_config_and_watchdog(client):
    r = client.post("/api/v1/agents/config", json={"count": 3})
    assert r.status_code == 200
    assert r.json()["active_agent_count"] == 3

    r2 = client.post("/api/v1/agents/agent_003/watchdog", json={"assign": True})
    assert r2.status_code == 200
    assert r2.json()["agent"]["role"] == "watchdog"

    lock = client.get("/api/v1/agents/input-lock").json()
    assert "holder" in lock


def test_health_is_actively_checked(client):
    r = client.get("/api/v1/monitor/health")
    assert r.status_code == 200
    body = r.json()
    assert "checked_at" in body
    assert body["backend"]["online"] is True
