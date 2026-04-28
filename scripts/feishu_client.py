from __future__ import annotations

from typing import Any


class FeishuClient:
    def __init__(self, app_id: str | None = None, app_secret: str | None = None) -> None:
        self.app_id = app_id
        self.app_secret = app_secret

    def parse_task_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    def resolve_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload:
            return payload
        message_id = self.fetch_task_message_id(payload)
        return self.fetch_task_message(message_id)

    def send_report(self, report_to: dict[str, Any] | None, result: dict[str, Any]) -> None:
        if report_to is None:
            return
        print("[feishu] report target:", report_to)
        print("[feishu] report payload:", result)

    def fetch_task_message_id(self, payload: dict[str, Any]) -> str:
        message_id = payload.get("feishu_message_id")
        if not message_id:
            raise ValueError("feishu_message_id is required when fetching task message")
        return str(message_id)

    def fetch_task_message(self, message_id: str) -> dict[str, Any]:
        return {
            "feishu_message_id": message_id,
            "task_id": message_id,
            "search_keyword": "索尼耳机",
            "rating_threshold": 0.99,
            "max_candidates": 5,
            "need_screenshot": True,
            "manual_approval_required": True,
        }