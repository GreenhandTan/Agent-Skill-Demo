from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskContext:
    task_id: str
    feishu_message_id: str | None = None
    search_keyword: str = "索尼耳机"
    rating_threshold: float = 0.99
    max_candidates: int = 5
    need_screenshot: bool = True
    manual_approval_required: bool = True
    report_channel: str = "feishu"
    session_state_path: str = ".cache/ui-automation-test/taobao-session.json"
    session_strategy: str = "storage_state"
    session_auto_save: bool = True
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StepRecord:
    name: str
    status: str
    message: str = ""
    artifact: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchedItem:
    title: str
    item_id: str | None = None
    price: str | None = None
    rating: float | None = None
    url: str | None = None
    cart_added: bool = False


@dataclass
class WorkflowResult:
    task_id: str
    status: str = "failed"
    login_status: str = "unknown"
    session_status: str = "unknown"
    search_status: str = "unknown"
    filter_status: str = "unknown"
    cart_status: str = "unknown"
    matched_items: list[MatchedItem] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)
    error: dict[str, Any] | None = None

    def add_step(self, name: str, status: str, message: str = "", artifact: str | None = None, **details: Any) -> None:
        self.steps.append(
            StepRecord(
                name=name,
                status=status,
                message=message,
                artifact=artifact,
                details=details,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "login_status": self.login_status,
            "session_status": self.session_status,
            "search_status": self.search_status,
            "filter_status": self.filter_status,
            "cart_status": self.cart_status,
            "matched_items": [
                {
                    "title": item.title,
                    "item_id": item.item_id,
                    "price": item.price,
                    "rating": item.rating,
                    "url": item.url,
                    "cart_added": item.cart_added,
                }
                for item in self.matched_items
            ],
            "evidence": self.evidence,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "message": step.message,
                    "artifact": step.artifact,
                    "details": step.details,
                }
                for step in self.steps
            ],
            "error": self.error,
        }