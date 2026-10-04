"""Inspect a running local portfolio; save screenshots without submitting real inquiries."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def verify(base_url, output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for width in (320, 375, 768, 1024, 1440):
            page = browser.new_page(viewport={"width": width, "height": 900 if width >= 768 else 812}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            for language in ("en", "fr"):
                for route in ("", "work/", "about/", "contact/", "stories/", "stories/race-day/"):
                    response = page.goto(f"{base_url}/{language}/{route}", wait_until="networkidle")
                    assert response.status == 200, (width, language, route, response.status)
                    page.evaluate("document.querySelectorAll('img').forEach(image => image.loading = 'eager')")
                    page.wait_for_function("Array.from(document.images).every(image => !image.getAttribute('src') || (image.complete && image.naturalWidth > 0))")
                    if route == "about/":
                        portrait = page.locator(".about-image img")
                        assert "images/justin-st-laurent" in portrait.get_attribute("src")
                        assert portrait.evaluate("image => image.naturalWidth === 959 && image.naturalHeight === 960")
                    dimensions = page.evaluate("({viewport:innerWidth, document:document.documentElement.scrollWidth})")
                    assert dimensions["document"] <= dimensions["viewport"], (width, language, route, dimensions)
                    name = route.strip("/").replace("/", "-") or "home"
                    if language == "en" or route in ("", "contact/"):
                        page.screenshot(path=str(output / f"{language}-{name}-{width}.png"), full_page=True)
                    results.append({"width": width, "language": language, "page": name, "status": response.status})
            page.goto(f"{base_url}/en/work/", wait_until="networkidle")
            origin = page.locator("[data-lightbox-index]").first
            origin.click()
            dialog = page.locator("dialog")
            assert dialog.is_visible()
            page.wait_for_function("document.querySelector('.lightbox-image').naturalWidth > 0")
            page.keyboard.press("ArrowRight")
            assert page.locator(".lightbox-count").inner_text().startswith("02")
            for _ in range(7):
                page.keyboard.press("Tab")
                assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)")
            page.screenshot(path=str(output / f"lightbox-{width}.png"))
            page.keyboard.press("Escape")
            assert not dialog.is_visible()
            assert origin.evaluate("element => element === document.activeElement")
            total = int(page.locator(".gallery-total").inner_text().split()[0])
            seen = set()
            page_number = 1
            while True:
                links = page.locator(".gallery-grid .photo-item a").evaluate_all("links => links.map(link => link.getAttribute('href'))")
                assert links and len(set(links)) == len(links)
                assert not seen.intersection(links), (width, page_number, "Duplicate gallery photographs")
                seen.update(links)
                next_page = page.locator(".pagination a").filter(has_text="Next")
                if not next_page.count():
                    break
                next_page.click()
                page.wait_for_load_state("networkidle")
                page_number += 1
                page.evaluate("document.querySelectorAll('img').forEach(image => image.loading = 'eager')")
                page.wait_for_function("Array.from(document.images).every(image => !image.getAttribute('src') || (image.complete && image.naturalWidth > 0))")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / f"en-work-page-{page_number}-{width}.png"), full_page=True)
                results.append({"width": width, "language": "en", "page": f"work-page-{page_number}", "status": 200})
            assert len(seen) == total, (width, len(seen), total)
            if page_number > 1:
                page.locator("[data-lightbox-index]").last.click()
                page.wait_for_function("document.querySelector('.lightbox-image').naturalWidth > 0")
                assert page.locator("dialog").is_visible()
                page.keyboard.press("Escape")
            if width <= 600:
                button = page.locator(".menu-toggle")
                button.click()
                assert button.get_attribute("aria-expanded") == "true"
                page.keyboard.press("Escape")
                assert button.get_attribute("aria-expanded") == "false"
            page.close()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{base_url}/en/work/?category=race-day", wait_until="networkidle")
        filtered_ids = page.locator(".gallery-grid .photo-item a").evaluate_all("links => links.map(link => link.getAttribute('href').split('/photos/')[1])")
        assert filtered_ids
        page.locator(".language-link").click()
        assert "/fr/work/?category=race-day" in page.url
        assert page.locator(".gallery-grid .photo-item a").evaluate_all("links => links.map(link => link.getAttribute('href').split('/photos/')[1])") == filtered_ids
        page.goto(f"{base_url}/en/contact/", wait_until="networkidle")
        page.get_by_role("button", name="Send inquiry").click()
        assert page.locator(".field-errors").count() == 3
        page.close()
        no_js = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 812})
        page = no_js.new_page()
        page.goto(f"{base_url}/en/work/?category=team-sports", wait_until="networkidle")
        assert page.locator(".site-nav").is_visible()
        assert page.locator(".gallery-grid .photo-item").count() > 0
        page.locator(".photo-item a").first.click()
        assert "/photos/" in page.url
        assert page.locator(".photo-detail picture img").count() == 1
        no_js.close()
        browser.close()
    assert not errors, errors
    print(json.dumps({"pages_checked": len(results), "widths": [320, 375, 768, 1024, 1440],
                      "javascript_errors": errors, "screenshots": str(output),
                      "interactions": "complete gallery pagination, lightbox on both pages, keyboard focus, menu, filters, language, validation, no-JS navigation"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/screenshots"))
    args = parser.parse_args()
    verify(args.url.rstrip("/"), args.output)
