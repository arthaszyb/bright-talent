"""Direct tests for the drift classifier `_status_for_file` (repo_scan.py).

This is the core of the governance console's drift detection: it turns three
hashes (current scaffold template, current runtime file, last-synced record)
into a status the health scorer consumes. test_health.py covers the scorer's
reaction to status strings; this pins the classifier that produces them.
"""
from console.repo_scan import _status_for_file

# ---- three-way (scaffold side known: BASE_SOURCE files) --------------------

def test_all_equal_is_up_to_date():
    assert _status_for_file("h", "h", "h", scaffold_known=True) == "up_to_date"


def test_scaffold_moved_only_is_template_moved():
    # scaffold template advanced; runtime still at the recorded/last-synced hash
    assert _status_for_file("rec", "rec", "new-scaffold", scaffold_known=True) == "template_moved"


def test_local_edited_only_is_local_changed():
    # runtime file hand-edited; scaffold still matches the record
    assert _status_for_file("rec", "local-edit", "rec", scaffold_known=True) == "local_changed"


def test_both_sides_diverged_is_both_changed():
    # scaffold moved AND runtime edited to a different value -> conflict
    assert _status_for_file("rec", "local-edit", "new-scaffold", scaffold_known=True) == "both_changed"


def test_missing_local_is_missing_even_when_scaffold_known():
    assert _status_for_file("rec", None, "scaffold", scaffold_known=True) == "missing"


# ---- two-way (scaffold side unknown: templated files) ----------------------

def test_templated_up_to_date_when_local_matches_record():
    assert _status_for_file("rec", "rec", None, scaffold_known=False) == "up_to_date"


def test_templated_local_changed_when_local_differs():
    assert _status_for_file("rec", "local-edit", None, scaffold_known=False) == "local_changed"


def test_missing_local_two_way():
    assert _status_for_file("rec", None, None, scaffold_known=False) == "missing"


def test_templated_ignores_scaffold_hash_even_if_passed():
    # scaffold_known=False must not consult scaffold_sha at all
    assert _status_for_file("rec", "rec", "irrelevant", scaffold_known=False) == "up_to_date"


# ---- cache invalidation: a scaffold upgrade must not serve a stale status ---

def test_scan_cache_reflects_a_scaffold_change(tmp_path):
    """`template_moved` depends on files outside the instance directory.

    A managed file's status is a three-way comparison against the scaffold's
    *current* template, so keying the scan cache on the instance alone let a
    scaffold upgrade go unnoticed: the console kept reporting `up_to_date`
    for files that had genuinely fallen behind, which is precisely the drift
    an upgrade creates.
    """
    import shutil
    from pathlib import Path

    from console.config import Config
    from console.repo_scan import RepoScanner

    repo_root = Path(__file__).resolve().parents[2]
    work = tmp_path / "repo"
    for d in ("scaffold", "instances", "skills"):
        shutil.copytree(repo_root / d, work / d, symlinks=True)

    cfg = Config.from_args(repo=str(work), port=0, db_path=str(tmp_path / "t.db"))
    scanner = RepoScanner(cfg)
    target = ".claude/hooks/context-isolator.py"

    def status_of(force=False):
        scan = scanner.scan_instance("acme-checkout-sre", force=force)
        return next(f["status"] for f in scan["managed_files"] if f["path"] == target)

    assert status_of() == "up_to_date"

    # Move the scaffold forward, touching nothing inside the instance.
    template = work / "scaffold" / "base" / target
    template.write_text(template.read_text() + "\n# scaffold moved forward\n")

    assert status_of() == "template_moved", "cached scan hid a real scaffold upgrade"
    assert status_of(force=True) == "template_moved"


def test_scan_cache_still_serves_repeat_scans(tmp_path):
    """The scaffold key must not defeat caching when nothing has changed."""
    import shutil
    from pathlib import Path

    from console.config import Config
    from console.repo_scan import RepoScanner

    repo_root = Path(__file__).resolve().parents[2]
    work = tmp_path / "repo"
    for d in ("scaffold", "instances", "skills"):
        shutil.copytree(repo_root / d, work / d, symlinks=True)

    cfg = Config.from_args(repo=str(work), port=0, db_path=str(tmp_path / "t.db"))
    scanner = RepoScanner(cfg)
    first = scanner.scan_instance("acme-checkout-sre")
    second = scanner.scan_instance("acme-checkout-sre")
    assert second is first, "an unchanged repo should hit the cache"
