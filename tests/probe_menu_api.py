"""提取 baselife_stock 菜单（扁平结构），保存供 GLM 分析"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright
from src.config import settings


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.HEADLESS)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto(f"{settings.ODOO_URL}/web/login", wait_until="networkidle", timeout=60000)
        page.fill("#login", settings.ODOO_USER)
        page.fill("#password", settings.ODOO_PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_selector("header.o_navbar", timeout=45000)

        data = page.evaluate("""async () => {
            const res = await fetch('/web/webclient/load_menus');
            return await res.json();
        }""")
        browser.close()

    menus = list(data.values()) if isinstance(data, dict) else []
    baselife = [m for m in menus if m.get("xmlid", "").startswith("baselife_stock")]
    print(f"total menus: {len(menus)}, baselife_stock: {len(baselife)}")
    for m in sorted(baselife, key=lambda x: x["id"]):
        print(f"  id={m['id']:<5} xmlid={m['xmlid']:<55} name={m['name']:<12} actionID={m.get('actionID')} children={len(m.get('children', []))}")

    with open(os.path.join(settings.BASE_DIR, "tests", "menu_map.json"), "w", encoding="utf-8") as f:
        json.dump(baselife, f, ensure_ascii=False, indent=2)
    print(f"\nsaved to tests/menu_map.json")


if __name__ == "__main__":
    main()
