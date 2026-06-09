"""Pydantic schemas for collector client input/output.

These define the contract between the AWX playbook and the collector client.
The item_json input and result JSON output are the ONLY interfaces.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CollectorItem(BaseModel):
    """Input item from AWX playbook.

    Contains all information needed for a single fact collection check.
    NO passwords — credentials come from AWX-injected env vars.
    """

    item_key: str = Field(min_length=1)
    check_code: str = Field(min_length=1)
    target_scope: str = Field(min_length=1)  # server, db_instance
    target_host: str = Field(min_length=1)
    target_port: int = Field(ge=1, le=65535)
    db_type_code: Optional[str] = None  # oracle, sqlserver, postgresql, mysql
    database_name: Optional[str] = None  # master, postgres, etc.
    service_name: Optional[str] = None  # Oracle service name
    os_family: Optional[str] = None  # linux, windows
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    fact_category: Optional[str] = None  # basic, version, role
    credential_profile_id: Optional[int] = None
    credential_code: Optional[str] = None
    credential_role: Optional[str] = None


class FactEntry(BaseModel):
    """A single collected fact key-value pair."""

    key: str
    value: Any = None
    category: str = "basic"  # basic, version, role, config
    source: Optional[str] = None  # query or command that produced this fact
    is_null: bool = False


class CollectorResult(BaseModel):
    """Output result from collector client — printed to stdout as JSON.

    The AWX playbook captures this output and includes it in the callback.
    """

    item_key: str
    status: str = "success"  # success, failed, skipped, partial
    error_code: Optional[str] = None  # CREDENTIAL_MISSING, CONNECTION_FAILED, etc.
    error_message: Optional[str] = None
    facts: list[FactEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {Any: str}
