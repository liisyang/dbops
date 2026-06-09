"""Tests verifying no passwords/keys/tokens appear in logs, DB, or API responses.

Phase 3.3A security requirement:
- DBOPS DB, logs, callback, extra_vars, item_json MUST NOT contain
  password, private_key, token, or secret.
"""

import os
import re

import pytest


# Sensitive patterns that must NEVER appear in code output/logs
FORBIDDEN_PATTERNS = [
    r'\bpassword\b',
    r'\bprivate_key\b',
    r'\bpasswd\b',
    r'\bsecret_key\b',
    r'\baccess_token\b',
]


class TestNoLogSecrets:

    def test_credential_profile_model_no_password_field(self):
        """CredentialProfile model must not have password/secret fields."""
        from app.models.dbops_assets import CredentialProfile

        columns = [c.name for c in CredentialProfile.__table__.columns]
        for col in columns:
            col_lower = col.lower()
            assert "password" not in col_lower, f"CredentialProfile must not have '{col}' column"
            assert "secret" not in col_lower, f"CredentialProfile must not have '{col}' column"
            assert "token" not in col_lower, f"CredentialProfile must not have '{col}' column"
            assert "key" not in col_lower, f"CredentialProfile must not have '{col}' column"

    def test_credential_resolver_output_no_secrets(self):
        """CredentialResolverService output keys must not include passwords."""
        from app.services.credential_resolver_service import CredentialResolverService

        # The returned dict keys are defined in _pick_best()
        # Source code review: keys should only be safe fields
        source = open(
            os.path.join(
                os.path.dirname(__file__),
                "../app/services/credential_resolver_service.py",
            )
        ).read()

        # Find the return dict in _pick_best
        # It must NOT contain password/private_key/token/secret
        for pattern in FORBIDDEN_PATTERNS:
            # Search in the _pick_best method only
            pick_best_start = source.find("def _pick_best")
            pick_best_end = source.find("def ", pick_best_start + 1) if pick_best_start >= 0 else -1
            if pick_best_end == -1:
                pick_best_end = len(source)
            pick_best_code = source[pick_best_start:pick_best_end] if pick_best_start >= 0 else ""
            matches = re.findall(pattern, pick_best_code, re.IGNORECASE)
            assert len(matches) == 0, f"CredentialResolverService._pick_best must not contain '{pattern}'"

    def test_collector_item_builder_no_passwords(self):
        """Check item builder output dicts never contain password fields."""
        source = open(
            os.path.join(
                os.path.dirname(__file__),
                "../app/services/check_item_builder_registry.py",
            )
        ).read()

        # Find the new fact builders section
        fact_section_start = source.find("Phase 3.3A — Fact Collection Item Builders")
        if fact_section_start >= 0:
            fact_code = source[fact_section_start:]

            # The item dicts built in these builders must not contain password fields
            for pattern in [r'"password"', r"'password'", r'"private_key"', r"'private_key'"]:
                matches = re.findall(pattern, fact_code, re.IGNORECASE)
                assert len(matches) == 0, f"Item builders must not contain '{pattern}'"

    def test_awx_service_launch_no_password_in_body(self):
        """AwxService.launch_job body must not contain passwords."""
        source = open(
            os.path.join(
                os.path.dirname(__file__),
                "../app/services/awx_service.py",
            )
        ).read()

        # The launch_job method builds the body dict
        # It should only contain extra_vars and credentials (array of ints)
        # Must not contain password/secret/token
        for pattern in [r'"password"', r"'password'", r'"secret"', r"'secret'"]:
            # Search in launch_job method
            launch_start = source.find("def launch_job")
            launch_end = source.find("def ", launch_start + 1) if launch_start >= 0 else -1
            if launch_end == -1:
                launch_end = len(source)
            launch_code = source[launch_start:launch_end] if launch_start >= 0 else ""
            matches = re.findall(pattern, launch_code, re.IGNORECASE)
            assert len(matches) == 0, f"AwxService.launch_job must not contain '{pattern}'"

    def test_extra_vars_construction_no_secrets(self):
        """Extra vars construction in batch_collector_service must not include secrets."""
        # The extra_vars dict built in create_batch_run and retry_failed_items
        # must only contain safe keys: schema_version, run_id, run_type, callback_url, items
        # NEVER: password, private_key, token
        source = open(
            os.path.join(
                os.path.dirname(__file__),
                "../app/services/batch_collector_service.py",
            )
        ).read()

        # Find all extra_vars dict constructions
        extra_vars_pattern = r'"extra_vars":\s*\{'
        for match in re.finditer(extra_vars_pattern, source):
            # Find the closing brace
            depth = 0
            end = match.end() - 1
            for i in range(match.start(), len(source)):
                if source[i] == "{":
                    depth += 1
                elif source[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            block = source[match.start():end + 1]
            assert "password" not in block.lower(), f"extra_vars must not contain 'password': {block[:200]}"
            assert "private_key" not in block.lower(), f"extra_vars must not contain 'private_key': {block[:200]}"

    def test_env_loader_never_logs_credentials(self):
        """EnvLoader must never log credential values."""
        # The env_loader.py should only read env vars and pass them.
        # It should NOT have any print() or logging of credential values.
        env_loader_path = os.path.join(
            os.path.dirname(__file__),
            "../../collector_helpers/collector_client/env_loader.py",
        )
        if os.path.exists(env_loader_path):
            source = open(env_loader_path).read()
            # Should not log env var values
            assert "print(password" not in source.lower()
            assert "print(username" not in source.lower()
            assert "print(private_key" not in source.lower()
            assert "logger" not in source.lower() or "password" not in source.lower()
