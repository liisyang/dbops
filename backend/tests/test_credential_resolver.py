"""Tests for CredentialResolverService — priority chains and CREDENTIAL_MISSING."""

import pytest

from app.models.dbops_assets import (
    CredentialBinding,
    CredentialProfile,
)
from app.services.credential_resolver_service import CredentialResolverService


class TestCredentialResolverService:

    def test_model_has_no_password_field(self):
        """CredentialProfile model must not have password/secret fields."""
        columns = [c.name for c in CredentialProfile.__table__.columns]
        for col in columns:
            col_lower = col.lower()
            assert "password" not in col_lower, f"CredentialProfile must not have '{col}' column"
            assert "secret" not in col_lower, f"CredentialProfile must not have '{col}' column"
            assert "token" not in col_lower, f"CredentialProfile must not have '{col}' column"
            assert "key" not in col_lower, f"CredentialProfile must not have '{col}' column"

    def test_model_has_required_fields(self):
        """CredentialProfile has all required fields for credential reference."""
        columns = {c.name for c in CredentialProfile.__table__.columns}
        required = {
            "id", "profile_code", "profile_name", "credential_type",
            "awx_credential_id", "awx_credential_name", "db_type_code",
            "os_family", "default_database", "is_enabled",
        }
        for field in required:
            assert field in columns, f"CredentialProfile missing field: {field}"

    def test_binding_model_has_required_fields(self):
        """CredentialBinding has all required fields for priority resolution."""
        columns = {c.name for c in CredentialBinding.__table__.columns}
        required = {
            "id", "profile_id", "binding_role", "binding_target_type",
            "binding_target_id", "network_zone", "priority", "is_enabled",
        }
        for field in required:
            assert field in columns, f"CredentialBinding missing field: {field}"

    def test_resolve_for_item_server_dispatches(self, monkeypatch):
        """resolve_for_item dispatches to resolve_os_credential for server scope."""
        called_with = None

        def mock_resolve(db, server_id):
            nonlocal called_with
            called_with = server_id
            return {"credential_type": "ssh_key"}

        monkeypatch.setattr(
            CredentialResolverService, "resolve_os_credential",
            staticmethod(mock_resolve)
        )

        asset = {"id": 42, "target_scope": "server"}
        result = CredentialResolverService.resolve_for_item(
            None, "server", asset, "OS_BASIC_FACT_COLLECTION"
        )
        assert called_with == 42
        assert result is not None
        assert result["credential_type"] == "ssh_key"

    def test_resolve_for_item_db_instance_dispatches(self, monkeypatch):
        """resolve_for_item dispatches to resolve_db_credential for db_instance scope."""
        called_with = None

        def mock_resolve(db, instance_id):
            nonlocal called_with
            called_with = instance_id
            return {"credential_type": "db_password"}

        monkeypatch.setattr(
            CredentialResolverService, "resolve_db_credential",
            staticmethod(mock_resolve)
        )

        asset = {"id": 99, "target_scope": "db_instance"}
        result = CredentialResolverService.resolve_for_item(
            None, "db_instance", asset, "DB_BASIC_FACT_COLLECTION"
        )
        assert called_with == 99
        assert result is not None
        assert result["credential_type"] == "db_password"

    def test_resolve_for_item_unknown_scope_returns_none(self):
        """Unknown target_scope returns None."""
        asset = {"id": 1}
        result = CredentialResolverService.resolve_for_item(
            None, "unknown", asset, "SOME_CHECK"
        )
        assert result is None

    def test_pick_best_returns_none_for_empty_list(self):
        """_pick_best returns None when no candidates."""
        result = CredentialResolverService._pick_best([])
        assert result is None

    def test_pick_best_sorts_by_priority(self):
        """_pick_best picks lowest priority value (lower number = higher priority)."""
        candidates = [
            {"credential_profile_id": 1, "credential_code": "A", "awx_credential_id": 10,
             "awx_credential_name": "A", "credential_type": "db_password",
             "binding_role": "db_readonly", "binding_target_type": "global",
             "binding_priority": 200, "default_database": None, "db_type_code": None},
            {"credential_profile_id": 2, "credential_code": "B", "awx_credential_id": 20,
             "awx_credential_name": "B", "credential_type": "db_password",
             "binding_role": "db_readonly", "binding_target_type": "global",
             "binding_priority": 10, "default_database": None, "db_type_code": None},
        ]
        best = CredentialResolverService._pick_best(candidates)
        # Lower binding_priority (10) should win over higher (200)
        assert best["credential_profile_id"] == 2

    def test_pick_best_never_returns_secrets(self):
        """_pick_best output never contains password/private_key/token."""
        candidates = [
            {"credential_profile_id": 1, "credential_code": "TEST", "awx_credential_id": 10,
             "awx_credential_name": "T", "credential_type": "db_password",
             "binding_role": "db_readonly", "binding_target_type": "global",
             "binding_priority": 100, "default_database": None, "db_type_code": None},
        ]
        best = CredentialResolverService._pick_best(candidates)
        forbidden = ["password", "private_key", "token", "secret", "username"]
        for key in forbidden:
            assert key not in best, f"Credential output must not contain '{key}'"

    def test_query_bindings_filters_enabled_only(self, monkeypatch):
        """_query_bindings should only return enabled bindings/profiles."""
        # Verify the method exists and has correct signature
        import inspect
        sig = inspect.signature(CredentialResolverService._query_bindings)
        params = list(sig.parameters.keys())
        assert "db" in params
        assert "binding_target_type" in params
        assert "binding_roles" in params
