"""Phase 3.5: SQL readonly safety validation service.

P0 implementation. Token-level keyword gating with string-literal masking
so a string like ``'DROP TABLE foo'`` does NOT trigger a false positive.
Not a full SQL parser — see comments for known limitations.

DBOPS may reject (return ``valid=False``) any SQL that:

* uses any keyword in :data:`DANGEROUS_KEYWORDS` outside of a string literal
* matches ``SELECT ... INTO``, ``INTO OUTFILE/DUMPFILE`` or ``FOR UPDATE``
* starts with anything other than an allowed lead keyword for the target DB
* contains multiple statements (more than one trailing ``;``)
* uses Oracle's ``q'[...]'`` alternative quoting — explicitly NOT handled in P0
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


# Dangerous keywords / functions. ``INTO`` is intentionally NOT in this
# list (would over-match identifiers like ``select_into_temp``). Instead
# we pattern-match ``SELECT ... INTO`` separately further down.
DANGEROUS_KEYWORDS = [
    # write operations
    "INSERT", "UPDATE", "DELETE", "MERGE", "DROP", "ALTER",
    "CREATE", "TRUNCATE", "GRANT", "REVOKE",
    # execution / calls
    "EXEC", "EXECUTE", "CALL", "BEGIN", "DECLARE",
    # maintenance
    "ANALYZE", "VACUUM", "REINDEX", "COPY",
    # lock / wait traps
    "LOCK", "WAITFOR",
    # Oracle high-risk packages
    "DBMS_LOCK", "DBMS_SCHEDULER", "DBMS_PIPE",
    "UTL_HTTP", "UTL_FILE", "UTL_SMTP", "UTL_TCP",
    # PostgreSQL high-risk
    "PG_SLEEP", "PG_READ_FILE", "PG_WRITE_FILE",
    # MySQL high-risk
    "SLEEP", "LOAD_FILE",
]


ALLOWED_LEAD_KEYWORDS: dict[str, set[str]] = {
    "oracle": {"SELECT", "WITH"},
    "postgresql": {"SELECT", "WITH", "SHOW"},
    "mysql": {"SELECT", "WITH", "SHOW"},
    "mssql": {"SELECT", "WITH"},
    "sqlserver": {"SELECT", "WITH"},
}


# Compile keyword patterns sorted longest-first so ``DBMS_LOCK`` wins over ``LOCK``.
_ESCAPED_KEYWORDS = sorted(
    (re.escape(k) for k in DANGEROUS_KEYWORDS), key=len, reverse=True
)
_DANGEROUS_PATTERN = re.compile(
    r"\b(" + "|".join(_ESCAPED_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
_SELECT_INTO_PATTERN = re.compile(
    r"\bSELECT\b.*\bINTO\b", re.IGNORECASE | re.DOTALL
)
_INTO_OUTFILE_PATTERN = re.compile(
    r"\bINTO\s+(OUTFILE|DUMPFILE)\b", re.IGNORECASE
)
_FOR_UPDATE_PATTERN = re.compile(r"\bFOR\s+UPDATE\b", re.IGNORECASE)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SINGLE_QUOTED = re.compile(r"'(?:[^']|'')*'")
_DOUBLE_QUOTED_IDENT = re.compile(r'"(?:[^"]|"")*"')
_IDENT_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_comments(sql: str) -> str:
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = _BLOCK_COMMENT.sub(" ", sql)
    return sql


def _mask_string_literals(sql: str) -> str:
    """Replace single-quoted strings with placeholders.

    ``SELECT 'DROP TABLE test' FROM dual`` must NOT match DROP.
    """
    # Handle ``''`` escaped quote: replace with placeholder first so we
    # don't accidentally match across the boundary.
    sql = sql.replace("''", "__ESC_QUOTE__")
    sql = _SINGLE_QUOTED.sub("__STR_LIT__", sql)
    sql = sql.replace("__ESC_QUOTE__", "''")
    return sql


def _mask_double_quoted_identifiers(sql: str) -> str:
    """Replace double-quoted identifiers (PostgreSQL ``"col"``, Oracle
    string literals with ``q'[...]'`` style alternatives).
    """
    return _DOUBLE_QUOTED_IDENT.sub("__IDENT__", sql)


def _first_keyword(sql: str) -> str:
    m = _IDENT_TOKEN.search(sql)
    return m.group(0).upper() if m else ""


def _split_strip_terminator(sql: str) -> tuple[str, bool]:
    stripped = sql.rstrip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()
        return stripped, True
    return stripped, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class SqlSafetyService:
    """Validate that a SQL string is a safe readonly statement."""

    DEFAULT_TIMEOUT_SECONDS = 30
    MAX_TIMEOUT_SECONDS = 120
    DEFAULT_MAX_ROWS = 200
    MAX_MAX_ROWS = 1000

    @staticmethod
    def compute_sql_hash(sql_text: str) -> str:
        return hashlib.sha256(sql_text.encode("utf-8")).hexdigest()

    @classmethod
    def validate_sql_readonly(
        cls, sql_text: str, db_type_code: str
    ) -> dict[str, Any]:
        """Return ``{valid, sql_hash, message, errors}`` for a SQL + db type.

        The frontend can render ``message`` as-is. ``errors`` is the raw
        list of violations for log/audit purposes.
        """
        db_type = (db_type_code or "").lower().strip()
        allowed = ALLOWED_LEAD_KEYWORDS.get(db_type, set())
        errors: list[str] = []

        if not sql_text or not sql_text.strip():
            errors.append("empty SQL")
            return {
                "valid": False,
                "sql_hash": "",
                "message": "SQL 为空",
                "errors": errors,
            }

        cleaned = _strip_comments(sql_text)
        masked = _mask_double_quoted_identifiers(_mask_string_literals(cleaned))

        if _SELECT_INTO_PATTERN.search(masked):
            errors.append("SELECT ... INTO is not allowed")
        if _INTO_OUTFILE_PATTERN.search(masked):
            errors.append("INTO OUTFILE/DUMPFILE is not allowed")
        if _FOR_UPDATE_PATTERN.search(masked):
            errors.append("FOR UPDATE is not allowed (would lock rows)")

        match = _DANGEROUS_PATTERN.search(masked)
        if match:
            errors.append(f"disallowed keyword: {match.group(0).upper()}")

        first = _first_keyword(masked)
        if allowed and first not in allowed:
            errors.append(
                f"first keyword must be one of {sorted(allowed)} "
                f"(got '{first or '<none>'}')"
            )

        stripped, _had_terminator = _split_strip_terminator(masked)
        if ";" in stripped:
            errors.append("multiple statements are not allowed")

        sql_hash = cls.compute_sql_hash(sql_text)
        message = "; ".join(errors) if errors else "SQL is read-only"
        return {
            "valid": not errors,
            "sql_hash": sql_hash,
            "message": message,
            "errors": errors,
        }

    @classmethod
    def validate_rule_config(
        cls, rule_config: dict[str, Any], db_type_code: str
    ) -> dict[str, Any]:
        """Validate a complete ``rule_config`` payload.

        Returns ``{valid, sql_hash, message, errors, normalized}`` where
        ``normalized`` carries the cleaned ``sql_text`` + clamped
        ``timeout_seconds`` + ``max_rows`` so the caller can persist them
        verbatim. Backend safety service is the primary gate; the collector
        client also runs an equivalent check as defense-in-depth.
        """
        errors: list[str] = []
        sql_text = (rule_config or {}).get("sql_text") or ""
        timeout_seconds = int(
            rule_config.get("timeout_seconds") or cls.DEFAULT_TIMEOUT_SECONDS
        )
        max_rows = int(
            rule_config.get("max_rows") or cls.DEFAULT_MAX_ROWS
        )

        if not (1 <= timeout_seconds <= cls.MAX_TIMEOUT_SECONDS):
            errors.append(
                f"timeout_seconds must be between 1 and {cls.MAX_TIMEOUT_SECONDS}"
            )
        if not (1 <= max_rows <= cls.MAX_MAX_ROWS):
            errors.append(
                f"max_rows must be between 1 and {cls.MAX_MAX_ROWS}"
            )

        check = cls.validate_sql_readonly(sql_text, db_type_code)
        if not check["valid"]:
            errors.extend(check["errors"])

        return {
            "valid": not errors,
            "sql_hash": check["sql_hash"],
            "message": check["message"],
            "errors": errors,
            "normalized": {
                "sql_text": sql_text.strip(),
                "timeout_seconds": timeout_seconds,
                "max_rows": max_rows,
                "result_status_column": (rule_config.get("result_status_column") or "RESULT_STATUS"),
                "message_column": (rule_config.get("message_column") or "MESSAGE"),
                "severity": (rule_config.get("severity") or "warning"),
            },
        }