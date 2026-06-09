"""Collector client CLI entry point.

Usage: python -m collector_client.cli --item-json '<json>'

Reads an item JSON from command line argument, loads credentials from
AWX-injected env vars, runs the appropriate connector, and prints
the result as JSON to stdout.

This is the ONLY interface for the AWX playbook to call.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any

from collector_client.db_connectors.base import BaseDbConnector
from collector_client.db_connectors.mssql import SqlServerConnector
from collector_client.db_connectors.mysql import MySqlConnector
from collector_client.db_connectors.oracle import OracleConnector
from collector_client.db_connectors.postgresql import PostgreSqlConnector
from collector_client.env_loader import EnvLoader
from collector_client.os_connectors.base import BaseOsConnector
from collector_client.os_connectors.linux_ssh import LinuxSshConnector
from collector_client.result_builder import ResultBuilder
from collector_client.schemas import CollectorItem, FactEntry

# Connector factory by db_type_code
DB_CONNECTOR_MAP = {
    "oracle": OracleConnector,
    "sqlserver": SqlServerConnector,
    "postgresql": PostgreSqlConnector,
    "mysql": MySqlConnector,
}

# Connector factory by os_family
OS_CONNECTOR_MAP = {
    "linux": LinuxSshConnector,
}

# Fact collection methods by check_code
FACT_METHOD_MAP = {
    "DB_BASIC_FACT_COLLECTION": "collect_basic_facts",
    "DB_VERSION_FACT_COLLECTION": "collect_version_facts",
    "DB_ROLE_FACT_COLLECTION": "collect_role_facts",
    "OS_BASIC_FACT_COLLECTION": "collect_basic_facts",
    "OS_VERSION_FACT_COLLECTION": "collect_version_facts",
    "OS_ROLE_FACT_COLLECTION": "collect_role_facts",
}


def build_db_connector(item: CollectorItem) -> BaseDbConnector:
    """Build the appropriate DB connector from item fields + env vars.

    Raises ValueError if credentials are missing or connector not found.
    """
    db_type = (item.db_type_code or "").lower()
    connector_cls = DB_CONNECTOR_MAP.get(db_type)
    if not connector_cls:
        supported = ", ".join(sorted(DB_CONNECTOR_MAP))
        raise ValueError(f"Unsupported db_type_code: {item.db_type_code}. Supported: {supported}")

    creds = EnvLoader.load_db_credentials()
    if not creds["username"] or not creds["password"]:
        raise ValueError("CREDENTIAL_MISSING: DBOPS_DB_USERNAME or DBOPS_DB_PASSWORD not set")

    kwargs = {
        "host": item.target_host,
        "port": item.target_port,
        "database": item.database_name or "master",
        "username": creds["username"],
        "password": creds["password"],
        "service_name": item.service_name or None,
        "timeout_seconds": item.timeout_seconds,
    }
    return connector_cls(**kwargs)


def build_os_connector(item: CollectorItem) -> BaseOsConnector:
    """Build the appropriate OS connector from item fields + env vars.

    Raises ValueError if credentials are missing or connector not found.
    """
    os_family = (item.os_family or "linux").lower()
    connector_cls = OS_CONNECTOR_MAP.get(os_family)
    if not connector_cls:
        supported = ", ".join(sorted(OS_CONNECTOR_MAP))
        raise ValueError(f"Unsupported os_family: {item.os_family}. Supported: {supported}")

    creds = EnvLoader.load_os_credentials()
    if not creds["username"]:
        raise ValueError("CREDENTIAL_MISSING: DBOPS_OS_USERNAME not set")
    if not creds["password"] and not creds["private_key"]:
        raise ValueError("CREDENTIAL_MISSING: DBOPS_OS_PASSWORD or DBOPS_OS_PRIVATE_KEY not set")

    kwargs = {
        "host": item.target_host,
        "port": item.target_port or 22,
        "username": creds["username"],
        "password": creds.get("password"),
        "private_key": creds.get("private_key"),
        "timeout_seconds": item.timeout_seconds,
    }
    return connector_cls(**kwargs)


def collect_facts(item: CollectorItem) -> dict[str, Any]:
    """Run fact collection based on check_code and item scope.

    Returns a dict of collected facts.
    """
    fact_method_name = FACT_METHOD_MAP.get(item.check_code)
    if not fact_method_name:
        raise ValueError(f"Unsupported check_code for fact collection: {item.check_code}")

    # Determine connector type from target_scope
    if item.target_scope in ("db_instance", "db"):
        connector = build_db_connector(item)
    elif item.target_scope in ("server", "os"):
        connector = build_os_connector(item)
    else:
        raise ValueError(f"Unsupported target_scope: {item.target_scope}")

    try:
        # Test connection first
        if not connector.test_connection():
            raise ConnectionError("Failed to establish connection")

        # Call the appropriate fact method
        method = getattr(connector, fact_method_name)
        facts = method()
        return facts
    finally:
        connector.close()


def main() -> None:
    """CLI entry point.

    Prints CollectorResult as JSON to stdout.
    Exits with code 0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="DBOPS Collector Client — collect facts from target hosts"
    )
    parser.add_argument(
        "--item-json",
        required=True,
        help="JSON string with CollectorItem fields",
    )
    args = parser.parse_args()

    try:
        # Parse item JSON
        item_data = json.loads(args.item_json)
        item = CollectorItem(**item_data)
    except Exception as e:
        result = ResultBuilder.build_failed(
            item_key=item_data.get("item_key", "unknown"),
            error_code="INVALID_ITEM_JSON",
            error_message=f"Failed to parse item JSON: {e}",
        )
        print(result.model_dump_json(indent=2))
        sys.exit(1)

    try:
        # Check if this is a fact collection check_code
        if item.check_code not in FACT_METHOD_MAP:
            result = ResultBuilder.build_skipped(
                item_key=item.item_key,
                error_code="UNSUPPORTED_CHECK_CODE",
                error_message=f"check_code {item.check_code} is not a fact collection code",
            )
            print(result.model_dump_json(indent=2))
            return

        # Collect facts
        facts_dict = collect_facts(item)

        # Convert to FactEntry list
        fact_entries = ResultBuilder.facts_from_dict(facts_dict, category="basic")

        # Build success result
        result = ResultBuilder.build_success(
            item_key=item.item_key,
            facts=fact_entries,
            metadata={
                "check_code": item.check_code,
                "target_host": item.target_host,
                "target_port": item.target_port,
                "collected_at": ResultBuilder.now_iso(),
            },
        )
        print(result.model_dump_json(indent=2))

    except ValueError as e:
        # CREDENTIAL_MISSING or other value errors
        error_msg = str(e)
        error_code = "CREDENTIAL_MISSING" if "CREDENTIAL_MISSING" in error_msg else "INVALID_CONFIG"
        result = ResultBuilder.build_skipped(
            item_key=item.item_key,
            error_code=error_code,
            error_message=error_msg,
        )
        print(result.model_dump_json(indent=2))

    except NotImplementedError as e:
        # MySQL stub — explicitly not implemented
        result = ResultBuilder.build_skipped(
            item_key=item.item_key,
            error_code="NOT_IMPLEMENTED",
            error_message=str(e),
        )
        print(result.model_dump_json(indent=2))

    except ConnectionError as e:
        result = ResultBuilder.build_failed(
            item_key=item.item_key,
            error_code="CONNECTION_FAILED",
            error_message=str(e),
        )
        print(result.model_dump_json(indent=2))

    except Exception as e:
        # Unexpected error — log traceback to stderr only
        traceback.print_exc(file=sys.stderr)
        result = ResultBuilder.build_failed(
            item_key=item.item_key,
            error_code="COLLECTOR_ERROR",
            error_message=f"{type(e).__name__}: {e}",
        )
        print(result.model_dump_json(indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
