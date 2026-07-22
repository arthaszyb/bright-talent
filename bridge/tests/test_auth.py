from __future__ import annotations

from conftest import build_config_dict

from bridge import auth
from bridge.config import config_from_dict


def cfg(tmp_path, **overrides):
    return config_from_dict(build_config_dict(tmp_path, **overrides))


def test_candidates_collects_user_id_and_email():
    assert auth._candidates({"user_id": "u1", "email": "u1@acme.example"}) == {
        "u1", "u1@acme.example"
    }


def test_candidates_empty_sender():
    assert auth._candidates({}) == set()
    assert auth._candidates(None) == set()


def test_allow_open_when_no_allowlist(tmp_path):
    config = cfg(tmp_path, auth={"allowed_users": [], "admin_users": []})
    assert auth.is_allowed({"user_id": "anyone"}, config) is True


def test_allow_matches_by_user_id_or_email(tmp_path):
    config = cfg(tmp_path, auth={"allowed_users": ["u1@acme.example"], "admin_users": []})
    assert auth.is_allowed({"email": "u1@acme.example"}, config) is True
    assert auth.is_allowed({"user_id": "u1@acme.example"}, config) is True
    assert auth.is_allowed({"user_id": "someone-else"}, config) is False


def test_admin_requires_explicit_membership(tmp_path):
    config = cfg(tmp_path, auth={"allowed_users": ["u1"], "admin_users": ["boss"]})
    assert auth.is_admin({"user_id": "boss"}, config) is True
    assert auth.is_admin({"user_id": "u1"}, config) is False


def test_admin_false_when_no_admins_configured(tmp_path):
    config = cfg(tmp_path, auth={"allowed_users": [], "admin_users": []})
    assert auth.is_admin({"user_id": "anyone"}, config) is False
