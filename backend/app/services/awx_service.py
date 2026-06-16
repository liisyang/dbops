from __future__ import annotations

import base64
import json
import logging
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import get_settings
from app.constants import AWX_TERMINAL_STATUSES


logger = logging.getLogger(__name__)


class AwxServiceError(RuntimeError):
    pass


class AwxService:
    @staticmethod
    def _build_url(path: str) -> str:
        settings = get_settings()
        if not settings.AWX_URL:
            raise AwxServiceError("AWX_URL 未配置")
        base_url = settings.AWX_URL.rstrip("/")
        return f"{base_url}{path}"

    @staticmethod
    def _request_json(method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        settings = get_settings()
        if not settings.AWX_USER:
            raise AwxServiceError("AWX_USER 未配置")
        if not settings.AWX_PASSWORD:
            raise AwxServiceError("AWX_PASSWORD 未配置")

        url = AwxService._build_url(path)
        raw_body = json.dumps(payload).encode("utf-8") if payload is not None else None

        credentials = f"{settings.AWX_USER}:{settings.AWX_PASSWORD}".encode("utf-8")
        auth = base64.b64encode(credentials).decode("utf-8")
        request = Request(url=url, method=method.upper(), data=raw_body)
        request.add_header("Authorization", f"Basic {auth}")
        request.add_header("Accept", "application/json")
        request.add_header("Content-Type", "application/json")

        try:
            with urlopen(request, timeout=settings.AWX_REQUEST_TIMEOUT) as response:
                content = response.read().decode("utf-8")
                if not content:
                    return {}
                return json.loads(content)
        except HTTPError as exc:
            # I6: cap error body length and log the raw body separately so
            # the exception message (which may land in DB error_message
            # columns) does not leak AWX internal paths / hostnames / creds.
            raw_body = exc.read().decode("utf-8", errors="ignore")[:500]
            logger.warning("AWX HTTP %s body=%s", exc.code, raw_body)
            raise AwxServiceError(f"AWX HTTP {exc.code}: upstream error") from exc
        except URLError as exc:
            raise AwxServiceError(f"AWX API 网络错误: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise AwxServiceError("AWX API 返回非 JSON 内容") from exc

    @staticmethod
    def _resolve_job_template(template_id: int, template_name: str) -> tuple[int, str]:
        if template_id > 0:
            return template_id, template_name

        encoded_name = quote(template_name, safe="")
        result = AwxService._request_json(
            "GET",
            f"/api/v2/job_templates/?name={encoded_name}",
        )
        items = result.get("results") or []
        if not items:
            raise AwxServiceError(f"未找到 AWX Job Template: {template_name}")
        first = items[0]
        resolved_id = int(first.get("id"))
        resolved_name = str(first.get("name") or template_name)
        return resolved_id, resolved_name

    @staticmethod
    def resolve_verify_job_template() -> tuple[int, str]:
        settings = get_settings()
        configured_id = int(settings.AWX_VERIFY_JOB_TEMPLATE_ID or 0)
        configured_name = settings.AWX_VERIFY_JOB_TEMPLATE_NAME or "JT_ASSET_VERIFY_PORT"
        return AwxService._resolve_job_template(configured_id, configured_name)

    @staticmethod
    def resolve_collector_job_template() -> tuple[int, str]:
        settings = get_settings()
        configured_id = int(settings.AWX_COLLECTOR_JOB_TEMPLATE_ID or 0)
        configured_name = settings.AWX_COLLECTOR_JOB_TEMPLATE_NAME or "JT_DBOPS_COLLECTOR_GENERIC"
        return AwxService._resolve_job_template(configured_id, configured_name)

    @staticmethod
    def launch_job(
        extra_vars: dict[str, Any],
        template_id: int | None = None,
        template_name: str | None = None,
        credentials: list[int] | None = None,
    ) -> dict[str, Any]:
        """Launch an AWX job template.

        Args:
            extra_vars: Job extra_vars payload.
            template_id: Optional job template ID.
            template_name: Optional job template name (resolved if ID not given).
            credentials: Optional list of AWX credential IDs to inject.
                         AWX injects these as env vars globally per job.
        """
        if template_id is None or template_name is None:
            resolved_template_id, resolved_template_name = AwxService.resolve_collector_job_template()
            template_id = resolved_template_id if template_id is None else template_id
            template_name = resolved_template_name if template_name is None else template_name

        body: dict[str, Any] = {"extra_vars": extra_vars}
        if credentials:
            body["credentials"] = credentials

        launch_result = AwxService._request_json(
            "POST",
            f"/api/v2/job_templates/{template_id}/launch/",
            body,
        )
        awx_job_id = launch_result.get("job")
        awx_job_url = None
        if awx_job_id:
            awx_job_url = f"{get_settings().AWX_URL.rstrip('/')}/#/jobs/playbook/{awx_job_id}"

        return {
            "awx_job_id": int(awx_job_id) if awx_job_id is not None else None,
            "awx_job_url": awx_job_url,
            "awx_job_template_id": template_id,
            "awx_job_template_name": template_name,
            "raw_response": launch_result,
        }

    @staticmethod
    def launch_verify_job(extra_vars: dict[str, Any]) -> dict[str, Any]:
        return AwxService.launch_job(extra_vars)

    # ------------------------------------------------------------------
    # P0-3: status / cancel helpers for timeout-recovery + batch-cancel.
    # ------------------------------------------------------------------

    @staticmethod
    def get_job_status(awx_job_id: int) -> dict[str, Any]:
        """Return a normalized snapshot of an AWX job.

        Response shape is the raw AWX `/api/v2/jobs/{id}/` payload plus a
        derived `is_terminal` boolean so callers don't need to mirror AWX
        status semantics.
        """
        if not awx_job_id:
            raise AwxServiceError("awx_job_id 不能为空")
        data = AwxService._request_json("GET", f"/api/v2/jobs/{int(awx_job_id)}/")
        status = (data.get("status") or "").lower()
        data["is_terminal"] = status in AWX_TERMINAL_STATUSES
        return data

    @staticmethod
    def cancel_job(awx_job_id: int) -> dict[str, Any]:
        """Request AWX to cancel a running job.

        AWX returns 405 if the job is already in a terminal state; that is
        surfaced as AwxServiceError so the caller can decide whether to
        treat it as success (idempotent cancel) or hard-fail.
        """
        if not awx_job_id:
            raise AwxServiceError("awx_job_id 不能为空")
        try:
            result = AwxService._request_json(
                "POST", f"/api/v2/jobs/{int(awx_job_id)}/cancel/"
            )
        except AwxServiceError as exc:
            logger.warning(
                "awx cancel_job failed: awx_job_id=%s error=%s", awx_job_id, exc
            )
            raise
        logger.info("awx cancel_job requested: awx_job_id=%s", awx_job_id)
        return result
