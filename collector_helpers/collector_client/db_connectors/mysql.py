"""MySQL connector — STUB ONLY for Phase 3.3A.

MySQL fact collection is NOT implemented in Phase 3.3A.
This stub exists for completeness and future Phase 3.3B implementation.
All methods raise NotImplementedError with a clear message.
"""

from __future__ import annotations

from typing import Any

from collector_client.db_connectors.base import BaseDbConnector


class MySqlConnector(BaseDbConnector):
    """MySQL connector — NOT IMPLEMENTED in Phase 3.3A.

    This is a stub that raises NotImplementedError on all operations.
    Full MySQL fact collection is deferred to Phase 3.3B.
    """

    _NOT_IMPLEMENTED_MSG = "MySQL fact collection is not implemented in Phase 3.3A"

    def test_connection(self) -> bool:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)

    def collect_basic_facts(self) -> dict[str, Any]:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)

    def collect_version_facts(self) -> dict[str, Any]:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)

    def collect_role_facts(self) -> dict[str, Any]:
        raise NotImplementedError(self._NOT_IMPLEMENTED_MSG)

    def close(self) -> None:
        pass  # No connection to close
