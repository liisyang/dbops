"""Read AWX-injected environment variables for DB/OS credentials.

AWX injects credentials as environment variables at job runtime.
This module reads those env vars and returns them as a dict.

CRITICAL: This module NEVER logs env var values.
It only passes them to connector constructors.
"""

from __future__ import annotations

import os
from typing import Optional


class EnvLoader:
    """Load credentials from AWX-injected environment variables.

    AWX credential type → env var mapping (configured in AWX custom credential types):
    - DB Password:   DBOPS_DB_USERNAME, DBOPS_DB_PASSWORD
    - SSH Password:  DBOPS_OS_USERNAME, DBOPS_OS_PASSWORD
    - SSH Key:       DBOPS_OS_USERNAME, DBOPS_OS_PRIVATE_KEY
    """

    @staticmethod
    def load_db_credentials() -> dict[str, Optional[str]]:
        """Load DB credentials from AWX-injected env vars.

        Returns dict with username/password for DB connections.
        These values are NEVER logged.
        """
        return {
            "username": os.environ.get("DBOPS_DB_USERNAME"),
            "password": os.environ.get("DBOPS_DB_PASSWORD"),
        }

    @staticmethod
    def load_os_credentials() -> dict[str, Optional[str]]:
        """Load OS credentials from AWX-injected env vars.

        Returns dict with username/password/private_key for OS connections.
        Supports both password-based and key-based SSH auth.
        """
        return {
            "username": os.environ.get("DBOPS_OS_USERNAME"),
            "password": os.environ.get("DBOPS_OS_PASSWORD"),
            "private_key": os.environ.get("DBOPS_OS_PRIVATE_KEY"),
        }

    @staticmethod
    def has_db_credentials() -> bool:
        """Check if DB credentials are available in environment."""
        creds = EnvLoader.load_db_credentials()
        return bool(creds["username"] and creds["password"])

    @staticmethod
    def has_os_credentials() -> bool:
        """Check if OS credentials are available in environment."""
        creds = EnvLoader.load_os_credentials()
        return bool(creds["username"] and (creds["password"] or creds["private_key"]))
