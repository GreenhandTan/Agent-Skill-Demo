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
            price_min=config.price_min,
            price_max=config.price_max,
            min_sales=config.min_sales,
            require_free_shipping=config.require_free_shipping,
            require_tmall=config.require_tmall,
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

            # Always verify login state — session restore does NOT guarantee login
            logged_in = self.browser.is_logged_in()
            if not logged_in:
                result.login_status = "waiting_manual"
                result.add_step(
                    "login_check",
                    "blocked",
                    message="淘宝未登录，请在弹出的浏览器窗口中手动完成登录",
                )

                if not context.manual_approval_required:
                    result.status = "partial_success"
                    result.error = {
                        "code": "LOGIN_REQUIRED",
                        "message": "淘宝未登录，需要先手动完成登录并保存会话。",
                        "step": "login",
                    }
                    result.add_step("workflow_stopped", "blocked", message="waiting for manual login and session capture")
                    return result

                # Block and wait for user to complete manual login
                self.browser.ensure_login(manual_approval_required=True, force_manual=True)
                logged_in = self.browser.is_logged_in()
                if not logged_in:
                    result.status = "partial_success"
                    result.error = {
                        "code": "LOGIN_REQUIRED",
                        "message": "登录超时或失败，请重试。",
                        "step": "login",
                    }
                    result.add_step("workflow_stopped", "blocked", message="login timeout or failed")
                    return result

                result.login_status = "success"
                result.add_step("login_flow", "success", message="manual login completed")
                if context.session_auto_save:
                    session_flow.capture_after_login()
                    result.session_status = "captured"
                    result.add_step("session_capture", "success", message="session persisted after login")
            else:
                result.login_status = "success"
                result.add_step("login_check", "success", message="登录状态已确认")
                if context.session_auto_save and context.session_strategy in {"storage_state", "cookie_localstorage"}:
                    session_flow.capture_after_login()
                    result.session_status = "captured"
                    result.add_step("session_capture", "success", message="session persisted from active login state")

            result.search_status = self.browser.search(context.search_keyword)
            result.add_step("search_submitted", result.search_status, keyword=context.search_keyword)
            result.search_status = self.browser.wait_for_results()
            result.add_step("search_results_ready", result.search_status)

            if not self.browser.ensure_search_access(context.manual_approval_required):
                result.status = "partial_success"
                result.error = {
                    "code": "SEARCH_BLOCKED",
                    "message": "Taobao risk control is blocking search results. Complete manual verification and retry.",
                    "step": "search",
                }
                result.add_step("search_blocked", "blocked", message="waiting for manual verification")
                return result

            result.evidence.append(self.browser.capture_evidence("search_results"))

            candidates = self.browser.collect_candidates(
                context.search_keyword, context.max_candidates, context.rating_threshold,
                price_min=context.price_min, price_max=context.price_max,
                min_sales=context.min_sales, require_free_shipping=context.require_free_shipping,
                require_tmall=context.require_tmall,
            )
            result.filter_status = "success"
            result.add_step("candidates_collected", "success", candidate_count=len(candidates))

            for item in candidates:
                # Visit product detail page to extract rating (search results don't show it)
                self.browser.enrich_item_rating(item)

                if item.rating is not None and item.rating <= context.rating_threshold:
                    result.add_step("candidate_skipped", "skipped",
                                    message=item.title, rating=item.rating)
                    continue
                if item.rating is None:
                    result.add_step("candidate_skipped", "skipped",
                                    message=f"{item.title} (好评率未知)", rating=-1)
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

    def report(self, payload: dict[str, Any], result: WorkflowResult) -> dict[str, Any]:
        report_to = payload.get("report_to")
        return self.feishu_client.send_report(report_to, result.to_dict())