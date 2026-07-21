"""Change-draft state machine (demo scope: CONFIG_EDIT operation type only,
per de-demo/DESIGN.md §S7 / §5 risk register: "other op types = enum +
allowlist table present but UI-exposed only for CONFIG_EDIT").

State machine (simplified per this build's task brief; a normalized subset of
docs/60-console/design.md's full MATERIALIZING/DIFF_READY/... pipeline):

    DRAFT --validate--> VALIDATING --> VALIDATED --(fail)--> DRAFT
    VALIDATED --build-test--> BUILD_TESTED --(fail)--> DRAFT
    BUILD_TESTED --create-mr--> MR_CREATED

Every transition is isolated: draft edits are held in the `drafts.files`
column (path -> new content) until validate/build-test time, at which point
the console copies the *real* instance directory (minus the build-output
`runtime/` and `editor/` dirs) into a throwaway temp workspace, applies the
draft's file edits there, rewrites the workspace-relative
`file://../../{scaffold,skills}` registry URLs to absolute paths (so
`./de` resolves them regardless of where the temp workspace lives), and runs
`<repo>/scaffold/de validate|build .` inside that workspace only. The real
instance tree is never touched. Every transition writes an `audit_events`
row.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .config import Config
from .db import Database, dumps, loads, row_to_dict
from .providers import MockMRProvider

# --- operation types & allowlists ------------------------------------------

OP_CONFIG_EDIT = "CONFIG_EDIT"
OP_SKILL_ADD = "SKILL_ADD"
OP_SKILL_REMOVE = "SKILL_REMOVE"
OP_SKILL_UPDATE = "SKILL_UPDATE"
OP_SCAFFOLD_UPGRADE = "SCAFFOLD_UPGRADE"
OP_ROLLBACK = "ROLLBACK"

# Demo UI only exposes CONFIG_EDIT (docs/60-console §"Operation Types");
# the other types are recognized here (allowlist table present) but the API
# rejects drafts of any other type for this build's scope.
UI_EXPOSED_OP_TYPES = {OP_CONFIG_EDIT}

_SKILL_FILES = {".gitignore", "skills.yaml", "skills-lock.json"}

OPERATION_ALLOWLISTS: dict[str, set[str]] = {
    OP_CONFIG_EDIT: {".gitignore", "instance.yaml"},
    OP_SKILL_ADD: set(_SKILL_FILES),
    OP_SKILL_REMOVE: set(_SKILL_FILES),
    OP_SKILL_UPDATE: set(_SKILL_FILES),
    OP_SCAFFOLD_UPGRADE: {
        "instance.yaml", ".github/workflows/instance-ci.yml", "Makefile", "de",
        "VERSION", "skills.yaml", "skills-lock.json",
    },
}
OPERATION_ALLOWLISTS[OP_ROLLBACK] = set().union(*OPERATION_ALLOWLISTS.values())

# This build's demo CONFIG_EDIT allowlist additionally covers the console
# task brief's explicit list (kb/team/**, .env.example, README.md) beyond the
# design doc's bare-bones `.gitignore`/`instance.yaml` pair -- documented
# widening, not a narrowing, of the spec's table.
CONFIG_EDIT_EXTRA_PREFIXES = ("kb/team/",)
CONFIG_EDIT_EXTRA_FILES = {".env.example", "README.md", "skills.yaml"}
OPERATION_ALLOWLISTS[OP_CONFIG_EDIT] |= CONFIG_EDIT_EXTRA_FILES

# Always-forbidden set (docs/60-console §"Always-forbidden set"): exact-or-prefix.
FORBIDDEN_PREFIXES = (
    "runtime/",
    ".env",  # .env* -- but .env.example is explicitly allowed, checked separately
    ".claude/policy/",
    ".claude/hooks/",
    "commands/",
    "agents/",
    "tools/",
)


def is_forbidden(path: str) -> bool:
    if path == ".env.example":
        return False
    for prefix in FORBIDDEN_PREFIXES:
        # docs/60-console §"Always-forbidden set": match is exact-or-prefix
        # against the blocked string with its trailing slash stripped, so
        # e.g. ".claude/policy-overrides.yaml" is blocked by the
        # ".claude/policy/" entry too, not just files literally under that
        # directory (the spec's own worked example).
        bare = prefix.rstrip("/")
        if path == bare or path.startswith(bare):
            return True
    return False


def is_allowed(operation_type: str, path: str) -> bool:
    if is_forbidden(path):
        return False
    if path == "VERSION":
        return operation_type == OP_SCAFFOLD_UPGRADE
    allowlist = OPERATION_ALLOWLISTS.get(operation_type, set())
    if path in allowlist:
        return True
    if operation_type == OP_CONFIG_EDIT:
        return any(path.startswith(p) for p in CONFIG_EDIT_EXTRA_PREFIXES)
    if operation_type == OP_ROLLBACK:
        return any(path.startswith(p) for p in CONFIG_EDIT_EXTRA_PREFIXES)
    return False


class AllowlistError(ValueError):
    pass


class TransitionError(ValueError):
    pass


STATE_DRAFT = "DRAFT"
STATE_VALIDATING = "VALIDATING"
STATE_VALIDATED = "VALIDATED"
STATE_BUILDING = "BUILD_TESTING"
STATE_BUILD_TESTED = "BUILD_TESTED"
STATE_MR_CREATED = "MR_CREATED"


class DraftService:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self.mr_provider = MockMRProvider(config.repo_root)

    # -- audit --------------------------------------------------------------
    def _audit(
        self,
        *,
        instance_id: str,
        draft_id: str,
        action: str,
        status: str,
        from_state: str | None,
        to_state: str | None,
        actor_email: str = "console-demo@local",
        actor_name: str = "Console Demo User",
        error: str | None = None,
        metadata: dict | None = None,
        route: str | None = None,
        method: str | None = None,
    ) -> None:
        self.db.execute(
            """INSERT INTO audit_events (event_id, instance_id, draft_id, action, status,
                actor_email, actor_name, actor_id, from_state, to_state, request_id, route,
                method, permission_source, error, metadata, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))""",
            (
                str(uuid.uuid4()), instance_id, draft_id, action, status,
                actor_email, actor_name, actor_email, from_state, to_state,
                str(uuid.uuid4()), route, method, "demo-fixed-actor", error,
                dumps(metadata or {}),
            ),
        )

    # -- CRUD -----------------------------------------------------------------
    def create_draft(self, instance_id: str, operation_type: str, actor_email: str = "console-demo@local", actor_name: str = "Console Demo User") -> dict:
        if operation_type not in UI_EXPOSED_OP_TYPES:
            raise TransitionError(
                f"operation_type {operation_type!r} is recognized but not UI-exposed in this demo build "
                f"(scope limited to {sorted(UI_EXPOSED_OP_TYPES)})"
            )
        instance_dir = self.config.instances_dir / instance_id
        if not instance_dir.is_dir():
            raise TransitionError(f"unknown instance: {instance_id}")

        draft_id = str(uuid.uuid4())
        base_commit = self._repo_head()
        self.db.execute(
            """INSERT INTO drafts (draft_id, instance_id, state, operation_type, target_branch,
                base_commit, payload, files, created_by_email, created_by_name,
                updated_by_email, updated_by_name, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'), datetime('now'))""",
            (
                draft_id, instance_id, STATE_DRAFT, operation_type,
                f"console/draft-{draft_id}", base_commit, dumps({}), dumps({}),
                actor_email, actor_name, actor_email, actor_name,
            ),
        )
        self._audit(
            instance_id=instance_id, draft_id=draft_id, action="DRAFT_CREATE",
            status="Succeeded", from_state=None, to_state=STATE_DRAFT,
            actor_email=actor_email, actor_name=actor_name,
        )
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,))
        return self._deserialize(row)

    def list_drafts(self, instance_id: str | None = None) -> list[dict]:
        if instance_id:
            rows = self.db.query(
                "SELECT * FROM drafts WHERE instance_id = ? ORDER BY updated_at DESC", (instance_id,)
            )
        else:
            rows = self.db.query("SELECT * FROM drafts ORDER BY updated_at DESC")
        return [self._deserialize(r) for r in rows]

    @staticmethod
    def _deserialize(row) -> dict | None:
        d = row_to_dict(row)
        if d is None:
            return None
        d["payload"] = loads(d.get("payload"), {})
        d["files"] = loads(d.get("files"), {})
        return d

    def _require_draft(self, draft_id: str) -> dict:
        d = self.get_draft(draft_id)
        if d is None:
            raise TransitionError(f"unknown draft: {draft_id}")
        return d

    def _repo_head(self) -> str:
        try:
            r = subprocess.run(
                ["git", "-C", str(self.config.repo_root), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            )
            return r.stdout.strip()
        except Exception:
            return ""

    # -- file editing ---------------------------------------------------------
    def set_files(self, draft_id: str, files: dict[str, str], actor_email: str = "console-demo@local", actor_name: str = "Console Demo User") -> dict:
        draft = self._require_draft(draft_id)
        if draft["state"] not in (STATE_DRAFT,):
            raise TransitionError(f"cannot edit files while draft is in state {draft['state']}")

        op_type = draft["operation_type"]
        for path in files:
            if not is_allowed(op_type, path):
                self._audit(
                    instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_FILE_ADD",
                    status="Failed", from_state=draft["state"], to_state=draft["state"],
                    actor_email=actor_email, actor_name=actor_name,
                    error=f"path not allowed for operation {op_type}: {path}",
                    metadata={"path": path},
                )
                raise AllowlistError(f"path {path!r} is not allowed for operation type {op_type}")

        merged = dict(draft["files"])
        merged.update(files)
        self.db.execute(
            "UPDATE drafts SET files = ?, updated_by_email = ?, updated_by_name = ?, updated_at = datetime('now') WHERE draft_id = ?",
            (dumps(merged), actor_email, actor_name, draft_id),
        )
        self._audit(
            instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_FILE_ADD",
            status="Succeeded", from_state=draft["state"], to_state=draft["state"],
            actor_email=actor_email, actor_name=actor_name, metadata={"paths": list(files.keys())},
        )
        return self.get_draft(draft_id)

    # -- isolated workspace -----------------------------------------------------
    def _materialize_workspace(self, draft: dict) -> Path:
        instance_dir = self.config.instances_dir / draft["instance_id"]
        workspace_root = self.config.workspaces_dir
        workspace_root.mkdir(parents=True, exist_ok=True)
        ws = Path(tempfile.mkdtemp(prefix=f"draft-{draft['draft_id']}-", dir=str(workspace_root)))

        def _ignore(dirpath, names):
            if Path(dirpath) == instance_dir:
                return [n for n in names if n in ("runtime", "editor")]
            return []

        shutil.copytree(instance_dir, ws, dirs_exist_ok=True, ignore=_ignore)

        # Rewrite depth-relative registry URLs so `./de` resolves them from
        # the temp workspace's location rather than instances/<id>'s.
        for fname in ("instance.yaml", "skills.yaml"):
            fp = ws / fname
            if fp.is_file():
                text = fp.read_text()
                new_text = re.sub(r"file://\.\./\.\./", f"file://{self.config.repo_root}/", text)
                if new_text != text:
                    fp.write_text(new_text)

        for path, content in draft["files"].items():
            target = ws / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)

        return ws

    def _run_de(self, ws: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.config.de_cli), *args, str(ws)],
            cwd=str(self.config.repo_root),
            capture_output=True,
            text=True,
            timeout=180,
        )

    def _cleanup_workspace(self, ws: Path) -> None:
        shutil.rmtree(ws, ignore_errors=True)

    # -- transitions ------------------------------------------------------------
    def validate(self, draft_id: str, actor_email: str = "console-demo@local", actor_name: str = "Console Demo User") -> dict:
        draft = self._require_draft(draft_id)
        if draft["state"] != STATE_DRAFT:
            raise TransitionError(f"validate requires state DRAFT, got {draft['state']}")

        self._set_state(draft_id, STATE_VALIDATING)
        self._audit(
            instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_VALIDATE",
            status="Started", from_state=STATE_DRAFT, to_state=STATE_VALIDATING,
            actor_email=actor_email, actor_name=actor_name,
        )

        ws = self._materialize_workspace(draft)
        try:
            result = self._run_de(ws, "validate")
            ok = result.returncode == 0
            new_state = STATE_VALIDATED if ok else STATE_DRAFT
            self._set_state(draft_id, new_state)
            self._audit(
                instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_VALIDATE",
                status="Succeeded" if ok else "Failed",
                from_state=STATE_VALIDATING, to_state=new_state,
                actor_email=actor_email, actor_name=actor_name,
                error=None if ok else (result.stdout + result.stderr)[-4000:],
                metadata={"returncode": result.returncode},
            )
            if not ok:
                raise TransitionError(f"validate failed: {(result.stdout + result.stderr)[-2000:]}")
            return self.get_draft(draft_id)
        finally:
            self._cleanup_workspace(ws)

    def build_test(self, draft_id: str, actor_email: str = "console-demo@local", actor_name: str = "Console Demo User") -> dict:
        draft = self._require_draft(draft_id)
        if draft["state"] != STATE_VALIDATED:
            raise TransitionError(f"build-test requires state VALIDATED, got {draft['state']}")

        self._set_state(draft_id, STATE_BUILDING)
        self._audit(
            instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_BUILD_TEST",
            status="Started", from_state=STATE_VALIDATED, to_state=STATE_BUILDING,
            actor_email=actor_email, actor_name=actor_name,
        )

        ws = self._materialize_workspace(draft)
        try:
            result = self._run_de(ws, "build")
            ok = result.returncode == 0
            new_state = STATE_BUILD_TESTED if ok else STATE_DRAFT
            self._set_state(draft_id, new_state)
            self._audit(
                instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_BUILD_TEST",
                status="Succeeded" if ok else "Failed",
                from_state=STATE_BUILDING, to_state=new_state,
                actor_email=actor_email, actor_name=actor_name,
                error=None if ok else (result.stdout + result.stderr)[-4000:],
                metadata={"returncode": result.returncode},
            )
            if not ok:
                raise TransitionError(f"build-test failed: {(result.stdout + result.stderr)[-2000:]}")
            return self.get_draft(draft_id)
        finally:
            self._cleanup_workspace(ws)

    def create_mr(self, draft_id: str, actor_email: str = "console-demo@local", actor_name: str = "Console Demo User") -> dict:
        draft = self._require_draft(draft_id)
        if draft["state"] != STATE_BUILD_TESTED:
            raise TransitionError(f"create-mr requires state BUILD_TESTED, got {draft['state']}")

        try:
            mr = self.mr_provider.create_mr(draft_id, draft["instance_id"])
        except subprocess.CalledProcessError as exc:
            self._audit(
                instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_CREATE_MR",
                status="Failed", from_state=STATE_BUILD_TESTED, to_state=STATE_BUILD_TESTED,
                actor_email=actor_email, actor_name=actor_name, error=exc.stderr,
            )
            raise TransitionError(f"mock MR creation failed: {exc.stderr}") from exc

        self.db.execute(
            """UPDATE drafts SET state = ?, mr_iid = ?, mr_url = ?, target_branch = ?,
               updated_by_email = ?, updated_by_name = ?, updated_at = datetime('now')
               WHERE draft_id = ?""",
            (STATE_MR_CREATED, mr["mr_iid"], mr["mr_url"], mr["branch"], actor_email, actor_name, draft_id),
        )
        self._audit(
            instance_id=draft["instance_id"], draft_id=draft_id, action="DRAFT_CREATE_MR",
            status="Succeeded", from_state=STATE_BUILD_TESTED, to_state=STATE_MR_CREATED,
            actor_email=actor_email, actor_name=actor_name, metadata=mr,
        )
        return self.get_draft(draft_id)

    def _set_state(self, draft_id: str, state: str) -> None:
        self.db.execute(
            "UPDATE drafts SET state = ?, updated_at = datetime('now') WHERE draft_id = ?",
            (state, draft_id),
        )
