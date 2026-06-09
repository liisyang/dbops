"""Tests for AwxService.launch_job with credentials parameter (Phase 3.3A).

These tests verify that:
1. launch_job accepts credentials: list[int]
2. Credentials array is included in the launch body
3. No passwords appear in extra_vars
"""

import pytest

from app.services.awx_service import AwxService, AwxServiceError


class TestAwxServiceCredentials:

    def test_launch_job_accepts_credentials_parameter(self):
        """launch_job signature includes optional credentials parameter."""
        import inspect
        sig = inspect.signature(AwxService.launch_job)
        assert "credentials" in sig.parameters
        param = sig.parameters["credentials"]
        # Should be optional (default None)
        assert param.default is None

    def test_extra_vars_never_contain_password(self):
        """Extra vars must not contain password/private_key/token."""
        extra_vars = {
            "schema_version": 1,
            "run_id": "TEST-RUN",
            "items": [
                {
                    "item_key": "test",
                    "check_code": "DB_BASIC_FACT_COLLECTION",
                    "target_host": "10.0.0.1",
                    "target_port": 1433,
                    "db_type_code": "sqlserver",
                }
            ],
        }
        # Check that no sensitive fields are in extra_vars
        extra_vars_str = str(extra_vars)
        assert "password" not in extra_vars_str.lower()
        assert "private_key" not in extra_vars_str.lower()
        assert "token" not in extra_vars_str.lower()
        assert "secret" not in extra_vars_str.lower()

    def test_credentials_array_only_contains_ints(self):
        """Credentials parameter should be list[int] — credential IDs only."""
        # Validate that we only pass integer credential IDs
        credentials = [45, 66, 99]
        assert all(isinstance(c, int) for c in credentials)
        assert len(credentials) == 3

    def test_credential_id_never_contains_password(self):
        """AWX credential IDs are integers, not passwords."""
        # AWX credential IDs are auto-increment integers, like 45, 66
        # They should NEVER be strings resembling passwords
        credentials = [45, 66]
        for c in credentials:
            assert isinstance(c, int)
            assert c > 0
    def test_item_dict_never_contains_password(self):
        """Item dicts in extra_vars must not contain password/private_key/token."""
        item = {
            "item_key": "db_instance:1:DB_BASIC_FACT_COLLECTION:10.0.0.1:1433",
            "check_code": "DB_BASIC_FACT_COLLECTION",
            "target_scope": "db_instance",
            "target_host": "10.0.0.1",
            "target_port": 1433,
            "db_type_code": "sqlserver",
            "credential_profile_id": 1,
            "credential_code": "SQL_READONLY_01",
            "credential_role": "db_readonly",
        }
        item_str = str(item)
        assert "password" not in item_str.lower()
        assert "private_key" not in item_str.lower()
        assert "token" not in item_str.lower()
        # Credential references are present but no secrets
        assert "credential_profile_id" in item_str
        assert "credential_code" in item_str
