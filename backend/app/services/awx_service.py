from __future__ import annotations

import base64
import json
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import get_settings


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
            detail = exc.read().decode("utf-8", errors="ignore")
            raise AwxServiceError(f"AWX API 请求失败: {exc.code} {detail}") from exc
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
            extra_vars: Extra variables to pass to the job.
            template_id: AWX job template ID (resolved if not provided).
            template_name: AWX job template name (resolved if not provided).
            credentials: Optional list of AWX credential IDs to attach to the job.
                         These are AWX credential IDs only — NEVER passwords.
                         AWX injects the actual credentials as env vars at runtime.

        Phase 3.3A: credentials parameter enables passing DB/OS credentials
        to the AWX job without exposing usernames/passwords in DBOPS.
        """
        if template_id is None or template_name is None:
            resolved_template_id, resolved_template_name = AwxService.resolve_collector_job_template()
            template_id = resolved_template_id if template_id is None else template_id
            template_name = resolved_template_name if template_name is None else template_name

        body: dict[str, Any] = {"extra_vars": extra_vars}
        if credentials:
            body["credentials"] = credentials  # AWX API: array of credential IDs

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
