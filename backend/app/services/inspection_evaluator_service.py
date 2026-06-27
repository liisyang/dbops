"""InspectionEvaluatorService — deterministic rule engine for inspection results.

Design principles:
- SQL collects raw data → Evaluator deterministically judges → AI explains/recommends
- AI must NOT modify evaluation_status, health_level, or health_score
- All evaluators are pure functions: no DB access, no randomness
- Column names are lowercased before matching
"""

from __future__ import annotations

from typing import Any


# Whitelist for multiple_rows.aggregate functions
VALID_AGGREGATE_FUNCTIONS = frozenset({"min", "max", "sum", "avg", "count"})


class EvaluatorError(ValueError):
    """Raised when evaluation fails due to malformed data or config."""


class InspectionEvaluatorService:
    """Deterministic rule engine for inspection result evaluation.

    Evaluates a single result row (from SQL execution) against the task
    item's rule_config_snapshot and returns (evaluation_status, findings, message).
    """

    RULE_ENGINE_VERSION = "1.0.0"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate(
        rule_config: dict[str, Any],
        columns: list[str],
        rows: list[list[Any]],
        *,
        execution_status: str = "success",
    ) -> dict[str, Any]:
        """Evaluate a single collector result against its rule config.

        Returns dict with:
          - evaluation_status: normal|warning|critical|unknown|not_evaluated
          - findings: list of per-row dicts (for multiple_rows.policy=each)
          - message: human-readable summary
        """
        if execution_status != "success":
            return {
                "evaluation_status": "unknown",
                "findings": [],
                "message": f"execution_status={execution_status}, skipping evaluation",
            }

        item_kind = (rule_config.get("item_kind") or "state").strip()
        evaluator_cfg = rule_config.get("evaluator") or {}
        evaluator_type = (evaluator_cfg.get("type") or "none").strip()
        normalized_columns = [c.strip().lower() for c in columns]

        # information items are never evaluated
        if item_kind == "information":
            return {
                "evaluation_status": "not_evaluated",
                "findings": [],
                "message": "information item, not evaluated",
            }

        # empty result → empty_result_policy
        if not rows:
            return InspectionEvaluatorService._handle_empty(rule_config)

        # evaluate each row
        row_results: list[str] = []
        for row_data in rows:
            row_dict = InspectionEvaluatorService._build_row_dict(
                normalized_columns, row_data
            )
            if evaluator_type == "none":
                status = "not_evaluated"
            elif evaluator_type == "range":
                status = InspectionEvaluatorService._eval_range(
                    evaluator_cfg, row_dict, rule_config
                )
            elif evaluator_type == "equals":
                status = InspectionEvaluatorService._eval_equals(
                    evaluator_cfg, row_dict, rule_config
                )
            elif evaluator_type == "not_equals":
                status = InspectionEvaluatorService._eval_not_equals(
                    evaluator_cfg, row_dict, rule_config
                )
            elif evaluator_type == "in":
                status = InspectionEvaluatorService._eval_in(
                    evaluator_cfg, row_dict, rule_config
                )
            elif evaluator_type == "not_in":
                status = InspectionEvaluatorService._eval_not_in(
                    evaluator_cfg, row_dict, rule_config
                )
            elif evaluator_type == "boolean":
                status = InspectionEvaluatorService._eval_boolean(
                    evaluator_cfg, row_dict, rule_config
                )
            elif evaluator_type == "status_column":
                status = InspectionEvaluatorService._eval_status_column(
                    evaluator_cfg, row_dict
                )
            else:
                status = "unknown"
            row_results.append(status)

        return InspectionEvaluatorService._aggregate_results(
            rule_config, row_results, normalized_columns, rows
        )

    # ------------------------------------------------------------------
    # Empty result handling
    # ------------------------------------------------------------------

    @staticmethod
    def _handle_empty(rule_config: dict[str, Any]) -> dict[str, Any]:
        policy = (rule_config.get("empty_result_policy") or "unknown").strip()
        valid = frozenset({"normal", "unknown", "warning", "critical"})
        if policy not in valid:
            policy = "unknown"
        return {
            "evaluation_status": policy,
            "findings": [],
            "message": f"no rows returned, empty_result_policy={policy}",
        }

    # ------------------------------------------------------------------
    # Per-row evaluators (8 types)
    # ------------------------------------------------------------------

    @staticmethod
    def _eval_range(
        evaluator_cfg: dict[str, Any],
        row: dict[str, Any],
        rule_config: dict[str, Any],
    ) -> str:
        value_sel = rule_config.get("value_selector") or {}
        column = (value_sel.get("column") or "").strip().lower()
        value = row.get(column)
        if value is None:
            return rule_config.get("null_value_policy") or "unknown"
        try:
            num = float(value)
        except (TypeError, ValueError):
            return "unknown"

        critical_cfg = evaluator_cfg.get("critical") or {}
        warning_cfg = evaluator_cfg.get("warning") or {}
        if InspectionEvaluatorService._threshold_match(num, critical_cfg):
            return "critical"
        if InspectionEvaluatorService._threshold_match(num, warning_cfg):
            return "warning"
        return "normal"

    @staticmethod
    def _threshold_match(value: float, threshold: dict[str, Any]) -> bool:
        if not threshold:
            return False
        if "gte" in threshold and value < threshold["gte"]:
            return False
        if "gt" in threshold and value <= threshold["gt"]:
            return False
        if "lte" in threshold and value > threshold["lte"]:
            return False
        if "lt" in threshold and value >= threshold["lt"]:
            return False
        if "eq" in threshold and value != threshold["eq"]:
            return False
        return True

    @staticmethod
    def _eval_equals(
        evaluator_cfg: dict[str, Any],
        row: dict[str, Any],
        rule_config: dict[str, Any],
    ) -> str:
        value_sel = rule_config.get("value_selector") or {}
        column = (value_sel.get("column") or "").strip().lower()
        expected = evaluator_cfg.get("expected")
        actual = row.get(column)
        if actual is None:
            return rule_config.get("null_value_policy") or "unknown"
        if str(actual).strip().lower() == str(expected).strip().lower():
            return "normal"
        return evaluator_cfg.get("on_mismatch") or "warning"

    @staticmethod
    def _eval_not_equals(
        evaluator_cfg: dict[str, Any],
        row: dict[str, Any],
        rule_config: dict[str, Any],
    ) -> str:
        value_sel = rule_config.get("value_selector") or {}
        column = (value_sel.get("column") or "").strip().lower()
        forbidden = evaluator_cfg.get("forbidden")
        actual = row.get(column)
        if actual is None:
            return rule_config.get("null_value_policy") or "unknown"
        if str(actual).strip().lower() == str(forbidden).strip().lower():
            return evaluator_cfg.get("on_match") or "critical"
        return "normal"

    @staticmethod
    def _eval_in(
        evaluator_cfg: dict[str, Any],
        row: dict[str, Any],
        rule_config: dict[str, Any],
    ) -> str:
        value_sel = rule_config.get("value_selector") or {}
        column = (value_sel.get("column") or "").strip().lower()
        allowed = evaluator_cfg.get("allowed") or []
        actual = row.get(column)
        if actual is None:
            return rule_config.get("null_value_policy") or "unknown"
        allowed_lower = {str(a).strip().lower() for a in allowed}
        if str(actual).strip().lower() in allowed_lower:
            return "normal"
        return evaluator_cfg.get("on_not_in") or "warning"

    @staticmethod
    def _eval_not_in(
        evaluator_cfg: dict[str, Any],
        row: dict[str, Any],
        rule_config: dict[str, Any],
    ) -> str:
        value_sel = rule_config.get("value_selector") or {}
        column = (value_sel.get("column") or "").strip().lower()
        forbidden = evaluator_cfg.get("forbidden") or []
        actual = row.get(column)
        if actual is None:
            return rule_config.get("null_value_policy") or "unknown"
        forbidden_lower = {str(f).strip().lower() for f in forbidden}
        if str(actual).strip().lower() in forbidden_lower:
            return evaluator_cfg.get("on_match") or "critical"
        return "normal"

    @staticmethod
    def _eval_boolean(
        evaluator_cfg: dict[str, Any],
        row: dict[str, Any],
        rule_config: dict[str, Any],
    ) -> str:
        value_sel = rule_config.get("value_selector") or {}
        column = (value_sel.get("column") or "").strip().lower()
        actual = row.get(column)
        if actual is None:
            return rule_config.get("null_value_policy") or "unknown"
        truthy = {True, 1, "1", "true", "yes", "t"}
        falsy = {False, 0, "0", "false", "no", "f"}
        val = actual if isinstance(actual, bool) else str(actual).strip().lower()
        if val in truthy:
            return evaluator_cfg.get("on_true") or "normal"
        if val in falsy:
            return evaluator_cfg.get("on_false") or "warning"
        return "unknown"

    @staticmethod
    def _eval_status_column(evaluator_cfg: dict[str, Any], row: dict[str, Any]) -> str:
        """Evaluate using SQL status column.

        Mapping: normal→normal, warning→warning, critical→critical,
        abnormal+severity=critical→critical, abnormal+other→warning,
        unknown→unknown, unrecognized→unknown.
        """
        status_col = (evaluator_cfg.get("status_column") or "result_status").strip().lower()
        severity_col = (evaluator_cfg.get("severity_column") or "severity").strip().lower()
        raw_status = str(row.get(status_col) or "").strip().lower()
        raw_severity = str(row.get(severity_col) or "").strip().lower()

        if raw_status == "normal":
            return "normal"
        if raw_status == "warning":
            return "warning"
        if raw_status == "critical":
            return "critical"
        if raw_status == "abnormal":
            return "critical" if raw_severity == "critical" else "warning"
        if raw_status == "unknown":
            return "unknown"
        return "unknown"

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_results(
        rule_config: dict[str, Any],
        row_results: list[str],
        columns: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        multi_cfg = rule_config.get("multiple_rows") or {}
        policy = (multi_cfg.get("policy") or "first").strip()

        if policy == "first":
            return InspectionEvaluatorService._agg_first(rule_config, row_results, columns, rows)
        if policy == "each":
            return InspectionEvaluatorService._agg_each(rule_config, row_results, columns, rows)
        if policy == "worst":
            return InspectionEvaluatorService._agg_worst(rule_config, row_results, columns, rows)
        if policy == "aggregate":
            return InspectionEvaluatorService._agg_aggregate(rule_config, multi_cfg, columns, rows)
        return InspectionEvaluatorService._agg_worst(rule_config, row_results, columns, rows)

    @staticmethod
    def _agg_first(
        rule_config: dict[str, Any],
        row_results: list[str],
        columns: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        status = row_results[0] if row_results else "unknown"
        msg_template = rule_config.get("message_template") or ""
        message = InspectionEvaluatorService._format_message(msg_template, columns, rows[0] if rows else [])
        return {
            "evaluation_status": status,
            "findings": [{"row_index": 0, "evaluation_status": status, "message": message}],
            "message": message,
        }

    @staticmethod
    def _agg_each(
        rule_config: dict[str, Any],
        row_results: list[str],
        columns: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        msg_template = rule_config.get("message_template") or ""
        findings = []
        for i, (status, row_data) in enumerate(zip(row_results, rows)):
            message = InspectionEvaluatorService._format_message(msg_template, columns, row_data)
            findings.append({"row_index": i, "evaluation_status": status, "message": message})
        parent = InspectionEvaluatorService._worst_status(row_results)
        return {
            "evaluation_status": parent,
            "findings": findings,
            "message": f"{len(findings)} row(s) evaluated, worst={parent}",
        }

    @staticmethod
    def _agg_worst(
        rule_config: dict[str, Any],
        row_results: list[str],
        columns: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        status = InspectionEvaluatorService._worst_status(row_results)
        msg_template = rule_config.get("message_template") or ""
        findings = []
        for i, (s, row_data) in enumerate(zip(row_results, rows)):
            findings.append({
                "row_index": i,
                "evaluation_status": s,
                "message": InspectionEvaluatorService._format_message(msg_template, columns, row_data),
            })
        return {
            "evaluation_status": status,
            "findings": findings,
            "message": f"worst among {len(findings)} row(s): {status}",
        }

    @staticmethod
    def _agg_aggregate(
        rule_config: dict[str, Any],
        multi_cfg: dict[str, Any],
        columns: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        agg_func = (multi_cfg.get("aggregate") or "sum").strip().lower()
        if agg_func not in VALID_AGGREGATE_FUNCTIONS:
            raise EvaluatorError(f"invalid aggregate function: {agg_func}")

        evaluator_cfg = rule_config.get("evaluator") or {}
        value_sel = rule_config.get("value_selector") or {}
        col_name = (value_sel.get("column") or "").strip().lower()
        if col_name not in columns:
            raise EvaluatorError(f"aggregate column '{col_name}' not found in {columns}")

        col_idx = columns.index(col_name)
        values: list[float] = []
        for row_data in rows:
            try:
                values.append(float(row_data[col_idx]))
            except (TypeError, ValueError, IndexError):
                values.append(0.0)

        if agg_func == "min":
            result_value = min(values)
        elif agg_func == "max":
            result_value = max(values)
        elif agg_func == "avg":
            result_value = sum(values) / len(values) if values else 0.0
        elif agg_func == "count":
            result_value = float(len(values))
        else:
            result_value = sum(values)

        single_row = {col_name: result_value}
        status = InspectionEvaluatorService._eval_range(evaluator_cfg, single_row, rule_config)
        return {
            "evaluation_status": status,
            "findings": [{"row_index": 0, "evaluation_status": status, "message": f"aggregate {agg_func}({col_name})={result_value}"}],
            "message": f"aggregate {agg_func}({col_name})={result_value} → {status}",
        }

    # ------------------------------------------------------------------
    # Health scoring
    # ------------------------------------------------------------------

    @staticmethod
    def compute_instance_health(results: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute health_level and health_score for one instance."""
        evaluable = [r for r in results if r.get("evaluation_status") != "not_evaluated"]
        all_not_evaluated = len(evaluable) == 0

        counts = {
            "normal_count": sum(1 for r in evaluable if r["evaluation_status"] == "normal"),
            "warning_count": sum(1 for r in evaluable if r["evaluation_status"] == "warning"),
            "critical_count": sum(1 for r in evaluable if r["evaluation_status"] == "critical"),
            "unknown_count": sum(1 for r in evaluable if r["evaluation_status"] == "unknown"),
            "not_evaluated_count": len(results) - len(evaluable),
        }

        if all_not_evaluated:
            return {"health_level": "not_assessed", "health_score": None, **counts}

        penalty_map = {"normal": 0.0, "warning": 0.4, "critical": 1.0, "unknown": 0.2}
        total_weighted = 0.0
        total_penalty = 0.0
        has_critical = False
        has_warning = False
        has_unknown = False

        for r in evaluable:
            weight = float(r.get("weight", 10))
            status = r["evaluation_status"]
            total_weighted += weight
            total_penalty += weight * penalty_map.get(status, 0.0)
            if status == "critical":
                has_critical = True
            elif status == "warning":
                has_warning = True
            elif status == "unknown":
                has_unknown = True

        if total_weighted == 0:
            return {"health_level": "not_assessed", "health_score": None, **counts}

        score = round(100.0 * (1.0 - total_penalty / total_weighted), 2)
        score = max(0.0, min(100.0, score))

        if has_critical:
            level = "critical"
        elif has_warning:
            level = "warning"
        elif has_unknown:
            level = "unknown"
        else:
            level = "healthy"

        return {"health_level": level, "health_score": score, **counts}

    @staticmethod
    def compute_report_health(instance_healths: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute overall report health from instance health dicts."""
        scores = [h["health_score"] for h in instance_healths if h.get("health_score") is not None]
        levels = [h.get("health_level") for h in instance_healths if h.get("health_level")]

        if not levels:
            return {"health_level": "not_assessed", "health_score": None}

        if "critical" in levels:
            level = "critical"
        elif "warning" in levels:
            level = "warning"
        elif "unknown" in levels:
            level = "unknown"
        elif all(l == "not_assessed" for l in levels):
            level = "not_assessed"
        else:
            level = "healthy"

        avg_score = round(sum(scores) / len(scores), 2) if scores else None
        return {"health_level": level, "health_score": avg_score}

    # ------------------------------------------------------------------
    # Rule config cross-field validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_rule_config(rule_config: dict[str, Any]) -> list[str]:
        """Cross-field validation. Returns list of error messages."""
        errors: list[str] = []
        item_kind = (rule_config.get("item_kind") or "state").strip()
        evaluator = rule_config.get("evaluator") or {}
        evaluator_type = (evaluator.get("type") or "none").strip()

        if item_kind == "information" and evaluator_type != "none":
            errors.append("item_kind=information requires evaluator.type=none")
        if item_kind == "composite" and evaluator_type != "status_column":
            errors.append("item_kind=composite requires evaluator.type=status_column")
        if evaluator_type == "range":
            vs = evaluator.get("value_selector") or {}
            if not vs.get("column"):
                errors.append("evaluator.type=range requires value_selector.column")
            has_c = bool(evaluator.get("critical"))
            has_w = bool(evaluator.get("warning"))
            if not has_c and not has_w:
                errors.append("evaluator.type=range requires at least one threshold")
            if has_c and has_w and "gte" in evaluator["critical"] and "gte" in evaluator["warning"]:
                if evaluator["critical"]["gte"] < evaluator["warning"]["gte"]:
                    errors.append("critical threshold must not be weaker than warning")

        empty_policy = rule_config.get("empty_result_policy")
        if empty_policy == "not_applicable":
            errors.append("empty_result_policy=not_applicable is not allowed")

        multi = rule_config.get("multiple_rows") or {}
        if multi.get("policy") == "aggregate" and not multi.get("aggregate"):
            errors.append("multiple_rows.policy=aggregate requires multiple_rows.aggregate")

        return errors

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_row_dict(columns: list[str], row: list[Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for i, col in enumerate(columns):
            result[col] = row[i] if i < len(row) else None
        return result

    @staticmethod
    def _worst_status(statuses: list[str]) -> str:
        priority = {"critical": 3, "warning": 2, "unknown": 1, "normal": 0, "not_evaluated": -1}
        worst = "normal"
        worst_p = -1
        for s in statuses:
            p = priority.get(s, 0)
            if p > worst_p:
                worst_p = p
                worst = s
        return worst

    @staticmethod
    def _format_message(template: str, columns: list[str], row: list[Any]) -> str:
        if not template:
            return ""
        result = template
        for i, col in enumerate(columns):
            placeholder = "{" + col + "}"
            value = row[i] if i < len(row) else ""
            if value is None:
                value = ""
            result = result.replace(placeholder, str(value))
        return result
