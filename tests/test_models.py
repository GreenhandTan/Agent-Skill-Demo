from __future__ import annotations

from scripts.models import MatchedItem, StepRecord, WorkflowResult


class TestStepRecord:
    def test_create(self):
        step = StepRecord(name="search", status="success", message="done", artifact="/tmp/img.png", details={"keyword": "test"})
        assert step.name == "search"
        assert step.status == "success"
        assert step.message == "done"
        assert step.artifact == "/tmp/img.png"
        assert step.details == {"keyword": "test"}

    def test_defaults(self):
        step = StepRecord(name="step1", status="pending")
        assert step.message == ""
        assert step.artifact is None
        assert step.details == {}


class TestWorkflowResult:
    def test_initial_status(self):
        result = WorkflowResult(task_id="task-1")
        assert result.task_id == "task-1"
        assert result.status == "failed"
        assert result.matched_items == []
        assert result.evidence == []
        assert result.steps == []
        assert result.error is None

    def test_add_step(self):
        result = WorkflowResult(task_id="task-1")
        result.add_step("login_check", "success", message="已登录")
        assert len(result.steps) == 1
        assert result.steps[0].name == "login_check"
        assert result.steps[0].status == "success"
        assert result.steps[0].message == "已登录"

    def test_add_step_with_details(self):
        result = WorkflowResult(task_id="task-1")
        result.add_step("search", "success", keyword="test", candidates=5)
        assert result.steps[0].details == {"keyword": "test", "candidates": 5}

    def test_to_dict_basic(self):
        result = WorkflowResult(task_id="task-1", status="success")
        d = result.to_dict()
        assert d["task_id"] == "task-1"
        assert d["status"] == "success"
        assert d["matched_items"] == []
        assert d["evidence"] == []
        assert d["steps"] == []

    def test_to_dict_with_items(self):
        result = WorkflowResult(task_id="task-1", status="success")
        item = MatchedItem(
            title="Test Item", item_id="123", price="¥99.00", price_value=99.0,
            sales_count=500, rating=0.95, free_shipping=True, is_tmall=True,
            url="https://example.com/item/123", cart_added=True,
        )
        result.matched_items.append(item)
        d = result.to_dict()
        assert len(d["matched_items"]) == 1
        mi = d["matched_items"][0]
        assert mi["title"] == "Test Item"
        assert mi["item_id"] == "123"
        assert mi["price"] == "¥99.00"
        assert mi["price_value"] == 99.0
        assert mi["sales_count"] == 500
        assert mi["rating"] == 0.95
        assert mi["free_shipping"] is True
        assert mi["is_tmall"] is True
        assert mi["url"] == "https://example.com/item/123"
        assert mi["cart_added"] is True

    def test_to_dict_with_error(self):
        result = WorkflowResult(task_id="task-1", status="failed")
        result.error = {"code": "LOGIN_REQUIRED", "message": "请登录"}
        d = result.to_dict()
        assert d["error"] == {"code": "LOGIN_REQUIRED", "message": "请登录"}

    def test_to_dict_with_steps(self):
        result = WorkflowResult(task_id="task-1")
        result.add_step("a", "success", message="ok")
        result.add_step("b", "failed", message="err", artifact="/tmp/x.png")
        d = result.to_dict()
        assert len(d["steps"]) == 2
        assert d["steps"][0] == {"name": "a", "status": "success", "message": "ok", "artifact": None, "details": {}}
        assert d["steps"][1]["artifact"] == "/tmp/x.png"


class TestMatchedItem:
    def test_defaults(self):
        item = MatchedItem(title="Test")
        assert item.title == "Test"
        assert item.item_id is None
        assert item.price is None
        assert item.price_value is None
        assert item.sales_count is None
        assert item.rating is None
        assert item.free_shipping is False
        assert item.is_tmall is False
        assert item.url is None
        assert item.cart_added is False
