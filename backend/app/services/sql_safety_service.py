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

Phase 3.6 C11: ``validate_with_ast`` adds an authoritative AST-based gate
powered by sqlglot. The regex-based :meth:`validate_sql_readonly` is kept
as defense-in-depth (Layer 2 in the 6-layer SQL safety model); the AST
layer (Layer 3) is now the primary gate and additionally enforces
schema-policy whitelists (``allowed_tables`` / ``allowed_columns``) and
the ``denied_columns`` blocklist from the active schema policy.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Phase 3.6 C11: sqlglot is the authoritative AST gate (Layer 3 in
# plan §5 6-layer SQL safety model). Imported lazily inside
# ``validate_with_ast`` so the existing regex path stays usable even
# when sqlglot is somehow unavailable (e.g. emergency hot-patch).
try:
    import sqlglot
    from sqlglot import expressions as _sqlglot_exp
    _HAS_SQLGLOT = True
except ImportError:  # pragma: no cover - sqlglot is in requirements.txt
    _HAS_SQLGLOT = False
    sqlglot = None  # type: ignore[assignment]
    _sqlglot_exp = None  # type: ignore[assignment]


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


# ---------------------------------------------------------------------------
# Phase 3.6 C11 — AST-based authoritative gate
# ---------------------------------------------------------------------------

# Dialect mapping (plan §5 line 579). First version only requires
# PostgreSQL to pass tests; the mapping exists so the same method is
# ready for Oracle/MSSQL/MySQL when those policy snapshots ship.
_DIALECT_MAP: dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mssql": "tsql",
    "sqlserver": "tsql",
    "tsql": "tsql",
    "oracle": "oracle",
    "mysql": "mysql",
}

# Defense-in-depth sensitive column pattern (plan §5 P1 layer 2).
# Blocklist via ``denied_columns`` from Schema Policy takes priority
# (it produces errors); this pattern only emits warnings so the
# downstream executor can still mask the column at row-fetch time.
_SENSITIVE_COLUMN_PATTERN = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|credential|credentials|"
    r"api[_-]?key|access[_-]?key|private[_-]?key|"
    r"phone|mobile|tel|email|e[_-]?mail|"
    r"id[_-]?card|idcard|ssn|social[_-]?security)\b"
)


def _resolve_sqlglot_dialect(db_type_code: str) -> str | None:
    code = (db_type_code or "").lower().strip()
    return _DIALECT_MAP.get(code)


def _qualified_name(schema: str | None, table: str | None) -> str | None:
    """Return ``schema.table`` lowercased, or None when table is empty."""
    if not table:
        return None
    if schema:
        return f"{schema.lower()}.{table.lower()}"
    return table.lower()


def _extract_column_identifiers(
    projection: Any,
) -> list[tuple[str, str | None]]:
    """Return list of ``(column_name, table_alias_or_None)`` from a projection.

    Walks into common wrappers (Alias, Cast, Boolean wrappers) so the
    underlying ``Column`` is reached. Literals (``SELECT 1``) and
    functions are reported as ``("", None)`` and excluded from the
    whitelist check by the caller.
    """
    from sqlglot import expressions as exp  # local import; module-level guard

    # Alias keeps the output alias; the expression itself lives under .this
    inner = projection
    while isinstance(inner, (exp.Alias, exp.Cast)):
        inner = inner.this

    if isinstance(inner, exp.Column):
        return [(inner.name.lower(), (inner.table or "").lower() or None)]
    if isinstance(inner, exp.Literal):
        # Literal in SELECT list — not a column reference.
        return [("", None)]
    if isinstance(inner, (exp.Star,)):
        # Handled separately by the caller via _collect_star_descriptors.
        return []
    # Function calls, CASE, etc. — best-effort: scan for Column children.
    found: list[tuple[str, str | None]] = []
    for col in inner.find_all(exp.Column):
        found.append((col.name.lower(), (col.table or "").lower() or None))
    return found


