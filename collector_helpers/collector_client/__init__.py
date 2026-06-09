# DBOPS Collector Client — Execution Node Python CLI
#
# This package runs on AWX Execution Nodes.
# It connects to target DB/OS hosts and collects read-only facts.
# NEVER exposes execute_sql() or any free SQL entry point.
#
# Usage:
#   python -m collector_client.cli --item-json '<json>'
#
# Environment variables injected by AWX credentials:
#   DBOPS_DB_USERNAME, DBOPS_DB_PASSWORD
#   DBOPS_OS_USERNAME, DBOPS_OS_PASSWORD, DBOPS_OS_PRIVATE_KEY

__version__ = "1.0.0"
