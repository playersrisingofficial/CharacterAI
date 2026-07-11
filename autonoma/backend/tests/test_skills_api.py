def test_create_and_version_skill(client, sample_skill):
    r = client.post("/api/v1/skills", json=sample_skill)
    assert r.status_code == 201, r.text
    skill = r.json()
    assert skill["version"] == 1
    sid = skill["skill_id"]

    # Update creates a new immutable version.
    updated = dict(sample_skill, description="v2 description")
    r2 = client.put(f"/api/v1/skills/{sid}", json=updated)
    assert r2.status_code == 200
    assert r2.json()["version"] == 2

    # Older version remains retrievable.
    r3 = client.get(f"/api/v1/skills/{sid}/versions/1")
    assert r3.status_code == 200
    assert r3.json()["description"] == "Logs into a desktop application."


def test_invalid_skill_rejected(client):
    r = client.post("/api/v1/skills", json={"name": "bad"})
    assert r.status_code == 400


def test_embedded_secret_rejected(client, sample_skill):
    bad = dict(sample_skill)
    bad["constraints"] = {"password": "hunter2"}
    r = client.post("/api/v1/skills", json=bad)
    assert r.status_code == 400
    assert "secret" in r.text.lower()


def test_status_and_rollback(client, sample_skill):
    sid = client.post("/api/v1/skills", json=sample_skill).json()["skill_id"]
    client.put(f"/api/v1/skills/{sid}", json=dict(sample_skill, description="v2"))
    r = client.post(f"/api/v1/skills/{sid}/rollback", json={"target_version": 1})
    assert r.status_code == 200
    assert r.json()["version"] == 3
    assert r.json()["rolled_back_from"] == 1

    rp = client.patch(f"/api/v1/skills/{sid}/status", json={"status": "archived"})
    assert rp.status_code == 200
    assert rp.json()["status"] == "archived"


def test_soft_delete(client, sample_skill):
    sid = client.post("/api/v1/skills", json=sample_skill).json()["skill_id"]
    r = client.delete(f"/api/v1/skills/{sid}")
    assert r.status_code == 204
    assert client.get(f"/api/v1/skills/{sid}").json()["status"] == "archived"
