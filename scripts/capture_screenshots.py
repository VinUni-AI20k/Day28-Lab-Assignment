"""Headless browser screenshots for Prefect UI and Grafana dashboard.

Uses Playwright's bundled Chromium (isolated from the user's Chrome).
"""
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

SCREENSHOTS = Path("/Users/bean/Day28-Lab-Assignment/screenshots")

TARGETS = [
    {
        "name": "prefect_ui",
        "url": "http://localhost:4200/deployments",
        "wait_for_selector": "text=kafka-to-delta-scheduled",
        "viewport": {"width": 1600, "height": 900},
        "wait_after": 1500,
    },
    {
        "name": "grafana_dashboard",
        "url": "http://localhost:3000/d/lab28-api-gateway/lab-28-api-gateway-overview?orgId=1&refresh=10s&from=now-15m&to=now&kiosk=tv",
        "wait_for_selector": "text=Lab 28 — API Gateway Overview",
        "viewport": {"width": 1800, "height": 1100},
        "wait_after": 4000,
    },
]


def main():
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for tgt in TARGETS:
            ctx = browser.new_context(viewport=tgt["viewport"], device_scale_factor=2)
            page = ctx.new_page()
            print(f"[{tgt['name']}] navigating to {tgt['url']}")
            page.goto(tgt["url"], wait_until="networkidle", timeout=30000)
            try:
                page.wait_for_selector(tgt["wait_for_selector"], timeout=15000)
                print(f"[{tgt['name']}] target selector matched")
            except Exception as exc:
                print(f"[{tgt['name']}] selector wait failed: {exc}")
            time.sleep(tgt["wait_after"] / 1000)
            out = SCREENSHOTS / f"{tgt['name']}.png"
            page.screenshot(path=str(out), full_page=False)
            print(f"[{tgt['name']}] wrote {out} ({out.stat().st_size:,} bytes)")
            ctx.close()
        browser.close()


if __name__ == "__main__":
    main()
