"""SQL Server connector — pyodbc + Microsoft ODBC Driver 17/18.

CORE PATH for Phase 3.3A.

System dependencies (must be pre-installed on Execution Node):
  unixODBC (apt: unixodbc unixodbc-dev)
  Microsoft ODBC Driver 17 or 18 for SQL Server
    https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
Python:
  pyodbc>=4.0.39

Local smoke test:
  python -c "
  import pyodbc
  conn = pyodbc.connect('DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost,1433;DATABASE=master;UID=sa;PWD=YourPassword;TrustServerCertificate=yes')
  cursor = conn.cursor()
  cursor.execute('SELECT @@VERSION')
  print(cursor.fetchone()[0])
  conn.close()
  "
"""

from __future__ import annotations

from typing import Any

from collector_client.db_connectors.base import BaseDbConnector


class SqlServerConnector(BaseDbConnector):
    """SQL Server database fact collector.

    Connects using pyodbc with Microsoft ODBC Driver 17/18.
    Queries @@VERSION, SERVERPROPERTY(), sys.dm_hadr_availability_replica_states.
    Graceful fallback on Always On DMV not accessible.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._connection = None
        self._cursor = None

    def _build_connection_string(self) -> str:
        """Build ODBC connection string for SQL Server.

        Uses ODBC Driver 17 for SQL Server by default.
        TrustServerCertificate=yes for non-production environments.
        """
        driver = "ODBC Driver 17 for SQL Server"
        conn_str = (
            f"DRIVER={{{driver}}};"
            f"SERVER={self.host},{self.port};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout={self.timeout_seconds};"
        )
        return conn_str

    def _connect(self) -> None:
        """Establish SQL Server connection if not already connected."""
        if self._connection is not None:
            return

        import pyodbc

        conn_str = self._build_connection_string()
        self._connection = pyodbc.connect(conn_str, timeout=self.timeout_seconds)
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

            # @@VERSION — full version string
            try:
                self._cursor.execute("SELECT @@VERSION")
                row = self._cursor.fetchone()
                if row:
                    facts["version_full"] = row[0]
            except Exception:
                facts["_version_error"] = "permission_limited"

            # SERVERPROPERTY queries for basic instance info
            properties = [
                ("ProductVersion", "product_version"),
                ("Edition", "edition"),
                ("EngineEdition", "engine_edition"),
                ("InstanceName", "instance_name"),
                ("IsClustered", "is_clustered"),
                ("ComputerNamePhysicalNetBIOS", "host_name"),
                ("IsHadrEnabled", "is_hadr_enabled"),
                ("ServerName", "server_name"),
            ]
            for prop_name, fact_key in properties:
                try:
                    self._cursor.execute(f"SELECT SERVERPROPERTY('{prop_name}')")
                    row = self._cursor.fetchone()
                    if row and row[0] is not None:
                        value = row[0]
                        # Convert 0/1 to bool for Is* properties
                        if prop_name.startswith("Is"):
                            value = bool(int(value))
                        facts[fact_key] = value
                except Exception:
                    facts[f"_sp_{prop_name}_error"] = "permission_limited"

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def collect_version_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # Product version components
            version_props = [
                ("ProductMajorVersion", "version_major"),
                ("ProductMinorVersion", "version_minor"),
                ("ProductBuild", "product_build"),
                ("ProductLevel", "product_level"),       # RTM, SP1, etc.
                ("ProductUpdateLevel", "product_update"), # CU1, etc.
                ("ProductVersion", "version_full"),
            ]
            for prop_name, fact_key in version_props:
                try:
                    self._cursor.execute(f"SELECT SERVERPROPERTY('{prop_name}')")
                    row = self._cursor.fetchone()
                    if row and row[0] is not None:
                        facts[fact_key] = str(row[0])
                except Exception:
                    facts[f"_sp_{prop_name}_error"] = "permission_limited"

            # Collation
            try:
                self._cursor.execute("SELECT SERVERPROPERTY('Collation')")
                row = self._cursor.fetchone()
                if row and row[0]:
                    facts["collation"] = row[0]
            except Exception:
                pass

        except Exception as e:
            facts["_connection_error"] = str(e)[:500]

        return facts

    def collect_role_facts(self) -> dict[str, Any]:
        facts: dict[str, Any] = {}
        try:
            self._connect()

            # IsHadrEnabled
            try:
                self._cursor.execute("SELECT SERVERPROPERTY('IsHadrEnabled')")
                row = self._cursor.fetchone()
                if row and row[0] is not None:
                    facts["is_hadr_enabled"] = bool(int(row[0]))
            except Exception:
                facts["_hadr_enabled_error"] = "permission_limited"

            # Always On availability replica states
            # Graceful fallback to UNKNOWN if DMV not accessible
            try:
                self._cursor.execute(
                    "SELECT replica_server_name, role_desc, operational_state_desc, "
                    "       connected_state_desc, synchronization_health_desc "
                    "FROM sys.dm_hadr_availability_replica_states ars "
                    "JOIN sys.availability_replicas ar ON ars.replica_id = ar.replica_id "
                    "WHERE ars.is_local = 1"
                )
                row = self._cursor.fetchone()
                if row:
                    facts["replica_server_name"] = row[0]
                    role_desc = row[1]  # PRIMARY, SECONDARY, RESOLVING
                    facts["replica_role"] = role_desc
                    facts["operational_state"] = row[2]
                    facts["connected_state"] = row[3]
                    facts["sync_health"] = row[4]

                    # Map to DBOPS role
                    role_map = {
                        "PRIMARY": "primary",
                        "SECONDARY": "standby",
                        "RESOLVING": "unknown",
                    }
                    facts["node_role"] = role_map.get(role_desc, "unknown")
                else:
                    # No Always On replica — this is a standalone instance
                    facts["replica_role"] = "SINGLE"
                    facts["node_role"] = "single"
            except Exception:
                # DMV not accessible — determine role by other means
                facts["_hadr_dmv_error"] = "permission_limited"
                facts["replica_role"] = "UNKNOWN"
                facts["node_role"] = "unknown"

            # Engine edition for role context
            try:
                self._cursor.execute("SELECT SERVERPROPERTY('EngineEdition')")
                row = self._cursor.fetchone()
                if row and row[0] is not None:
                    engine_edition = int(row[0])
                    facts["engine_edition"] = engine_edition
                    # 1=Personal/Desktop, 2=Standard, 3=Enterprise, 4=Express, 5=SQL Database, 8=Managed Instance
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
