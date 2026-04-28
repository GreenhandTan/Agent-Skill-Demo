from __future__ import annotations

import math
import random
import re
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, urljoin, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright
from playwright_stealth import Stealth

from models import MatchedItem
from session_manager import SessionSnapshot
from slider_solver import SliderSolver

_SCRIPTS_DIR = Path(__file__).parent.resolve()


class BrowserAdapter:
    def __init__(self, browser_name: str = "chromium", headless: bool = False, artifact_dir: str = ".cache/ui-automation-test/artifacts") -> None:
        self.browser_name = browser_name
        self.headless = headless
        artifact_path = Path(artifact_dir)
        if not artifact_path.is_absolute():
            artifact_path = _SCRIPTS_DIR / artifact_path
        self.artifact_dir = artifact_path
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._slider_solver = SliderSolver(method="ddddocr")

    # ──────────────────────────────────────────────
    # Browser Lifecycle
    # ──────────────────────────────────────────────

    def open(self) -> None:
        if self._browser is not None:
            return

        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        # Wrap Playwright with stealth — injects 20 anti-detection evasion patches
        self._playwright = Stealth(
            navigator_languages_override=("zh-CN", "zh"),
            navigator_platform_override="Win32",
            navigator_vendor_override="Google Inc.",
            webgl_vendor_override="Intel Inc.",
            webgl_renderer_override="Intel Iris OpenGL Engine",
        ).use_sync(sync_playwright()).start()

        browser_type = getattr(self._playwright, self.browser_name, None)
        if browser_type is None:
            raise ValueError(f"Unsupported browser type: {self.browser_name}")

        # Anti-detection launch args
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--window-size=1920,1080",
        ]

        launch_errors: list[str] = []
        launch_attempts: list[dict[str, Any]] = [
            {"headless": self.headless, "args": launch_args},
            {"headless": self.headless, "channel": "msedge", "args": launch_args},
            {"headless": self.headless, "channel": "chrome", "args": launch_args},
        ]

        for launch_kwargs in launch_attempts:
            try:
                self._browser = browser_type.launch(**launch_kwargs)
                print(f"[browser] open {self.browser_name} browser session with stealth")
                return
            except Exception as exc:
                launch_errors.append(f"{launch_kwargs}: {exc}")

        raise RuntimeError("Unable to launch a browser backend. Attempts: " + " | ".join(launch_errors))

    def _create_context(self, storage_state: dict[str, Any] | None = None) -> None:
        if self._browser is None:
            raise RuntimeError("Browser is not opened")

        if self._context is not None:
            with suppress(Exception):
                self._context.close()

        # Randomize viewport slightly to avoid fingerprint consistency
        w = random.randint(1900, 1940)
        h = random.randint(1060, 1100)

        # Use realistic, recent Chrome user agent
        chrome_ver = random.choice(["131.0.0.0", "130.0.0.0", "129.0.0.0", "128.0.0.0"])

        context_kwargs: dict[str, Any] = {
            "viewport": {"width": w, "height": h},
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "ignore_https_errors": True,
            "user_agent": (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"
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

    # ──────────────────────────────────────────────
    # Session Management
    # ──────────────────────────────────────────────

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

    # ──────────────────────────────────────────────
    # Login
    # ──────────────────────────────────────────────

    def navigate_to_taobao(self) -> None:
        page = self._ensure_page()
        page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=30000)
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=5000)
        # Auto-solve CAPTCHA if triggered on navigation
        self._handle_captcha_if_present(page)

    def is_logged_in(self) -> bool:
        page = self._ensure_page()
        if self._looks_logged_in(page):
            print("[browser] check login status => logged in")
            return True
        print("[browser] check login status => not logged in")
        return False

    def ensure_login(self, manual_approval_required: bool, force_manual: bool = False) -> str:
        page = self._ensure_page()
        if not force_manual and self._looks_logged_in(page):
            return "success"
        if manual_approval_required:
            print("[browser] waiting for human takeover or approved login flow")
            self._wait_for_user_login(page)
            return "success" if self._looks_logged_in(page) else "waiting_manual"
        return "success"

    def _looks_logged_in(self, page: Page) -> bool:
        url = page.url.lower()
        if "login" in url:
            return False
        with suppress(Exception):
            if page.locator("text=亲，请登录").first.is_visible():
                return False
        for selector in ["text=退出", "text=我的淘宝", "text=已登录"]:
            with suppress(Exception):
                if page.locator(selector).first.is_visible():
                    return True
        return False

    def _wait_for_user_login(self, page: Page) -> None:
        print("[browser] ============================================")
        print("[browser] 请在弹出的浏览器窗口中手动完成淘宝登录")
        print("[browser] 登录完成后脚本会自动检测并继续")
        print("[browser] ============================================")

        with suppress(Exception):
            login_link = page.locator("text=亲，请登录").first
            if login_link.is_visible():
                self._human_click(page, login_link)
                page.wait_for_timeout(2000)

        for i in range(100):
            time.sleep(3)
            try:
                page.reload(wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(2000)
            except Exception:
                pass
            if self._looks_logged_in(page):
                print(f"[browser] 登录成功! (等待约 {(i+1)*3}s)")
                return
            if (i + 1) % 10 == 0:
                print(f"[browser] 等待登录中... ({(i+1)*3}s/300s)")

        print("[browser] 登录超时，请重试")

    # ──────────────────────────────────────────────
    # Search
    # ──────────────────────────────────────────────

    def search(self, keyword: str) -> str:
        page = self._ensure_page()

        # Step 1: Ensure we are on the taobao homepage
        if "taobao.com" not in page.url or "s.taobao.com" in page.url:
            print("[browser] navigating to taobao homepage before search")
            page.goto("https://www.taobao.com", wait_until="domcontentloaded", timeout=30000)
            self._human_wait(2, 4)

        # Step 2: Dismiss any popups/overlays
        for _ in range(3):
            dismissed = False
            for sel in [
                "button:has-text('关闭')",
                "button:has-text('我知道了')",
                "text=关闭",
                "text=我知道了",
            ]:
                with suppress(Exception):
                    btn = self._find_first_visible_locator(page, [sel])
                    if btn is not None:
                        self._human_click(page, btn)
                        self._human_wait(0.3, 0.8)
                        dismissed = True
            if not dismissed:
                break

        # Step 3: Hide overlay divs that intercept clicks
        with suppress(Exception):
            page.evaluate("""() => {
                document.querySelectorAll('.J_MIDDLEWARE_FRAME_WIDGET, [class*="middleware"], [class*="overlay"]').forEach(el => {
                    el.style.display = 'none';
                });
            }""")

        self._human_wait(0.5, 1.5)
        self._random_mouse_move(page)

        # Step 4: Locate search input and interact human-like
        search_input = self._find_first_visible_locator(
            page,
            [
                "#q",
                "input[name='q']",
                "input[placeholder*='搜索']",
                "input[aria-label*='搜索']",
                "input.search-combobox-input",
                "input[class*='search']",
            ],
        )
        if search_input is None:
            raise RuntimeError("Unable to locate Taobao search input")

        # Human-like: move mouse to input, click, then type
        self._human_click(page, search_input)
        self._human_wait(0.3, 0.8)

        # Clear existing text
        with suppress(Exception):
            page.keyboard.press("Control+a")
            self._human_wait(0.1, 0.3)

        # Type keyword with human-like delays
        self._human_type(page, keyword)
        self._human_wait(0.5, 1.5)

        print(f"[browser] search keyword: {keyword}")

        if random.random() < 0.5:
            self._random_mouse_move(page)

        # Dismiss search suggestion dropdown that may intercept Enter
        with suppress(Exception):
            page.keyboard.press("Escape")
            self._human_wait(0.3, 0.6)

        # Step 5: Re-focus input then submit
        with suppress(Exception):
            search_input.focus()
            self._human_wait(0.1, 0.3)

        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                page.keyboard.press("Enter")
        except Exception:
            pass

        # If Enter didn't navigate, try programmatic form submit
        if "s.taobao.com/search" not in page.url:
            print("[browser] Enter key did not navigate, trying form submit")
            with suppress(Exception):
                page.evaluate("""() => {
                    const form = document.querySelector('#J_TSearchForm')
                        || document.querySelector('form[action*="search"]')
                        || document.querySelector('form[class*="search"]');
                    if (form) { form.submit(); return true; }
                    return false;
                }""")
            try:
                page.wait_for_url("**/search**", timeout=10000)
            except Exception:
                pass

        # If form submit didn't work, try clicking search button
        if "s.taobao.com/search" not in page.url:
            print("[browser] form submit did not navigate, trying search button")
            for btn_sel in ["button[type='submit']", "#J_TSearchForm button", "button:has-text('搜索')", ".btn-search"]:
                with suppress(Exception):
                    btn = self._find_first_visible_locator(page, [btn_sel])
                    if btn is not None:
                        self._human_click(page, btn)
                        self._human_wait(1, 2)
                        break
            try:
                page.wait_for_url("**/search**", timeout=10000)
            except Exception:
                pass

        # Last resort: direct URL navigation
        if "s.taobao.com/search" not in page.url:
            print("[browser] all interactive methods failed, using direct URL")
            search_url = f"https://s.taobao.com/search?q={quote(keyword)}"
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Auto-solve CAPTCHA if triggered by search navigation
        self._handle_captcha_if_present(page)

        # Step 6: Wait for results to load
        with suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=10000)
        self._human_wait(2, 4)

        # Human-like scroll to trigger lazy loading
        self._human_scroll(page, target_y=random.randint(800, 1200))

        print(f"[browser] current url: {page.url}")
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

    def ensure_search_access(self, manual_approval_required: bool) -> bool:
        page = self._ensure_page()
        if not self._looks_access_blocked(page):
            return True
        print("[browser] access blocked by Taobao risk control")

        # Try auto-solving CAPTCHA first
        if self._handle_captcha_if_present(page):
            print("[browser] CAPTCHA auto-solved, access restored")
            return True

        if not manual_approval_required:
            return False
        print("[browser] waiting for user to pass manual verification")
        self._wait_for_access_recovery(page)
        return not self._looks_access_blocked(page)

    # ──────────────────────────────────────────────
    # Candidate Collection & Cart
    # ──────────────────────────────────────────────

    def collect_candidates(self, keyword: str, max_candidates: int, rating_threshold: float) -> list[MatchedItem]:
        page = self._ensure_page()
        links = self._find_candidate_links(page)
        candidates: list[MatchedItem] = []
        seen_urls: set[str] = set()
        keyword_tokens = self._build_keyword_tokens(keyword)

        if not links:
            anchor_count = page.locator("a").count()
            item_count = page.locator("a[href*='item.htm']").count()
            tmall_count = page.locator("a[href*='detail.tmall.com']").count()
            print(f"[browser] candidate diagnostics => url={page.url}, anchors={anchor_count}, item_links={item_count}, tmall_links={tmall_count}")
            with suppress(Exception):
                samples = page.evaluate(
                    """() => Array.from(document.querySelectorAll('a'))
                        .slice(0, 12)
                        .map((a) => ({ href: a.getAttribute('href') || '', text: (a.textContent || '').trim().slice(0, 40) }))"""
                )
                print(f"[browser] anchor samples => {samples}")

        for link in links:
            if len(candidates) >= max_candidates:
                break
            href = link.get("href")
            title = (link.get("title") or link.get("text") or "").strip()
            if not href or href in seen_urls or not title:
                continue
            text = link.get("text", "")
            if keyword_tokens and not self._matches_keyword(title, text, keyword_tokens):
                continue
            absolute_href = urljoin(page.url, href)
            seen_urls.add(absolute_href)
            rating = self._extract_rating(text)
            item = MatchedItem(title=title, url=absolute_href, rating=rating)
            candidates.append(item)
            if len(candidates) % 3 == 0:
                self._human_wait(0.3, 1)

        print(f"[browser] collect up to {max_candidates} candidates with threshold {rating_threshold}, found={len(candidates)}")
        return candidates

    def enrich_item_rating(self, item: MatchedItem) -> float | None:
        page = self._ensure_page()
        if not item.url:
            return None
        try:
            self._human_wait(2, 4)
            self._random_mouse_move(page)
            self._human_wait(0.3, 0.8)

            page.goto(item.url, wait_until="domcontentloaded", timeout=20000)
            with suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=8000)
            self._handle_captcha_if_present(page)

            self._simulate_browsing(page, max_scroll=1500)

            # Extract item_id from URL query param
            if not item.item_id:
                parsed = urlparse(item.url)
                params = parse_qs(parsed.query)
                id_vals = params.get("id", [])
                if id_vals:
                    item.item_id = id_vals[0]

            # Extract price from detail page
            if not item.price:
                price_text = page.evaluate("""() => {
                    const selectors = [
                        '#J_StrPr498', '.tm-price', '.tb-rmb-num',
                        '[class*="price"]:not([class*="price-"])',
                        '.tm-promo-price .tm-price', '.tb-item-price',
                        '.sku-price .price-value', '.J_original_price',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.textContent.trim()) {
                            return el.textContent.trim();
                        }
                    }
                    return null;
                }""")
                if price_text:
                    match = re.search(r'([\d,]+(?:\.\d{2})?)', price_text.replace(',', ''))
                    if match:
                        val = match.group(1)
                        try:
                            f = float(val)
                            if f >= 0.01:
                                item.price = f"{f:.2f}"
                        except ValueError:
                            pass

            text = page.evaluate("""() => {
                const body = document.body.innerText;
                const ratingEls = document.querySelectorAll(
                    '[class*="rate"], [class*="Rating"], [class*="rating"], '
                    + '[class*="score"], [class*="positive"], [class*="好评"], '
                    + '.dsr-item, .tm-ind-item, .tb-seller-rate, #dsr-info, '
                    + '[class*="seller"], [class*="star"], .tb-rate, .tm-rate, '
                    + '.J_TitleRate, .tm-ind-title'
                );
                let extra = '';
                ratingEls.forEach(el => { extra += ' ' + el.textContent; });
                return body + extra;
            }""")

            rating = self._extract_rating(text)
            if rating is not None:
                item.rating = rating
                print(f"[browser] enriched rating for [{item.title[:30]}]: {rating*100:.0f}%")
            else:
                print(f"[browser] no rating found for [{item.title[:30]}]")
            return rating
        except Exception as e:
            print(f"[browser] enrich rating failed for [{item.title[:30]}]: {e}")
            return None

    def add_to_cart(self, item: MatchedItem) -> bool:
        page = self._ensure_page()
        if item.url:
            self._human_wait(2, 5)
            self._random_mouse_move(page)
            self._human_wait(0.3, 0.8)

            page.goto(item.url, wait_until="domcontentloaded", timeout=30000)
            with suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=10000)
            self._handle_captcha_if_present(page)

            self._simulate_browsing(page, max_scroll=1000)

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

        self._human_click(page, button)
        self._human_wait(1, 2.5)
        item.cart_added = True
        print(f"[browser] add item to cart: {item.title}")
        return True

    def confirm_cart_state(self) -> str:
        page = self._ensure_page()
        try:
            page.goto("https://cart.taobao.com/cart.htm", wait_until="domcontentloaded", timeout=20000)
            with suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=10000)
            self._handle_captcha_if_present(page)
            self._human_wait(1.5, 3)

            cart_item_selectors = [
                ".cart-list-item", ".item-wrapper", "[class*='cart-item']",
                ".item-body", ".J_ItemBody", ".cart-item",
            ]
            for sel in cart_item_selectors:
                with suppress(Exception):
                    locator = page.locator(sel).first
                    if locator.is_visible(timeout=3000):
                        count = page.locator(sel).count()
                        print(f"[browser] confirm cart state => success ({count} items)")
                        return "success"

            if "cart.taobao.com" in page.url or "cart.tmall.com" in page.url:
                print("[browser] confirm cart state => empty (on cart page but no items)")
                return "empty"
            else:
                print("[browser] confirm cart state => error (did not reach cart page)")
                return "error"
        except Exception as e:
            print(f"[browser] confirm cart state => error: {e}")
            return "error"

    def capture_evidence(self, name: str) -> str:
        page = self._ensure_page()
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        path = self.artifact_dir / f"{name}.png"
        page.screenshot(path=str(path), full_page=True)
        print(f"[browser] capture evidence: {path}")
        return str(path)

    # ──────────────────────────────────────────────
    # Human-Like Behavior: Bezier Mouse Movement
    # ──────────────────────────────────────────────

    def _bezier_curve(self, start: tuple[float, float], end: tuple[float, float], steps: int = 20) -> list[tuple[float, float]]:
        """Generate a cubic Bezier curve path from start to end with random control points."""
        sx, sy = start
        ex, ey = end
        dist = math.hypot(ex - sx, ey - sy)

        # Random control points — create natural curvature
        jitter = max(dist * 0.3, 30)
        cp1 = (
            sx + (ex - sx) * random.uniform(0.1, 0.4) + random.uniform(-jitter, jitter),
            sy + (ey - sy) * random.uniform(0.1, 0.4) + random.uniform(-jitter, jitter),
        )
        cp2 = (
            sx + (ex - sx) * random.uniform(0.6, 0.9) + random.uniform(-jitter, jitter),
            sy + (ey - sy) * random.uniform(0.6, 0.9) + random.uniform(-jitter, jitter),
        )

        points = []
        for i in range(steps + 1):
            t = i / steps
            # Ease-in-out: accelerate then decelerate
            t_eased = t * t * (3 - 2 * t)

            x = (1 - t_eased) ** 3 * sx + 3 * (1 - t_eased) ** 2 * t_eased * cp1[0] + 3 * (1 - t_eased) * t_eased ** 2 * cp2[0] + t_eased ** 3 * ex
            y = (1 - t_eased) ** 3 * sy + 3 * (1 - t_eased) ** 2 * t_eased * cp1[1] + 3 * (1 - t_eased) * t_eased ** 2 * cp2[1] + t_eased ** 3 * ey

            # Add slight random jitter
            x += random.uniform(-1.5, 1.5)
            y += random.uniform(-1.5, 1.5)

            points.append((x, y))

        return points

    def _human_click(self, page: Page, locator, timeout: int = 5000) -> None:
        """Click a locator with human-like Bezier mouse movement."""
        try:
            box = locator.bounding_box(timeout=timeout)
            if box is None:
                locator.click(timeout=timeout)
                return

            # Click at a random point within the element (not always center)
            target_x = box["x"] + box["width"] * random.uniform(0.25, 0.75)
            target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

            # Get current mouse position (default to a random start)
            current_x = random.randint(400, 800)
            current_y = random.randint(300, 600)

            # Generate and follow Bezier curve
            points = self._bezier_curve((current_x, current_y), (target_x, target_y), steps=random.randint(15, 30))
            for px, py in points:
                page.mouse.move(px, py)
                time.sleep(random.uniform(0.005, 0.02))

            # Small pause before clicking
            time.sleep(random.uniform(0.05, 0.15))
            page.mouse.click(target_x, target_y)

        except Exception:
            # Fallback to standard click
            with suppress(Exception):
                locator.click(timeout=timeout)

    def _human_type(self, page: Page, text: str) -> None:
        """Type text with human-like variable delays and occasional pauses."""
        for i, char in enumerate(text):
            page.keyboard.type(char)

            # Variable delay between keystrokes
            base_delay = random.uniform(0.03, 0.12)

            # Occasional longer pause (simulating thinking)
            if random.random() < 0.08:
                base_delay = random.uniform(0.2, 0.5)

            time.sleep(base_delay)

    def _human_scroll(self, page: Page, target_y: int = 800) -> None:
        """Scroll the page with human-like variable speed and slight back-scrolling."""
        current_y = page.evaluate("window.scrollY")
        remaining = target_y - current_y

        while abs(remaining) > 50:
            # Variable scroll increment
            step = min(abs(remaining), random.randint(80, 350))
            direction = 1 if remaining > 0 else -1

            # Occasionally scroll back slightly
            if random.random() < 0.15 and abs(remaining) > 200:
                step = -random.randint(20, 60)
                direction = -direction

            page.evaluate(f"window.scrollBy(0, {step * direction})")
            time.sleep(random.uniform(0.3, 1.0))

            current_y = page.evaluate("window.scrollY")
            remaining = target_y - current_y

    def _human_wait(self, min_s: float = 0.5, max_s: float = 2.0) -> None:
        """Wait a random duration to simulate human pause."""
        time.sleep(random.uniform(min_s, max_s))

    def _random_mouse_move(self, page: Page) -> None:
        """Move mouse to a random viewport position (simulating user looking around)."""
        viewport = page.viewport_size
        if viewport is None:
            return
        target_x = random.randint(100, viewport["width"] - 100)
        target_y = random.randint(200, viewport["height"] - 200)
        start_x = random.randint(200, 600)
        start_y = random.randint(200, 500)
        points = self._bezier_curve(
            (start_x, start_y), (target_x, target_y), steps=random.randint(10, 20)
        )
        for px, py in points:
            page.mouse.move(px, py)
            time.sleep(random.uniform(0.008, 0.025))

    def _simulate_browsing(self, page: Page, max_scroll: int = 1200) -> None:
        """Simulate a user browsing the page: scroll in stages, pause, look around."""
        scroll_targets = [
            random.randint(200, 400),
            random.randint(500, 800),
            random.randint(800, max_scroll),
        ]
        for target in scroll_targets:
            self._human_scroll(page, target)
            self._human_wait(0.5, 1.5)
            if random.random() < 0.4:
                self._random_mouse_move(page)
        self._human_scroll(page, random.randint(0, 300))
        self._human_wait(0.3, 1)

    # ──────────────────────────────────────────────
    # Access Control Detection
    # ──────────────────────────────────────────────

    def _wait_for_access_recovery(self, page: Page) -> None:
        for _ in range(90):
            if not self._looks_access_blocked(page):
                return
            with suppress(Exception):
                page.wait_for_timeout(2000)

    def _looks_access_blocked(self, page: Page) -> bool:
        signals = [
            "text=访问被拒绝",
            "text=验证",
            "text=异常流量",
            "text=请拖动滑块",
            "text=请完成验证",
        ]
        for selector in signals:
            with suppress(Exception):
                if page.locator(selector).first.is_visible():
                    return True
        title = ""
        with suppress(Exception):
            title = page.title().lower()
        if "access denied" in title or "验证" in title:
            return True
        return False

    def _handle_captcha_if_present(self, page: Page) -> bool:
        """Detect and auto-solve slider CAPTCHA if present. Returns True if solved."""
        if self._slider_solver.is_captcha_present(page):
            print("[browser] slider CAPTCHA detected, attempting auto-solve...")
            return self._slider_solver.solve(page, max_retries=3)
        return False

    # ──────────────────────────────────────────────
    # DOM Helpers
    # ──────────────────────────────────────────────

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
            "a[href*='item.taobao.com']",
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

    # ──────────────────────────────────────────────
    # Text Processing
    # ──────────────────────────────────────────────

    def _build_keyword_tokens(self, keyword: str) -> list[str]:
        normalized = "".join(keyword.split())
        if len(normalized) < 2:
            return [normalized] if normalized else []
        tokens = {normalized}
        for index in range(len(normalized) - 1):
            chunk = normalized[index : index + 2]
            if len(chunk) == 2:
                tokens.add(chunk)
        return [token for token in tokens if token]

    def _matches_keyword(self, title: str, text: str, tokens: list[str]) -> bool:
        haystack = f"{title}\n{text}"
        return any(token in haystack for token in tokens)

    def _extract_rating(self, text: str) -> float | None:
        patterns = [
            r"好评率\s*([\d.]+)%",
            r"([\d.]+)%\s*好评",
            r"好评\s*([\d.]+)%",
            r"好评率[：:]\s*([\d.]+)%",
            r"好评率[：:]\s*([\d.]+)(?![.\d])",
            r"好评[率]?[：:]\s*([\d.]+)%",
            r"用户评价[：:]\s*([\d.]+)%",
            r"([\d.]+)%\s*[正好评]",
            r"好评.*?([\d.]+)%",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    val = float(match.group(1))
                    if val > 10:
                        return val / 100.0
                    elif 0 < val <= 1.0:
                        return val
                    elif val > 5:
                        return val / 100.0
                except ValueError:
                    continue
        return None