def _collect_star_descriptors(
    projections: list[Any],
) -> list[str]:
    """Return a list of human-readable descriptors for every ``*`` /
    ``table.*`` projection.

    Empty list means no star was found. Each descriptor is one of:
    ``"*"`` (bare star) or ``"alias.*"`` / ``"table.*"`` (qualified).
    """
    from sqlglot import expressions as exp

    out: list[str] = []
    for proj in projections:
        # Bare ``SELECT *`` — projection itself is Star.
        if isinstance(proj, exp.Star):
            out.append("*")
            continue
        # Column-wrapped Star: ``SELECT u.*`` ⇒ Column(this=Star(), table=...)
        if isinstance(proj, exp.Column):
            if isinstance(proj.this, exp.Star):
                tbl = proj.table or ""
                out.append(f"{tbl}.*" if tbl else "*")
    return out


def _collect_from_sources(ast: Any) -> list[tuple[str | None, str, str | None]]:
    """Return ``[(schema_or_None, table_name, alias_or_None), ...]`` for every
    physical table referenced by the AST (FROM + JOIN + CTE).

    Subqueries are excluded: the ``Subquery`` node is not an
    ``exp.Table``, so ``find_all(exp.Table)`` automatically skips them.
    CTE aliases also appear as ``exp.Table`` references in the outer
    query — they are returned as-is so column resolution can match
    them, but the caller is responsible for skipping them in the
    table-whitelist check (use :func:`_collect_cte_aliases` to detect).
    """
    from sqlglot import expressions as exp

    out: list[tuple[str | None, str, str | None]] = []
    for src in ast.find_all(exp.Table):
        schema = src.args.get("db").name if src.args.get("db") else None
        alias = src.alias if hasattr(src, "alias") else None
        # alias may be empty string when absent — coerce to None for clarity.
        alias = alias or None
        out.append((schema, src.name, alias))
    return out


def _collect_cte_aliases(ast: Any) -> set[str]:
    """Return the set of CTE aliases declared at the top of the query
    (i.e. ``WITH x AS (...) SELECT ... FROM x``). Lowercased.
    """
    from sqlglot import expressions as exp

    aliases: set[str] = set()
    with_node = ast.args.get("with")
    if with_node is None:
        return aliases
    for cte in with_node.expressions:
        if cte.alias:
            aliases.add(cte.alias.lower())
    return aliases


def _ast_has_lock_clause(ast: Any) -> bool:
    """Return True when the AST carries any FOR UPDATE / FOR SHARE lock.

    sqlglot represents these as ``locks=[Lock(update=True/False, ...)]``
    on the Select node. We also walk the tree for any Lock descendant
    in case the dialect stores it elsewhere.
    """
    from sqlglot import expressions as exp

    locks = ast.args.get("locks") or []
    if locks:
        return True
    for _ in ast.find_all(exp.Lock):
        return True
    return False


def _ast_has_into_clause(ast: Any) -> bool:
    """Return True when the AST carries a SELECT … INTO destination.

    sqlglot exposes this via ``ast.args.get('into')`` for postgres dialect.
    """
    return ast.args.get("into") is not None


def _is_top_level_readonly(ast: Any) -> bool:
    """True when the AST root is a read-only statement (SELECT, optionally
    wrapped in WITH/CTE). Anything else (INSERT/UPDATE/DELETE/MERGE/...)
    is rejected.
    """
    from sqlglot import expressions as exp

    return isinstance(ast, exp.Select)


