from __future__ import annotations

from typing import Any

from browser_adapter import BrowserAdapter
from config import OpenClawSkillConfig
from feishu_client import FeishuClient
from models import TaskContext, WorkflowResult
from session_flow import SessionFlow
from session_manager import SessionManager


class UiAutomationWorkflow:
    def __init__(self, feishu_client: FeishuClient, browser: BrowserAdapter) -> None:
        self.feishu_client = feishu_client
        self.browser = browser

    def build_context(self, payload: dict[str, Any]) -> TaskContext:
        config = OpenClawSkillConfig.from_payload(payload)
        return TaskContext(
            task_id=str(config.task_id or config.feishu_message_id or "unknown-task"),
            feishu_message_id=config.feishu_message_id,
            search_keyword=config.search_keyword,
            rating_threshold=config.rating_threshold,
            max_candidates=config.max_candidates,
            need_screenshot=config.need_screenshot,
            manual_approval_required=config.manual_approval_required,
            report_channel=config.report_channel,
            session_state_path=config.session_state_path,
            session_strategy=config.session_strategy,
            session_auto_save=config.session_auto_save,
            raw_payload=payload,
        )

    def run(self, payload: dict[str, Any]) -> WorkflowResult:
        context = self.build_context(payload)
        result = WorkflowResult(task_id=context.task_id)
        session_manager = SessionManager(context.session_state_path)
        session_flow = SessionFlow(self.browser, session_manager)

        try:
            result.add_step("task_received", "success", task_id=context.task_id, report_channel=context.report_channel)
            self.browser.open()
            result.add_step("browser_opened", "success", browser=getattr(self.browser, "browser_name", "controlled"))

            restored = False
            if context.session_strategy in {"storage_state", "cookie_localstorage"}:
                restored = session_flow.try_restore()
                result.session_status = "restored" if restored else "missing"
                result.add_step("session_restore", "success" if restored else "skipped", strategy=context.session_strategy, restored=restored)

            self.browser.navigate_to_taobao()
            result.add_step("taobao_opened", "success", url="https://www.taobao.com")

            logged_in = self.browser.is_logged_in() if not restored else True
            if logged_in:
                result.login_status = "success"
                result.add_step("login_check", "success", message="session already logged in or restored")
            else:
                result.login_status = self.browser.ensure_login(context.manual_approval_required)
                result.add_step("login_flow", result.login_status, message="login flow executed")
                if result.login_status != "success":
                    result.status = "partial_success"
                    result.error = {
                        "code": "LOGIN_REQUIRED",
                        "message": "Manual takeover is required before continuing.",
                        "step": "login",
                    }
                    result.add_step("workflow_stopped", "blocked", message="waiting for manual takeover")
                    return result

                if context.session_auto_save:
                    session_flow.capture_after_login()
                    result.session_status = "captured"
                    result.add_step("session_capture", "success", message="session persisted after login")

            result.search_status = self.browser.search(context.search_keyword)
            result.add_step("search_submitted", result.search_status, keyword=context.search_keyword)
            result.search_status = self.browser.wait_for_results()
            result.add_step("search_results_ready", result.search_status)
            result.evidence.append(self.browser.capture_evidence("search_results"))

            candidates = self.browser.collect_candidates(context.max_candidates, context.rating_threshold)
            result.filter_status = "success"
            result.add_step("candidates_collected", "success", candidate_count=len(candidates))

            for item in candidates:
                if item.rating is None or item.rating < context.rating_threshold:
                    result.add_step("candidate_skipped", "skipped", message=item.title, rating=item.rating or -1)
                    continue
                if self.browser.add_to_cart(item):
                    result.matched_items.append(item)
                    result.add_step("item_added", "success", message=item.title, item_id=item.item_id or "")

            result.cart_status = self.browser.confirm_cart_state()
            result.add_step("cart_confirmed", result.cart_status, item_count=len(result.matched_items))
            result.evidence.append(self.browser.capture_evidence("cart_result"))
            result.status = "success" if result.matched_items else "partial_success"
            result.add_step("workflow_completed", result.status, matched_count=len(result.matched_items))
            return result

        except Exception as exc:
            result.status = "failed"
            result.error = {
                "code": "WORKFLOW_ERROR",
                "message": str(exc),
                "step": "workflow",
            }
            result.add_step("workflow_failed", "failed", message=str(exc))
            return result
        finally:
            self.browser.close()

    def report(self, payload: dict[str, Any], result: WorkflowResult) -> None:
        report_to = payload.get("report_to")
        self.feishu_client.send_report(report_to, result.to_dict())