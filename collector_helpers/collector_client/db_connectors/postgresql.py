"""PostgreSQL connector — psycopg (psycopg 3).

Uses psycopg 3.x for async-capable, modern PostgreSQL connectivity.
Default database: postgres.
"""

from __future__ import annotations

from typing import Any

from collector_client.db_connectors.base import BaseDbConnector


class PostgreSqlConnector(BaseDbConnector):
    """PostgreSQL database fact collector.

    Connects using psycopg 3.
    Requires: psycopg[binary]>=3.0
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connection = None
        self._cursor = None

    def _connect(self) -> None:
        """Establish PostgreSQL connection if not already connected."""
        if self._connection is not None:
            return

        import psycopg

        conn_str = (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.username} "
            f"password={self.password} "
            f"connect_timeout={self.timeout_seconds}"
        )
        self._connection = psycopg.connect(conn_str)
        self._cursor = self._connection.cursor()

    def test_connection(self) -> bool:
        try:
            self._connect()
            self._cursor.execute("SELECT 1")
            self._cursor.fetchone()
            return True
        except Exception:
            return False

    def collect_basic_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # version()
            try:
                self._cursor.execute("SELECT version()")
                row = self._cursor.fetchone()
                if row:
                    facts["version_full"] = row[0]
            except Exception:
                facts["_version_error"] = "permission_limited"

            # pg_is_in_recovery()
            try:
                self._cursor.execute("SELECT pg_is_in_recovery()")
                row = self._cursor.fetchone()
                if row:
                    facts["is_in_recovery"] = bool(row[0])
            except Exception:
                facts["_recovery_error"] = "permission_limited"

            # pg_postmaster_start_time()
            try:
                self._cursor.execute("SELECT pg_postmaster_start_time()")
                row = self._cursor.fetchone()
                if row:
                    facts["startup_time"] = str(row[0]) if row[0] else None
            except Exception:
                facts["_startup_time_error"] = "permission_limited"

            # current_database(), inet_server_addr(), inet_server_port()
            try:
                self._cursor.execute(
                    "SELECT current_database(), inet_server_addr(), inet_server_port()"
                )
                row = self._cursor.fetchone()
                if row:
                    facts["current_database"] = row[0]
                    facts["server_addr"] = str(row[1]) if row[1] else None
                    facts["server_port"] = int(row[2]) if row[2] else None
            except Exception:
                facts["_server_info_error"] = "permission_limited"

            # Basic settings
            for setting in ["max_connections", "shared_buffers", "server_encoding"]:
                try:
                    self._cursor.execute("SELECT current_setting(%s)", (setting,))
                    row = self._cursor.fetchone()
                    if row:
                        facts[setting] = row[0]
                except Exception:
                    pass

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def collect_version_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # server_version and server_version_num
            try:
                self._cursor.execute("SHOW server_version")
                row = self._cursor.fetchone()
                if row:
                    facts["version_full"] = row[0]
            except Exception:
                pass

            try:
                self._cursor.execute("SHOW server_version_num")
                row = self._cursor.fetchone()
                if row and row[0]:
                    version_num = int(row[0])
                    facts["version_num"] = version_num
                    facts["version_major"] = version_num // 10000
                    facts["version_minor"] = (version_num % 10000) // 100
                    facts["version_patch"] = version_num % 100
            except Exception:
                pass

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def collect_role_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # pg_is_in_recovery determines primary vs standby
            try:
                self._cursor.execute("SELECT pg_is_in_recovery()")
                row = self._cursor.fetchone()
                if row:
                    is_recovery = bool(row[0])
                    facts["is_in_recovery"] = is_recovery
                    facts["node_role"] = "standby" if is_recovery else "primary"
            except Exception:
                facts["_role_error"] = "permission_limited"

            # Current WAL LSN for replication lag context
            try:
                self._cursor.execute("SELECT pg_current_wal_lsn()")
                row = self._cursor.fetchone()
                if row:
                    facts["current_wal_lsn"] = str(row[0]) if row[0] else None
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