class SqlSafetyService:
    """Validate that a SQL string is a safe readonly statement."""

    DEFAULT_TIMEOUT_SECONDS = 30
    MAX_TIMEOUT_SECONDS = 120
    DEFAULT_MAX_ROWS = 200
    MAX_MAX_ROWS = 1000

    # Defense-in-depth pattern of sensitive column names (plan §5 P1 layer 2).
    SENSITIVE_COLUMN_PATTERN = _SENSITIVE_COLUMN_PATTERN

    # ------------------------------------------------------------------
    # Phase 3.6 C13 — Layer 1: Dify Code 节点 JSON 解析 + 正则预检
    # ------------------------------------------------------------------
    #
    # Layer 1 由两部分组成：
    #   (a) 正则预检（本方法 layer1_precheck_question）：在调 Dify 之前用
    #       正则快速拦截用户问题中明显的非只读关键词（中英文：删除/
    #       DROP/DELETE/...）。命中 → 直接构造 rejected audit，**不再调
    #       Dify**，节省 token + 延迟 + Dify 配额。
    #   (b) Dify Code 节点 JSON 解析（在 AiSqlPreviewService 内实现）：
    #       解析结构化 JSON 输出 {generated_sql, warnings, table_refs,
    #       confidence, explanation}，稳健处理字段缺失。
    #
    # 本方法只实现 (a)。SQL 关键字（SQL 文本层）的拦截由 Layer 2
    # (validate_sql_readonly) + Layer 3 (validate_with_ast) 负责。

    # Layer 1 中英文关键词（中英文都覆盖；中文用子串匹配）
    _LAYER1_DANGEROUS_KEYWORDS_EN = [
        "DROP", "DELETE", "UPDATE", "INSERT", "TRUNCATE", "ALTER",
        "CREATE", "GRANT", "REVOKE", "MERGE",
        "EXEC", "EXECUTE", "CALL",
    ]
    _LAYER1_DANGEROUS_KEYWORDS_CN = [
        # 严格动词 + 强烈意图；放前面
        "删除", "删掉", "写入", "插入", "截断",
        "建表", "建库", "建索引", "建视图",
        "授权", "撤销", "改结构", "改字段",
    ]

    @classmethod
    def layer1_precheck_question(cls, user_question: str) -> dict[str, Any]:
        """Layer 1 正则预检（plan §5 Layer 1）。

        检查 ``user_question`` 中是否含有明显的非只读意图（中英文关键词）。
        命中 → 建议上层 service 直接构造 rejected audit 返回，不再调 Dify。

        Args:
            user_question: 用户原始问题（来自 Chat 或独立 SQL Preview 页）

        Returns:
            dict:
              - allowed (bool)         — True 表示未命中，可继续调 Dify
              - reason (str|None)      — 人类可读的拒绝原因（命中时填）
              - matched_keyword (str|None) — 命中的关键词
              - matched_pattern (str|None) — "cn" | "en" | None
              - error_code (str|None)  — 机器可读错误码（命中时 = "LAYER1_DANGEROUS_KEYWORD"）

        关键设计：
        - 简单正则匹配，**不**做语义分析；Layer 3 AST 是兜底
        - 中英文分别用不同策略：英文用 ``\\b`` 词边界，中文用子串匹配
        - 不区分大小写（英文）
        - 空 / 纯标点问题允许通过（不会凭空拦截）
        """
        if not user_question or not user_question.strip():
            return {
                "allowed": True,
                "reason": None,
                "matched_keyword": None,
                "matched_pattern": None,
                "error_code": None,
            }

        text = user_question.strip()

        # 英文：\b 词边界
        en_pattern = re.compile(
            r"\b(" + "|".join(cls._LAYER1_DANGEROUS_KEYWORDS_EN) + r")\b",
            re.IGNORECASE,
        )
        en_match = en_pattern.search(text)
        if en_match:
            kw = en_match.group(0).upper()
            return {
                "allowed": False,
                "reason": (
                    f"问题包含非只读关键词 '{kw}'；"
                    "AI Copilot SQL Preview 仅支持只读（SELECT）查询"
                ),
                "matched_keyword": kw,
                "matched_pattern": "en",
                "error_code": "LAYER1_DANGEROUS_KEYWORD",
            }

        # 中文：子串匹配
        for kw in cls._LAYER1_DANGEROUS_KEYWORDS_CN:
            if kw in text:
                return {
                    "allowed": False,
                    "reason": (
                        f"问题包含非只读关键词 '{kw}'；"
                        "AI Copilot SQL Preview 仅支持只读（SELECT）查询"
                    ),
                    "matched_keyword": kw,
                    "matched_pattern": "cn",
                    "error_code": "LAYER1_DANGEROUS_KEYWORD",
                }

        return {
            "allowed": True,
            "reason": None,
            "matched_keyword": None,
            "matched_pattern": None,
            "error_code": None,
        }

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

    # ------------------------------------------------------------------
    # Phase 3.6 C11 — AST-based authoritative gate
    # ------------------------------------------------------------------

    @classmethod
    def resolve_dialect(cls, db_type_code: str) -> str | None:
        """Public helper so callers (and tests) can resolve a db_type_code
        to a sqlglot dialect name without re-implementing the map."""
        return _resolve_sqlglot_dialect(db_type_code)

    @classmethod
    def validate_with_ast(
        cls,
        sql_text: str,
        db_type_code: str,
        *,
        allowed_tables: list[str] | None = None,
        allowed_columns: dict[str, list[str]] | None = None,
        denied_columns: list[str] | None = None,
        max_rows: int = 100,
    ) -> dict[str, Any]:
        """Authoritative SQL safety gate powered by sqlglot AST (plan §5).

        Returns::

            {
                "valid": bool,
                "approved_sql": str,        # sqlglot-canonical form
                "approved_sql_hash": str,   # SHA-256 of approved_sql
                "errors": [str, ...],       # hard violations → reject
                "warnings": [str, ...],     # soft hints (sensitive column
                                            # pattern matched; downstream
                                            # executor should mask at
                                            # row-fetch time per plan §5)
            }

        Layer 3 of the 6-layer SQL safety model. ``allowed_tables`` and
        ``allowed_columns`` come from the active Schema Policy snapshot
        (plan §4.5/§4.6). ``denied_columns`` is the policy blocklist;
        matching columns produce errors. The generic sensitive-name
        pattern is applied as a second layer that only emits warnings.

        ``max_rows`` is clamped but not enforced here — it is forwarded
        to the executor via the rule_config and enforced by the
        Collector EE. The clamp is documented here so callers cannot
        pass a wildly large value by accident.
        """
        errors: list[str] = []
        warnings: list[str] = []
        allowed_tables = list(allowed_tables or [])
        allowed_columns = dict(allowed_columns or {})
        denied_columns = list(denied_columns or [])

        # Normalize denied/allowed tables to lowercased qualified names.
        allowed_tables_lc = {
            t.lower() for t in allowed_tables if isinstance(t, str) and t
        }
        allowed_columns_lc: dict[str, set[str]] = {
            (k.lower()): {c.lower() for c in (v or [])}
            for k, v in allowed_columns.items()
        }
        denied_columns_lc = {c.lower() for c in denied_columns if c}

        # Clamp max_rows to a sane upper bound. The executor enforces the
        # real value; we surface the clamped value to the caller so they
        # know what was actually accepted.
        try:
            max_rows = int(max_rows)
        except (TypeError, ValueError):
            errors.append("max_rows must be an integer")
            max_rows = cls.DEFAULT_MAX_ROWS
        if max_rows < 1:
            errors.append("max_rows must be >= 1")
            max_rows = cls.DEFAULT_MAX_ROWS
        if max_rows > cls.MAX_MAX_ROWS:
            warnings.append(
                f"max_rows={max_rows} exceeds MAX_MAX_ROWS={cls.MAX_MAX_ROWS}; "
                f"clamped to {cls.MAX_MAX_ROWS}"
            )
            max_rows = cls.MAX_MAX_ROWS

        if not sql_text or not sql_text.strip():
            errors.append("empty SQL")
            return {
                "valid": False,
                "approved_sql": "",
                "approved_sql_hash": "",
                "errors": errors,
                "warnings": warnings,
            }

        if not _HAS_SQLGLOT:
            errors.append("sqlglot is required for validate_with_ast but is not installed")
            return {
                "valid": False,
                "approved_sql": sql_text.strip(),
                "approved_sql_hash": cls.compute_sql_hash(sql_text.strip()),
                "errors": errors,
                "warnings": warnings,
            }

        dialect = _resolve_sqlglot_dialect(db_type_code)
        if dialect is None:
            errors.append(
                f"unsupported db_type_code for AST validation: {db_type_code!r}"
            )
            return {
                "valid": False,
                "approved_sql": sql_text.strip(),
                "approved_sql_hash": cls.compute_sql_hash(sql_text.strip()),
                "errors": errors,
                "warnings": warnings,
            }

        # Multi-statement detection (use parse() which returns all statements).
        # parse_one() silently returns only the first statement.
        try:
            statements = sqlglot.parse(sql_text, read=dialect)
        except sqlglot.errors.ParseError as exc:
            errors.append(f"SQL parse error: {exc}")
            return {
                "valid": False,
                "approved_sql": sql_text.strip(),
                "approved_sql_hash": cls.compute_sql_hash(sql_text.strip()),
                "errors": errors,
                "warnings": warnings,
            }
        except Exception as exc:  # noqa: BLE001 — sqlglot raises a few distinct exception types
            errors.append(f"SQL parse error: {exc}")
            return {
                "valid": False,
                "approved_sql": sql_text.strip(),
                "approved_sql_hash": cls.compute_sql_hash(sql_text.strip()),
                "errors": errors,
                "warnings": warnings,
            }

        # Filter out empty / comment-only statements sqlglot sometimes emits
        # (e.g. trailing ``;``).
        non_empty = [
            s for s in statements
            if s is not None and s.sql(dialect=dialect).strip().strip(";").strip()
        ]
        if len(non_empty) != 1:
            errors.append(
                f"expected exactly 1 statement, got {len(non_empty)}"
            )
            return {
                "valid": False,
                "approved_sql": sql_text.strip(),
                "approved_sql_hash": cls.compute_sql_hash(sql_text.strip()),
                "errors": errors,
                "warnings": warnings,
            }

        ast = non_empty[0]
        if not _is_top_level_readonly(ast):
            errors.append(
                f"only SELECT/WITH statements are allowed (got "
                f"{type(ast).__name__})"
            )
            return {
                "valid": False,
                "approved_sql": sql_text.strip(),
                "approved_sql_hash": cls.compute_sql_hash(sql_text.strip()),
                "errors": errors,
                "warnings": warnings,
            }

        # Defense-in-depth: SELECT INTO and FOR UPDATE. sqlglot normalizes
        # both; the AST layer should catch them, but we double-check in
        # case a future dialect version emits them differently.
        if _ast_has_into_clause(ast):
            errors.append("SELECT ... INTO is not allowed")
        if _ast_has_lock_clause(ast):
            errors.append("FOR UPDATE / FOR SHARE is not allowed (would lock rows)")

        # P1 SELECT * / table.* — reject unconditionally.
        star_descs = _collect_star_descriptors(ast.expressions)
        if star_descs:
            errors.append(
                "SELECT * / table.* is not allowed; all output columns "
                "must be explicit (got: " + ", ".join(sorted(set(star_descs))) + ")"
            )

        # Whitelist: every FROM source must be in allowed_tables.
        sources = _collect_from_sources(ast)
        if not sources:
            errors.append("no FROM source found; SELECT must reference at least one table")
        cte_aliases = _collect_cte_aliases(ast)
        for schema, table, _alias in sources:
            # CTE aliases are virtual tables — they are not in the schema
            # policy whitelist (the policy describes physical schema, not
            # query-local derived tables). Skip the whitelist check.
            if table.lower() in cte_aliases:
                continue
            qname = _qualified_name(schema, table)
            if qname is None:
                errors.append("FROM source with empty table name")
                continue
            if allowed_tables_lc and qname not in allowed_tables_lc:
                # Be helpful: also try the bare table name (in case the
                # policy was registered without a schema prefix).
                bare = table.lower()
                if bare not in allowed_tables_lc:
                    errors.append(
                        f"table {qname!r} is not in the schema policy whitelist"
                    )

        # Whitelist: every output column must resolve to allowed_columns.
        # We collect every physical column referenced by any projection,
        # including inside functions / CASE expressions.
        all_output_columns = _extract_all_physical_columns(ast)
        if not all_output_columns and not star_descs:
            # No columns at all and no star → literal-only SELECT; that's
            # allowed but meaningless. We only flag if the user did not
            # explicitly reference any column.
            warnings.append("SELECT returns no columns")

        for col_name, qname in all_output_columns:
            # Resolve the physical table for the column reference.
            target_table = cls._resolve_column_target_table(
                col_name=col_name,
                qname=qname,
                sources=sources,
                allowed_tables_lc=allowed_tables_lc,
                allowed_columns_lc=allowed_columns_lc,
                errors=errors,
            )
            if target_table is None:
                # An error was already recorded; skip this column.
                continue
            allowed_cols = allowed_columns_lc.get(target_table, set())
            if allowed_cols and col_name not in allowed_cols:
                errors.append(
                    f"column {col_name!r} is not allowed for table {target_table!r}"
                )
                continue
            # First layer: explicit denied_columns from Schema Policy.
            if col_name in denied_columns_lc:
                errors.append(
                    f"column {col_name!r} is in the schema policy denied list"
                )
                continue
            # Second layer: pattern-based sensitive name detection (warning only).
            if cls.SENSITIVE_COLUMN_PATTERN.search(col_name):
                warnings.append(
                    f"column {col_name!r} matches sensitive-name pattern; "
                    f"downstream executor should mask at row-fetch time"
                )

        # Hard errors short-circuit any further approval. The approved_sql
        # hash is still computed against the raw input so callers can
        # observe "this exact input was rejected".
        if errors:
            stripped = sql_text.strip()
            return {
                "valid": False,
                "approved_sql": stripped,
                "approved_sql_hash": cls.compute_sql_hash(stripped),
                "errors": errors,
                "warnings": warnings,
            }

        # Approved form: sqlglot-canonical SQL in the target dialect. This
        # is what will be persisted as ``approved_sql`` and re-hashed at
        # execute time (plan §5 P0-4). Empty trailing ``;`` is normalized away.
        approved_sql = ast.sql(dialect=dialect).strip().rstrip(";").strip()
        approved_sql_hash = cls.compute_sql_hash(approved_sql)

        return {
            "valid": True,
            "approved_sql": approved_sql,
            "approved_sql_hash": approved_sql_hash,
            "errors": [],
            "warnings": warnings,
        }

    @staticmethod
    def _resolve_column_target_table(
        *,
        col_name: str,
        qname: str | None,
        sources: list[tuple[str | None, str, str | None]],
        allowed_tables_lc: set[str],
        allowed_columns_lc: dict[str, set[str]],
        errors: list[str],
    ) -> str | None:
        """Resolve a column reference to its fully-qualified table.

        Resolution rules:

        * ``u.id`` where ``u`` matches a FROM alias → the underlying table.
        * ``public.users.id`` where the schema+table matches → that table.
        * Bare ``id`` is rejected outright when more than one FROM source
          is present (cannot uniquely resolve), unless the column exists in
          exactly one of the allowed columns maps (P1 §5 unambiguous rule).
        """
        from sqlglot import expressions as exp  # local

        # Qualified column with explicit alias → resolve alias → table.
        if qname is not None:
            # First try: qname is an alias.
            for schema, table, alias in sources:
                if alias and alias.lower() == qname.lower():
                    return _qualified_name(schema, table)
            # Second try: qname is already schema.table.
            for schema, table, _alias in sources:
                if _qualified_name(schema, table) == qname.lower():
                    return qname.lower()
            # Third try: qname is a bare table name.
            for schema, table, _alias in sources:
                if table.lower() == qname.lower():
                    return _qualified_name(schema, table)
            # Could not resolve — treat as error.
            errors.append(
                f"column {col_name!r} references unknown table/alias {qname!r}"
            )
            return None

        # Unqualified column → must uniquely resolve.
        candidate_tables: list[str] = []
        for schema, table, _alias in sources:
            qn = _qualified_name(schema, table)
            if qn is None:
                continue
            if not allowed_columns_lc:
                # No whitelist means we cannot disambiguate across tables.
                candidate_tables.append(qn)
                continue
            cols_here = allowed_columns_lc.get(qn, set())
            if not cols_here:
                # No column whitelist on this table — skip (we already
                # validated that the table is in allowed_tables_lc).
                continue
            if col_name in cols_here:
                candidate_tables.append(qn)

        if len(candidate_tables) == 1:
            return candidate_tables[0]
        if len(candidate_tables) == 0:
            # If no whitelist applies, fall back to the single-source case.
            if not allowed_columns_lc and len(sources) == 1:
                schema, table, _alias = sources[0]
                qn = _qualified_name(schema, table)
                if qn is not None:
                    return qn
            errors.append(
                f"unqualified column {col_name!r} cannot be resolved: "
                f"not present in any whitelisted column set"
            )
            return None

        errors.append(
            f"unqualified column {col_name!r} is ambiguous across "
            f"{len(candidate_tables)} tables: "
            f"{', '.join(sorted(candidate_tables))}"
        )
        return None


