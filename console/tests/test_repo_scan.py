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
