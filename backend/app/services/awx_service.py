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
    def resolve_verify_job_template() -> tuple[int, str]:
        settings = get_settings()
        configured_id = int(settings.AWX_VERIFY_JOB_TEMPLATE_ID or 0)
        configured_name = settings.AWX_VERIFY_JOB_TEMPLATE_NAME or "JT_ASSET_VERIFY_PORT"

        if configured_id > 0:
            return configured_id, configured_name

        encoded_name = quote(configured_name, safe="")
        result = AwxService._request_json(
            "GET",
            f"/api/v2/job_templates/?name={encoded_name}",
        )
        items = result.get("results") or []
        if not items:
            raise AwxServiceError(f"未找到 AWX Job Template: {configured_name}")
        first = items[0]
        template_id = int(first.get("id"))
        template_name = str(first.get("name") or configured_name)
        return template_id, template_name

    @staticmethod
    def launch_verify_job(extra_vars: dict[str, Any]) -> dict[str, Any]:
        template_id, template_name = AwxService.resolve_verify_job_template()
        launch_result = AwxService._request_json(
            "POST",
            f"/api/v2/job_templates/{template_id}/launch/",
            {"extra_vars": extra_vars},
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
