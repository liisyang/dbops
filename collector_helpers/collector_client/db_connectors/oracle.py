"""Oracle connector — python-oracledb thin mode.

Uses python-oracledb in Thin mode (no Oracle Instant Client required).
Queries v$instance, v$database, v$version, v$option.
Graceful fallback on permission denied.
"""

from __future__ import annotations

from typing import Any

from collector_client.db_connectors.base import BaseDbConnector


class OracleConnector(BaseDbConnector):
    """Oracle database fact collector.

    Connects using python-oracledb thin mode.
    Requires: python-oracledb (pip install oracledb)
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connection = None
        self._cursor = None

    def _connect(self) -> None:
        """Establish Oracle connection if not already connected."""
        if self._connection is not None:
            return

        import oracledb

        # Build DSN: host:port/service_name
        if self.service_name:
            dsn = f"{self.host}:{self.port}/{self.service_name}"
        else:
            dsn = f"{self.host}:{self.port}"

        self._connection = oracledb.connect(
            user=self.username,
            password=self.password,
            dsn=dsn,
        )
        self._cursor = self._connection.cursor()

    def test_connection(self) -> bool:
        try:
            self._connect()
            self._cursor.execute("SELECT 1 FROM DUAL")
            self._cursor.fetchone()
            return True
        except Exception:
            return False

    def collect_basic_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # v$instance: instance_name, host_name, status, startup_time
            try:
                self._cursor.execute(
                    "SELECT instance_name, host_name, status, startup_time, "
                    "       database_status, instance_role "
                    "FROM v$instance"
                )
                row = self._cursor.fetchone()
                if row:
                    facts["instance_name"] = row[0]
                    facts["host_name"] = row[1]
                    facts["instance_status"] = row[2]
                    facts["startup_time"] = str(row[3]) if row[3] else None
                    facts["database_status"] = row[4]
                    facts["instance_role"] = row[5]
            except Exception:
                facts["_v_instance_error"] = "permission_limited"

            # v$database: name, open_mode, database_role, log_mode
            try:
                self._cursor.execute(
                    "SELECT name, open_mode, database_role, log_mode, "
                    "       created, platform_name "
                    "FROM v$database"
                )
                row = self._cursor.fetchone()
                if row:
                    facts["database_name"] = row[0]
                    facts["open_mode"] = row[1]
                    facts["database_role"] = row[2]
                    facts["log_mode"] = row[3]
                    facts["created"] = str(row[4]) if row[4] else None
                    facts["platform_name"] = row[5]
            except Exception:
                facts["_v_database_error"] = "permission_limited"

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def collect_version_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # v$version: full version banner
            try:
                self._cursor.execute("SELECT banner FROM v$version WHERE banner LIKE 'Oracle%'")
                row = self._cursor.fetchone()
                if row:
                    facts["version_full"] = row[0]
            except Exception:
                facts["_v_version_error"] = "permission_limited"

            # v$option: installed components
            try:
                self._cursor.execute(
                    "SELECT parameter, value FROM v$option WHERE parameter IN "
                    "('Partitioning', 'Real Application Clusters', 'Advanced Compression', 'OLAP')"
                )
                for parameter, value in self._cursor.fetchall():
                    facts[f"option_{parameter.lower().replace(' ', '_')}"] = value == "TRUE"
            except Exception:
                facts["_v_option_error"] = "permission_limited"

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def collect_role_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # Database role from v$database
            try:
                self._cursor.execute("SELECT database_role FROM v$database")
                row = self._cursor.fetchone()
                if row:
                    role = row[0]
                    facts["database_role"] = role
                    # Map to DBOPS role
                    if role == "PRIMARY":
                        facts["node_role"] = "primary"
                    elif role == "PHYSICAL STANDBY":
                        facts["node_role"] = "standby"
                    elif role == "LOGICAL STANDBY":
                        facts["node_role"] = "standby"
                    else:
                        facts["node_role"] = "unknown"
            except Exception:
                facts["_role_error"] = "permission_limited"

            # Instance role from v$instance
            try:
                self._cursor.execute("SELECT instance_role FROM v$instance")
                row = self._cursor.fetchone()
                if row:
                    facts["instance_role"] = row[0]
            except Exception:
                pass

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def close(self) -> None:
        try:
            if self._cursor:
                self._cursor.close()
        except Exception:
            pass
        try:
            if self._connection:
                self._connection.close()
        except Exception:
            pass
        self._connection = None
        self._cursor = None
