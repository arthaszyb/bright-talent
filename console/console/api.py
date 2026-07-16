"""REST API + static frontend hosting (docs/60-console/design.md §"API Surface",
simplified per this build's task brief)."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import health
from .config import Config
from .db import Database, loads, row_to_dict
from .drafts import AllowlistError, DraftService, TransitionError
from .providers import MockCIProvider
from .repo_scan import RepoScanner

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class CreateDraftRequest(BaseModel):
    instance_id: str
    operation_type: str = "CONFIG_EDIT"
    actor_email: str | None = None
    actor_name: str | None = None


class SetFilesRequest(BaseModel):
    files: dict[str, str]
    actor_email: str | None = None
    actor_name: str | None = None


class ActorRequest(BaseModel):
    actor_email: str | None = None
    actor_name: str | None = None


def build_app(config: Config) -> FastAPI:
    app = FastAPI(title="DE Fleet Governance Console")
    db = Database(config.resolved_db_path)
    scanner = RepoScanner(config)
    ci_provider = MockCIProvider()
    drafts = DraftService(config, db)

    def _instance_ci(instance_id: str) -> dict[str, Any]:
        instance_dir = config.instances_dir / instance_id
        return ci_provider.instance_ci(instance_dir)

    def _instance_view(instance_id: str, force: bool = False) -> dict[str, Any]:
        scan = scanner.scan_instance(instance_id, force=force)
        ci = _instance_ci(instance_id)
        ev = health.evaluate(scan, ci)
        return {
            "instance_id": instance_id,
            "identity": scan["identity"],
            "scope": scan["scope"],
            "version": scan["version"],
            "base": scan["base"],
            "health": {"score": ev["score"], "status": ev["status"], "color": ev["color"], "label": ev["label"], "deductions": ev["deductions"]},
            "ci": ci,
            "managed_files": scan["managed_files"],
            "unmanaged_drift": scan["unmanaged_drift"],
            "skills": scan["skills"],
            "files": scan["files"],
            "scanned_at": scan["scanned_at"],
        }

    # -- static frontend -----------------------------------------------------
    @app.get("/")
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    if FRONTEND_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    # -- health/liveness ------------------------------------------------------
    @app.get("/api/health")
    def api_health():
        return {"status": "ok", "time": time.time()}

    # -- instances --------------------------------------------------------------
    @app.get("/api/instances")
    def list_instances(refresh: bool = False):
        out = []
        for instance_id in scanner.list_instance_ids():
            out.append(_instance_view(instance_id, force=refresh))
        return {"instances": out}

    @app.get("/api/instances/{instance_id}")
    def get_instance(instance_id: str, refresh: bool = False):
        if instance_id not in scanner.list_instance_ids():
            raise HTTPException(404, f"unknown instance: {instance_id}")
        return _instance_view(instance_id, force=refresh)

    # -- skills -----------------------------------------------------------------
    @app.get("/api/skills")
    def list_skills():
        skills_dir = config.skills_dir
        tags: list[str] = []
        try:
            r = subprocess.run(
                ["git", "-C", str(skills_dir), "tag", "-l"],
                check=True, capture_output=True, text=True,
            )
            tags = [t for t in r.stdout.splitlines() if t.strip()]
        except Exception:
            pass
        ci = ci_provider.skills_ci(skills_dir)
        instances_using: dict[str, list[str]] = {}
        for instance_id in scanner.list_instance_ids():
            scan = scanner.scan_instance(instance_id)
            for s in scan["skills"]:
                instances_using.setdefault(s["name"], []).append(instance_id)
        return {"repo": str(skills_dir), "tags": tags, "ci": ci, "installed_by_instance": instances_using}

    # -- drafts -------------------------------------------------------------------
    @app.post("/api/drafts")
    def create_draft(req: CreateDraftRequest):
        try:
            return drafts.create_draft(
                req.instance_id, req.operation_type,
                actor_email=req.actor_email or "console-demo@local",
                actor_name=req.actor_name or "Console Demo User",
            )
        except TransitionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/drafts")
    def list_drafts(instance_id: str | None = None):
        return {"drafts": drafts.list_drafts(instance_id)}

    @app.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: str):
        d = drafts.get_draft(draft_id)
        if d is None:
            raise HTTPException(404, f"unknown draft: {draft_id}")
        return d

    @app.put("/api/drafts/{draft_id}/files")
    def set_files(draft_id: str, req: SetFilesRequest):
        try:
            return drafts.set_files(
                draft_id, req.files,
                actor_email=req.actor_email or "console-demo@local",
                actor_name=req.actor_name or "Console Demo User",
            )
        except AllowlistError as exc:
            raise HTTPException(422, str(exc)) from exc
        except TransitionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/drafts/{draft_id}/validate")
    def validate_draft(draft_id: str, req: ActorRequest = ActorRequest()):
        try:
            return drafts.validate(
                draft_id,
                actor_email=req.actor_email or "console-demo@local",
                actor_name=req.actor_name or "Console Demo User",
            )
        except TransitionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/drafts/{draft_id}/build-test")
    def build_test_draft(draft_id: str, req: ActorRequest = ActorRequest()):
        try:
            return drafts.build_test(
                draft_id,
                actor_email=req.actor_email or "console-demo@local",
                actor_name=req.actor_name or "Console Demo User",
            )
        except TransitionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/drafts/{draft_id}/create-mr")
    def create_mr_draft(draft_id: str, req: ActorRequest = ActorRequest()):
        try:
            return drafts.create_mr(
                draft_id,
                actor_email=req.actor_email or "console-demo@local",
                actor_name=req.actor_name or "Console Demo User",
            )
        except TransitionError as exc:
            raise HTTPException(400, str(exc)) from exc

    # -- audit ------------------------------------------------------------------
    @app.get("/api/audit")
    def list_audit(instance_id: str | None = None, draft_id: str | None = None, limit: int = 200):
        sql = "SELECT * FROM audit_events"
        clauses = []
        params: list[Any] = []
        if instance_id:
            clauses.append("instance_id = ?")
            params.append(instance_id)
        if draft_id:
            clauses.append("draft_id = ?")
            params.append(draft_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = db.query(sql, params)
        events = []
        for r in rows:
            d = row_to_dict(r)
            d["metadata"] = loads(d.get("metadata"), {})
            events.append(d)
        return {"events": events}

    return app
