from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FeishuTaskEnvelope:
    task_id: str | None = None
    feishu_message_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FeishuReportEnvelope:
    task_id: str
    report_to: dict[str, Any] | None
    result: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class FeishuClient:
    """OpenClaw-facing Feishu protocol adapter.

    The OpenClaw transport/plugin layer is responsible for receiving Feishu
    messages and delivering replies. This adapter only normalizes payloads and
    shapes the outbound report envelope used by the workflow.
    """

    def parse_task_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.normalize_task_payload(payload)

    def resolve_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.normalize_task_payload(payload)

    def build_task_envelope(self, payload: dict[str, Any]) -> FeishuTaskEnvelope:
        normalized = self.normalize_task_payload(payload)
        return FeishuTaskEnvelope(
            task_id=self._string_or_none(normalized.get("task_id")),
            feishu_message_id=self._string_or_none(normalized.get("feishu_message_id")),
            payload=normalized,
            metadata=self._extract_metadata(normalized),
        )

    def build_report_envelope(self, report_to: dict[str, Any] | None, result: dict[str, Any]) -> FeishuReportEnvelope:
        task_id = self._string_or_none(result.get("task_id")) or self._string_or_none((report_to or {}).get("task_id"))
        if not task_id:
            task_id = "unknown-task"

        return FeishuReportEnvelope(
            task_id=task_id,
            report_to=report_to,
            result=result,
            metadata={
                "channel": "feishu",
                "transport": "openclaw-plugin",
            },
        )

    def send_report(self, report_to: dict[str, Any] | None, result: dict[str, Any]) -> dict[str, Any]:
        envelope = self.build_report_envelope(report_to, result)
        return {
            "task_id": envelope.task_id,
            "report_to": envelope.report_to,
            "result": envelope.result,
            "metadata": envelope.metadata,
        }

    def normalize_task_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if payload is None:
            return {}

        normalized = dict(payload)

        if isinstance(normalized.get("payload"), dict):
            nested_payload = normalized.pop("payload")
            normalized = {**nested_payload, **normalized}

        if isinstance(normalized.get("message"), dict):
            nested_message = normalized.pop("message")
            normalized = {**nested_message, **normalized}

        if isinstance(normalized.get("data"), dict):
            nested_data = normalized.pop("data")
            normalized = {**nested_data, **normalized}

        return normalized

    def _extract_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for key in ("source", "chat_id", "message_id", "thread_id", "sender", "report_channel"):
            value = payload.get(key)
            if value is not None:
                metadata[key] = value
        return metadata

    def _string_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None