from __future__ import annotations

import argparse
import json
from pathlib import Path

from browser_adapter import BrowserAdapter
from config import OpenClawSkillConfig
from feishu_client import FeishuClient
from workflow import UiAutomationWorkflow


def load_payload(path: str) -> dict:
    payload_path = Path(path)
    with payload_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the OpenClaw-compatible UI automation skill")
    parser.add_argument("--task-file", help="Path to the Feishu task JSON file")
    parser.add_argument("--task-id", help="Task id when no task file is provided")
    parser.add_argument("--feishu-message-id", help="Feishu message id when resolving the task remotely")
    parser.add_argument("--search-keyword", default="索尼耳机", help="Keyword to search on Taobao")
    parser.add_argument("--rating-threshold", type=float, default=0.99, help="Minimum rating threshold")
    parser.add_argument("--max-candidates", type=int, default=5, help="Maximum candidates to inspect")
    parser.add_argument("--no-screenshot", action="store_true", help="Disable evidence screenshots")
    parser.add_argument("--no-manual-approval", action="store_true", help="Disable manual takeover pause")
    parser.add_argument("--session-state-path", default=".cache/ui-automation-test/taobao-session.json", help="Path to persisted session state")
    parser.add_argument("--session-strategy", default="storage_state", choices=["storage_state", "cookie_localstorage", "none"], help="Session restore strategy")
    parser.add_argument("--no-session-auto-save", action="store_true", help="Disable automatic session persistence after manual login")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    payload: dict
    if args.task_file:
        payload = load_payload(args.task_file)
    else:
        payload = {
            "task_id": args.task_id,
            "feishu_message_id": args.feishu_message_id,
            "search_keyword": args.search_keyword,
            "rating_threshold": args.rating_threshold,
            "max_candidates": args.max_candidates,
            "need_screenshot": not args.no_screenshot,
            "manual_approval_required": not args.no_manual_approval,
            "report_channel": "feishu",
            "session_state_path": args.session_state_path,
            "session_strategy": args.session_strategy,
            "session_auto_save": not args.no_session_auto_save,
            "constraints": {
                "browser": "chromium",
                "headless": args.headless,
            },
        }

    config = OpenClawSkillConfig.from_payload(payload)
    feishu_client = FeishuClient()
    browser = BrowserAdapter(browser_name=config.browser_name, headless=bool(payload.get("constraints", {}).get("headless", False)))
    workflow = UiAutomationWorkflow(feishu_client, browser)

    result = workflow.run(payload)
    workflow.report(payload, result)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status in {"success", "partial_success"} else 2


if __name__ == "__main__":
    raise SystemExit(main())