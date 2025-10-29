from pathlib import Path

from playwright.sync_api import expect, Page


def test_dashboard_smoke(page: Page, dashboard_server: str, screenshot_dir: Path) -> None:
    page.goto(f"{dashboard_server}/dashboard/", wait_until="networkidle")

    expect(page.get_by_role("heading", name="AI Ticket Operations")).to_be_visible()
    expect(page.get_by_role("heading", name="Realtime Metrics")).to_be_visible()

    # Toggle the shortcut overlay and close it again.
    page.keyboard.press("Shift+/")
    overlay = page.get_by_test_id("shortcut-overlay")
    expect(overlay).to_be_visible()
    page.keyboard.press("Escape")
    expect(overlay).not_to_be_visible()

    # Expand the admin panel and toggle a few persistent settings.
    page.get_by_test_id("admin-panel-toggle").click()
    page.get_by_test_id("theme-light").click()
    page.get_by_test_id("pause-stream-toggle").locator("input").check()

    # Capture a regression screenshot for visual drift detection.
    screenshot_path = screenshot_dir / "dashboard-smoke.png"
    page.screenshot(path=str(screenshot_path), full_page=True)

    assert screenshot_path.exists()
