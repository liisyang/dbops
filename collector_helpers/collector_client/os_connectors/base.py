"""Base OS connector interface.

STRICT INTERFACE — only these 5 methods are allowed:
  - test_connection()
  - collect_basic_facts()
  - collect_version_facts()
  - collect_role_facts()
  - close()

NO execute_command() or shell execution outside the defined methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseOsConnector(ABC):
    """Abstract base for all OS connectors.

    Subclasses implement the 5 allowed methods.
    Connection credentials come from constructor args (loaded from env vars).
    """

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str | None = None,
        private_key: str | None = None,
        timeout_seconds: int = 30,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.timeout_seconds = timeout_seconds
        self._connected = False

    @abstractmethod
    def test_connection(self) -> bool:
        """Test connectivity to the OS. Returns True if reachable and authenticated."""
        ...

    @abstractmethod
    def collect_basic_facts(self) -> dict[str, Any]:
        """Collect basic OS info (hostname, CPU, memory, disk, network)."""
        ...

    @abstractmethod
    def collect_version_facts(self) -> dict[str, Any]:
        """Collect OS version details (kernel, distribution, release)."""
        ...

    @abstractmethod
    def collect_role_facts(self) -> dict[str, Any]:
        """Collect OS-level role info (virtualization, cluster membership)."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the OS connection and release resources."""
        ...
