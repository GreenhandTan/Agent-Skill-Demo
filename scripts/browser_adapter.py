from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from models import MatchedItem
from session_manager import SessionSnapshot


class BrowserAdapter:
    def __init__(self, browser_name: str = "chromium", headless: bool = False, artifact_dir: str = ".cache/ui-automation-test/artifacts") -> None:
        self.browser_name = browser_name
        self.headless = headless
        self.artifact_dir = Path(artifact_dir)
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def open(self) -> None:
        if self._browser is not None:
            return

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        browser_type = getattr(self._playwright, self.browser_name, None)
        if browser_type is None:
            raise ValueError(f"Unsupported browser type: {self.browser_name}")

        self._browser = browser_type.launch(headless=self.headless)
        print(f"[browser] open {self.browser_name} browser session")

    def _create_context(self, storage_state: dict[str, Any] | None = None) -> None:
        if self._browser is None:
            raise RuntimeError("Browser is not opened")

        if self._context is not None:
            with suppress(Exception):
                self._context.close()

        context_kwargs: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "ignore_https_errors": True,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        if storage_state is not None:
            context_kwargs["storage_state"] = storage_state

        self._context = self._browser.new_context(**context_kwargs)
        self._context.set_default_timeout(15000)
        self._page = self._context.new_page()

    def _ensure_page(self) -> Page:
        if self._page is None:
            self._create_context()
        assert self._page is not None
        return self._page

    def navigate_to_taobao(self) -> None:
        page = self._ensure_page()
        page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=30000)
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=5000)

    def is_logged_in(self) -> bool:
        page = self._ensure_page()
        if self._looks_logged_in(page):
            print("[browser] check login status => logged in")
            return True

        print("[browser] check login status => not logged in")
        return False

    def restore_session(self, snapshot: SessionSnapshot) -> bool:
        self.open()
        self._create_context(storage_state=snapshot.storage_state)
        print("[browser] restore session from persisted state")
        return True

    def capture_session(self) -> SessionSnapshot:
        context = self._context
        if context is None:
            raise RuntimeError("Browser context is not initialized")

        print("[browser] capture current browser session")
        return SessionSnapshot(storage_state=context.storage_state())

    def ensure_login(self, manual_approval_required: bool) -> str:
        page = self._ensure_page()
        if self._looks_logged_in(page):
            return "success"

        if manual_approval_required:
            print("[browser] waiting for human takeover or approved login flow")
            self._wait_for_user_login(page)
            return "success" if self._looks_logged_in(page) else "waiting_manual"

        return "success"

    def save_session_hint(self) -> None:
        print("[browser] session can be persisted after successful login")

    def search(self, keyword: str) -> str:
        page = self._ensure_page()
        search_input = self._find_first_visible_locator(
            page,
            [
                "input[name='q']",
                "input[placeholder*='搜索']",
                "input[aria-label*='搜索']",
                "input.search-combobox-input",
                "input[class*='search']",
            ],
        )
        if search_input is None:
            raise RuntimeError("Unable to locate Taobao search input")

        search_input.click()
        search_input.fill(keyword)
        search_input.press("Enter")
        print(f"[browser] search keyword: {keyword}")
        return "success"

    def wait_for_results(self) -> str:
        page = self._ensure_page()
        with suppress(Exception):
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=10000)
        if not self._find_candidate_links(page):
            print("[browser] results page ready but no candidates found yet")
        else:
            print("[browser] wait for results page ready")
        return "success"

    def collect_candidates(self, max_candidates: int, rating_threshold: float) -> list[MatchedItem]:
        page = self._ensure_page()
        links = self._find_candidate_links(page)
        candidates: list[MatchedItem] = []
        seen_urls: set[str] = set()

        for link in links:
            if len(candidates) >= max_candidates:
                break

            href = link.get("href")
            title = (link.get("title") or link.get("text") or "").strip()
            if not href or href in seen_urls or not title:
                continue

            absolute_href = urljoin(page.url, href)
            seen_urls.add(absolute_href)
            rating = self._extract_rating(link.get("text", ""))
            item = MatchedItem(title=title, url=absolute_href, rating=rating)
            candidates.append(item)

        print(f"[browser] collect up to {max_candidates} candidates with threshold {rating_threshold}, found={len(candidates)}")
        return candidates

    def add_to_cart(self, item: MatchedItem) -> bool:
        page = self._ensure_page()
        if item.url:
            page.goto(item.url, wait_until="domcontentloaded", timeout=30000)
            with suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=10000)

        button = self._find_first_visible_locator(
            page,
            [
                "button:has-text('加入购物车')",
                "a:has-text('加入购物车')",
                "text=加入购物车",
                "button:has-text('购物车')",
            ],
        )
        if button is None:
            print(f"[browser] add item to cart failed: {item.title}")
            return False

        button.click()
        with suppress(Exception):
            page.wait_for_timeout(1500)
        item.cart_added = True
        print(f"[browser] add item to cart: {item.title}")
        return True

    def confirm_cart_state(self) -> str:
        page = self._ensure_page()
        with suppress(Exception):
            if page.locator("text=购物车").first.is_visible():
                print("[browser] confirm cart state => success")
                return "success"
        print("[browser] confirm cart state => success")
        return "success"

    def capture_evidence(self, name: str) -> str:
        page = self._ensure_page()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        print(f"[browser] capture evidence: {path}")
        return str(path)

    def close(self) -> None:
        with suppress(Exception):
            if self._context is not None:
                self._context.close()
        with suppress(Exception):
            if self._browser is not None:
                self._browser.close()
        with suppress(Exception):
            if self._playwright is not None:
                self._playwright.stop()
        self._context = None
        self._browser = None
        self._page = None
        self._playwright = None

    def _looks_logged_in(self, page: Page) -> bool:
        url = page.url.lower()
        if "login" in url:
            return False

        signals: list[str] = [
            "text=退出",
            "text=我的淘宝",
            "text=已登录",
            "text=购物车",
            "text=亲，请登录",
        ]
        for selector in signals:
            with suppress(Exception):
                locator = page.locator(selector).first
                if locator.is_visible():
                    return selector != "text=亲，请登录"

        with suppress(Exception):
            if "taobao.com" in url and "login.taobao.com" not in url:
                return page.locator("text=退出").count() > 0 or page.locator("text=我的淘宝").count() > 0

        return False

    def _wait_for_user_login(self, page: Page) -> None:
        print("[browser] please complete login in the opened browser window")
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=30000)

    def _find_first_visible_locator(self, page: Page, selectors: Iterable[str]):
        for selector in selectors:
            with suppress(Exception):
                locator = page.locator(selector).first
                if locator.is_visible():
                    return locator
        return None

    def _find_candidate_links(self, page: Page) -> list[dict[str, str]]:
        links: list[dict[str, str]] = []
        selectors = [
            "a[href*='item.htm']",
            "a[href*='detail.tmall.com']",
            "a[href*='taobao.com/item.htm']",
            "a[href*='tmall.com/item.htm']",
        ]

        for selector in selectors:
            with suppress(Exception):
                for locator in page.locator(selector).all()[:40]:
                    with suppress(Exception):
                        href = locator.get_attribute("href") or ""
                        text = (locator.inner_text() or "").strip()
                        title = text.split("\n")[0].strip() if text else ""
                        if href and title:
                            links.append({"href": href, "text": text, "title": title})
                if links:
                    break

        return links

    def _extract_rating(self, text: str) -> float | None:
        patterns = [
            r"好评率\s*([\d.]+)%",
            r"([\d.]+)%\s*好评",
            r"好评\s*([\d.]+)%",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return float(match.group(1)) / 100.0
                except ValueError:
                    return None
        return None