def _extract_all_physical_columns(ast: Any) -> list[tuple[str, str | None]]:
    """Return ``[(column_name, table_or_alias_or_None), ...]`` for every
    physical ``Column`` referenced at the top-level SELECT scope.

    Top-level scope includes the SELECT list, WHERE, GROUP BY, HAVING,
    ORDER BY, JOIN ON clauses, etc. — but **not** columns inside
    CTE bodies (``WITH x AS (SELECT ...)``) or derived subqueries
    (``FROM (SELECT ...) AS u``). Those nested scopes get their own
    From source list and their own validation when the executor
    descends into them.

    Aliases and literals are skipped. Star-only projections are skipped
    (handled separately by ``_collect_star_descriptors``).
    """
    from sqlglot import expressions as exp

    out: list[tuple[str, str | None]] = []
    # BFS over the top-level SELECT only; do not descend into nested
    # Select / Subquery nodes (those are independent scopes).
    queue: list[Any] = [ast]
    visited: set[int] = {id(ast)}
    while queue:
        node = queue.pop(0)
        if isinstance(node, exp.Column):
            if not isinstance(node.this, exp.Star):
                out.append((node.name.lower(), (node.table or "").lower() or None))
        # Iterate over the node's direct children (each arg in args dict
        # plus the ``this`` field if any). We skip Select/Subquery
        # descendants — those are separate scopes.
        for key, value in (node.args or {}).items():
            if value is None:
                continue
            if isinstance(value, exp.Select):
                # Skip nested Select nodes (subquery / CTE body).
                continue
            if isinstance(value, exp.Subquery):
                # Skip nested subqueries — they are their own scope.
                continue
            if isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, exp.Expression) and id(item) not in visited:
                        # Do not descend into Select/Subquery children.
                        if isinstance(item, (exp.Select, exp.Subquery)):
                            continue
                        visited.add(id(item))
                        queue.append(item)
            elif isinstance(value, exp.Expression) and id(value) not in visited:
                if isinstance(value, (exp.Select, exp.Subquery)):
                    continue
                visited.add(id(value))
                queue.append(value)
    # De-dup while preserving order.
    seen: set[tuple[str, str | None]] = set()
    deduped: list[tuple[str, str | None]] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped