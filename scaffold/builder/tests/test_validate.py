"""Unit tests for instance.yaml field-level validation (builder/validate.py).

validate_config is the user-facing contract for declarative instances: it
collects every error (never stops at the first) and the de CLI surfaces
them as one bulleted ValidationError. These tests pin the contract.
"""
from __future__ import annotations

import pytest

from builder.errors import ValidationError
from builder.validate import load_and_validate, validate_config


def minimal_config() -> dict:
    return {
        "schema_version": 1,
        "identity": {"id": "DE-TEST-001", "team": "test-team"},
        "scope": {"service_catalog": ["acme.storefront.checkout"]},
        "base": {"version": "0.1.0"},
    }


def errors_for(config, is_layer: bool = False) -> list[str]:
    errors: list[str] = []
    validate_config(config, errors, is_layer=is_layer)
    return errors


class TestInstanceConfig:
    def test_minimal_valid_config_has_no_errors(self):
        assert errors_for(minimal_config()) == []

    def test_non_mapping_top_level(self):
        assert errors_for(["not", "a", "mapping"]) == ["instance.yaml: top level must be a mapping"]

    def test_missing_required_keys_reported_together(self):
        errs = errors_for({"schema_version": 1})
        assert any("missing required top-level keys" in e and "identity" in e for e in errs)

    def test_unknown_top_level_key_rejected(self):
        errs = errors_for({**minimal_config(), "surprise": 1})
        assert "surprise: unknown top-level key" in errs

    def test_plugins_rejected_with_migration_hint(self):
        errs = errors_for({**minimal_config(), "plugins": []})
        assert any("no longer supported" in e and "skills.yaml" in e for e in errs)

    def test_schema_version_must_be_literal_1(self):
        errs = errors_for({**minimal_config(), "schema_version": "1"})
        assert any(e.startswith("schema_version:") for e in errs)

    def test_identity_field_errors(self):
        cfg = {**minimal_config(), "identity": {"id": "", "team": "  ", "description": 3}}
        errs = errors_for(cfg)
        assert "identity.id: must be a non-empty string" in errs
        assert "identity.team: must be a non-empty string" in errs
        assert "identity.description: must be a string" in errs

    def test_scope_catalog_must_be_nonempty_string_list(self):
        for bad in ({}, {"service_catalog": []}, {"service_catalog": ["ok", ""]}):
            errs = errors_for({**minimal_config(), "scope": bad})
            assert any("scope.service_catalog" in e for e in errs), bad

    def test_duplicate_layer_names_rejected(self):
        cfg = {
            **minimal_config(),
            "layers": [
                {"name": "obs", "repo": "acme/layer-obs"},
                {"name": "obs", "repo": "acme/layer-obs-2"},
            ],
        }
        errs = errors_for(cfg)
        assert any("duplicate name 'obs'" in e for e in errs)

    def test_multiple_errors_collected_not_first_only(self):
        cfg = {
            "schema_version": 2,
            "identity": {"id": ""},
            "scope": {"service_catalog": []},
            "base": {},
            "bogus": True,
        }
        errs = errors_for(cfg)
        assert len(errs) >= 4  # collects everything in one pass


class TestSettingsSection:
    def test_invalid_permission_mode(self):
        cfg = {**minimal_config(), "settings": {"permissions": {"default_mode": "yolo"}}}
        errs = errors_for(cfg)
        assert any("default_mode" in e and "yolo" in e for e in errs)

    def test_extra_allow_must_be_string_list(self):
        cfg = {**minimal_config(), "settings": {"permissions": {"extra_deny": ["ok", 42]}}}
        errs = errors_for(cfg)
        assert any("extra_deny" in e for e in errs)

    def test_env_must_be_str_to_str(self):
        cfg = {**minimal_config(), "settings": {"env": {"KEY": 1}}}
        errs = errors_for(cfg)
        assert any("settings.env" in e for e in errs)

    def test_deprecated_sandbox_rejected(self):
        cfg = {**minimal_config(), "settings": {"sandbox": {}}}
        errs = errors_for(cfg)
        assert any("sandbox is deprecated" in e for e in errs)


class TestLayerConfig:
    def test_instance_only_keys_forbidden_in_layer(self):
        errs = errors_for({"identity": {"id": "x", "team": "y"}, "bridge": {}}, is_layer=True)
        assert "identity: not permitted in a layer.yaml (instance-only key)" in errs
        assert "bridge: not permitted in a layer.yaml (instance-only key)" in errs

    def test_shared_sections_still_validated_in_layer(self):
        errs = errors_for({"settings": {"permissions": {"default_mode": "yolo"}}}, is_layer=True)
        assert any("default_mode" in e for e in errs)


class TestLoadAndValidate:
    def test_missing_instance_yaml_raises(self, tmp_path):
        with pytest.raises(ValidationError, match="not found"):
            load_and_validate(tmp_path)

    def test_yaml_parse_error_raises(self, tmp_path):
        (tmp_path / "instance.yaml").write_text("identity: [unclosed\n", encoding="utf-8")
        with pytest.raises(ValidationError, match="YAML parse error"):
            load_and_validate(tmp_path)

    def test_field_errors_raise_bulleted_message(self, tmp_path):
        (tmp_path / "instance.yaml").write_text("schema_version: 2\n", encoding="utf-8")
        with pytest.raises(ValidationError, match=r"error\(s\):\n  - "):
            load_and_validate(tmp_path)

    def test_reference_instance_in_repo_is_valid(self):
        from pathlib import Path

        instance_dir = Path(__file__).resolve().parents[3] / "instances" / "acme-checkout-sre"
        config = load_and_validate(instance_dir)
        assert config["identity"]["id"] == "DE-ACME-CHECKOUT-001"
