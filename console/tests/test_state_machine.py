import shutil

import pytest

from console.drafts import (
    STATE_BUILD_TESTED,
    STATE_DRAFT,
    STATE_MR_CREATED,
    STATE_VALIDATED,
    AllowlistError,
    DraftService,
    TransitionError,
)

INSTANCE_ID = "acme-checkout-sre"


@pytest.fixture()
def service(config, db):
    svc = DraftService(config, db)
    yield svc
    if config.workspaces_dir.exists():
        shutil.rmtree(config.workspaces_dir, ignore_errors=True)


def test_create_draft_starts_in_draft_state(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    assert d["state"] == STATE_DRAFT
    assert d["operation_type"] == "CONFIG_EDIT"
    assert d["instance_id"] == INSTANCE_ID


def test_create_draft_rejects_non_ui_exposed_op_type(service):
    with pytest.raises(TransitionError):
        service.create_draft(INSTANCE_ID, "SCAFFOLD_UPGRADE")


def test_create_draft_rejects_unknown_instance(service):
    with pytest.raises(TransitionError):
        service.create_draft("no-such-instance", "CONFIG_EDIT")


def test_set_files_rejects_forbidden_path(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    with pytest.raises(AllowlistError):
        service.set_files(d["draft_id"], {".claude/policy/security.yaml": "x: 1\n"})


def test_set_files_rejects_runtime_path(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    with pytest.raises(AllowlistError):
        service.set_files(d["draft_id"], {"runtime/CLAUDE.md": "hacked"})


def test_set_files_accepts_kb_team_path(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    updated = service.set_files(d["draft_id"], {"kb/team/ok.md": "# ok\n"})
    assert "kb/team/ok.md" in updated["files"]


def test_cannot_build_test_before_validated(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    service.set_files(d["draft_id"], {"kb/team/ok.md": "# ok\n"})
    with pytest.raises(TransitionError):
        service.build_test(d["draft_id"])


def test_cannot_create_mr_before_build_tested(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    with pytest.raises(TransitionError):
        service.create_mr(d["draft_id"])


def test_cannot_validate_twice_without_returning_to_draft(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    service.set_files(d["draft_id"], {"kb/team/ok.md": "# ok\n"})
    service.validate(d["draft_id"])
    with pytest.raises(TransitionError):
        service.validate(d["draft_id"])


def test_full_happy_path_validate_build_mr(service):
    d = service.create_draft(INSTANCE_ID, "CONFIG_EDIT")
    service.set_files(d["draft_id"], {"kb/team/ok.md": "# appended by test\n"})

    validated = service.validate(d["draft_id"])
    assert validated["state"] == STATE_VALIDATED

    built = service.build_test(d["draft_id"])
    assert built["state"] == STATE_BUILD_TESTED

    mr = service.create_mr(d["draft_id"])
    assert mr["state"] == STATE_MR_CREATED
    assert mr["mr_url"]
    assert mr["target_branch"].startswith("console/draft-")

    # Real instance tree must remain untouched.
    import subprocess

    status = subprocess.run(
        ["git", "-C", str(service.config.repo_root), "status", "--porcelain", "instances/"],
        capture_output=True, text=True,
    )
    assert status.stdout.strip() == ""

    # Clean up the branch this test created.
    subprocess.run(
        ["git", "-C", str(service.config.repo_root), "branch", "-D", mr["target_branch"]],
        capture_output=True, text=True,
    )
