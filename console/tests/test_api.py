def test_list_instances_includes_acme(app_client):
    resp = app_client.get("/api/instances")
    assert resp.status_code == 200
    body = resp.json()
    ids = [i["instance_id"] for i in body["instances"]]
    assert "acme-checkout-sre" in ids
    acme = next(i for i in body["instances"] if i["instance_id"] == "acme-checkout-sre")
    assert acme["health"]["score"] >= 85
    assert acme["health"]["status"] in ("healthy", "warn")


def test_get_instance_detail(app_client):
    resp = app_client.get("/api/instances/acme-checkout-sre")
    assert resp.status_code == 200
    body = resp.json()
    assert body["managed_files"]
    assert body["ci"]["available"] is True


def test_get_unknown_instance_404(app_client):
    resp = app_client.get("/api/instances/does-not-exist")
    assert resp.status_code == 404


def test_draft_file_add_rejects_forbidden_path_via_api(app_client):
    resp = app_client.post("/api/drafts", json={"instance_id": "acme-checkout-sre", "operation_type": "CONFIG_EDIT"})
    assert resp.status_code == 200
    draft_id = resp.json()["draft_id"]
    resp2 = app_client.put(f"/api/drafts/{draft_id}/files", json={"files": {".claude/policy/security.yaml": "x: 1\n"}})
    assert resp2.status_code == 422


def test_health_liveness(app_client):
    resp = app_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_frontend_served(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert b"DE Fleet Governance Console" in resp.content
