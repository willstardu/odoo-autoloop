"""
Odoo 19 E2E 测试：登录 + OmniPod 备件库（baselife_stock）冒烟测试。
确定性断言，失败时输出截图/日志供 Qwen 诊断。
"""
import os
import time
import json
import traceback
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from src.config import settings


class OdooE2E:
    def __init__(self):
        self.url = settings.ODOO_URL
        self.user = settings.ODOO_USER
        self.password = settings.ODOO_PASSWORD
        self.headless = settings.HEADLESS
        self.out = {
            "passed": False,
            "logs": [],
            "screenshot": None,
            "page_source": None,
            "console": [],
            "errors": [],
        }

    def log(self, msg):
        self.out["logs"].append(msg)
        print(f"    {msg}")

    def run(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            page = browser.new_page(viewport={"width": 1600, "height": 900})

            page.on("console", lambda m: self.out["console"].append(f"[{m.type}] {m.text}"))
            page.on("pageerror", lambda e: self.out["errors"].append(str(e)))

            try:
                self.test_login(page)
                self.test_omnipod_open(page)
                self.test_omnipod_pages(page)
                self.out["passed"] = True
                self.log("ALL TESTS PASSED")
            except PlaywrightTimeoutError as e:
                self.out["errors"].append(f"TIMEOUT: {e}")
                self.save_failure(page, "timeout")
            except Exception as e:
                self.out["errors"].append(f"{type(e).__name__}: {e}")
                self.save_failure(page, "exception")
            finally:
                browser.close()
        return self.out

    def save_failure(self, page, tag):
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(settings.SCREENSHOTS, f"failure_{tag}_{ts}.png")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            page.screenshot(path=path, full_page=True)
            self.out["screenshot"] = path
            self.log(f"screenshot saved: {path}")
        except Exception as e:
            self.log(f"screenshot failed: {e}")
        try:
            self.out["page_source"] = page.content()[:200000]
        except Exception:
            pass

    # ---------- tests ----------

    def test_login(self, page):
        self.log("visit login page")
        page.goto(f"{self.url}/web/login", wait_until="networkidle", timeout=60000)

        self.log("fill credentials")
        page.fill("#login", self.user)
        page.fill("#password", self.password)
        page.click("button[type='submit']")

        self.log("wait for app shell")
        page.wait_for_selector("header.o_navbar", timeout=45000)

        assert "web/login" not in page.url, "仍停留在登录页，登录失败"
        self.log(f"login OK, url={page.url}")

    def test_omnipod_open(self, page):
        """打开 OmniPod 应用（顶部应用菜单）"""
        self.log("open apps menu")
        page.click(".o_navbar_apps_menu button")
        page.wait_for_timeout(1200)

        self.log("find & click OmniPod app")
        omnipod = page.locator("a.o_app", has_text="OmniPod")
        omnipod.first.click(timeout=8000)
        self.log("clicked OmniPod")
        page.wait_for_timeout(3000)

        # 确认当前品牌为 OmniPod
        brand = page.locator("a.o_menu_brand").first
        assert "OmniPod" in (brand.inner_text() or ""), f"品牌栏未显示 OmniPod: {brand.inner_text()}"
        self.log("OmniPod app opened")

    def test_omnipod_pages(self, page):
        """遍历 menu_map.json 中所有叶子菜单，直接 action URL 导航并验证"""
        menu_map_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu_map.json")
        with open(menu_map_path, "r", encoding="utf-8") as f:
            menu_map = json.load(f)

        leaf_actions = [
            item for item in menu_map
            if not item.get("children") and item.get("actionID") not in (False, None)
        ]
        self.log(f"OmniPod leaf menu actions to test: {len(leaf_actions)}")

        base_url = settings.ODOO_URL.rstrip("/")
        screenshot_dir = settings.SCREENSHOTS
        os.makedirs(screenshot_dir, exist_ok=True)

        failures = []
        for menu in leaf_actions:
            action_id = menu["actionID"]
            name = menu.get("name", "unknown")
            url = f"{base_url}/odoo/action-{action_id}"
            self.log(f"Testing menu: {name} -> {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".o_control_panel, .o_action", state="visible", timeout=20000)
                error_loc = page.locator(".o_error, .o_dialog_error")
                for i in range(error_loc.count()):
                    if error_loc.nth(i).is_visible():
                        raise AssertionError(error_loc.nth(i).inner_text().strip()[:500])
                page.screenshot(path=os.path.join(screenshot_dir, f"page_{action_id}.png"))
                self.log(f"PASS: {name} (action {action_id})")
            except Exception as exc:
                self.log(f"FAIL: {name} (action {action_id}) - {exc}")
                failures.append((action_id, name, str(exc)))
                self.save_failure(page, f"omnipod_page_{action_id}")

        assert not failures, f"OmniPod page tests failed: {failures}"


def run_e2e() -> dict:
    t = OdooE2E()
    try:
        return t.run()
    except Exception:
        t.out["errors"].append(traceback.format_exc())
        return t.out


def run_e2e_json() -> str:
    return json.dumps(run_e2e(), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    result = run_e2e()
    print(json.dumps(result, ensure_ascii=False, indent=2))
