"""Base DB connector interface.

STRICT INTERFACE — only these 5 methods are allowed:
  - test_connection()
  - collect_basic_facts()
  - collect_version_facts()
  - collect_role_facts()
  - close()

NO execute_sql() or any free SQL entry point.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDbConnector(ABC):
    """Abstract base for all DB connectors.

    Subclasses implement the 5 allowed methods.
    Connection credentials come from constructor args (loaded from env vars).
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        username: str,
        password: str,
        service_name: str | None = None,
        timeout_seconds: int = 30,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.service_name = service_name
        self.timeout_seconds = timeout_seconds
        self._connected = False

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connectivity to the database. Returns True if reachable."""
        ...

    @abstractmethod
    def collect_basic_facts(self) -> dict[str, Any]:
        """Collect basic instance info (name, role, startup time, etc.)."""
        ...

    @abstractmethod
    def collect_version_facts(self) -> dict[str, Any]:
        """Collect version details (major, minor, patch, edition)."""
        ...

    @abstractmethod
    def collect_role_facts(self) -> dict[str, Any]:
        """Collect HA/replication role info (primary, standby, etc.)."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the database connection and release resources."""
        ...
