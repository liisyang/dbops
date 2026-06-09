"""Build unified JSON output for the collector callback.

Constructs CollectorResult from connector output.
The result is printed to stdout as JSON for the AWX playbook to capture.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from collector_client.schemas import CollectorResult, FactEntry


class ResultBuilder:
    """Build CollectorResult from connector output."""

    @staticmethod
    def build_success(
        item_key: str,
        facts: list[FactEntry],
        warnings: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CollectorResult:
        """Build a success result with collected facts."""
        return CollectorResult(
            item_key=item_key,
            status="success",
            facts=facts,
            warnings=warnings or [],
            metadata=metadata or {},
        )

    @staticmethod
    def build_partial(
        item_key: str,
        facts: list[FactEntry],
        error_message: str,
        error_code: str = "PARTIAL_COLLECTION",
        warnings: list[str] | None = None,
    ) -> CollectorResult:
        """Build a partial success result — some facts collected, some failed."""
        return CollectorResult(
            item_key=item_key,
            status="partial",
            error_code=error_code,
            error_message=error_message,
            facts=facts,
            warnings=warnings or [],
        )

    @staticmethod
    def build_skipped(
        item_key: str,
        error_code: str,
        error_message: str,
    ) -> CollectorResult:
        """Build a skipped result (e.g., CREDENTIAL_MISSING)."""
        return CollectorResult(
            item_key=item_key,
            status="skipped",
            error_code=error_code,
            error_message=error_message,
            facts=[],
        )

    @staticmethod
    def build_failed(
        item_key: str,
        error_code: str,
        error_message: str,
    ) -> CollectorResult:
        """Build a failed result."""
        return CollectorResult(
            item_key=item_key,
            status="failed",
            error_code=error_code,
            error_message=error_message,
            facts=[],
        )

    @staticmethod
    def facts_from_dict(
        data: dict[str, Any],
        category: str = "basic",
        prefix: str = "",
    ) -> list[FactEntry]:
        """Convert a flat dict of key-value pairs into FactEntry list.

        Args:
            data: Dict of {key: value} pairs.
            category: Fact category (basic, version, role, config).
            prefix: Optional prefix for fact keys.

        Returns:
            List of FactEntry objects.
        """
        facts: list[FactEntry] = []
        for key, value in data.items():
            fact_key = f"{prefix}{key}" if prefix else key
            facts.append(
                FactEntry(
                    key=fact_key,
                    value=value,
                    category=category,
                    is_null=value is None,
                )
            )
        return facts

    @staticmethod
    def now_iso() -> str:
        """Return current UTC timestamp as ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()
