"""Check service pages and browser-local selections without submitting an inquiry."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


KEY = "mrsaintj.shortlist.v1"


def inspect(page):
    page.evaluate("document.querySelectorAll('img').forEach(image => image.loading = 'eager')")
    page.wait_for_function("Array.from(document.images).every(image => !image.getAttribute('src') || (image.complete && image.naturalWidth > 0))")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.url
    assert page.evaluate("Array.from(document.querySelectorAll('script[type=\"application/ld+json\"]')).every(script => JSON.parse(script.textContent)['@graph'].length > 0)")
    for name in ("Epic Action Imagery", "Sportograf", "FinisherPix"):
        assert name not in page.locator("body").inner_text()


def verify(base_url, output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    pages = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for width in (320, 375, 768, 1024, 1440):
            context = browser.new_context(viewport={"width": width, "height": 900 if width >= 768 else 812})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            for language in ("en", "fr"):
                page.goto(f"{base_url}/{language}/services/", wait_until="networkidle")
                links = page.locator(".offering-detail").evaluate_all("links => [...new Set(links.map(link => link.getAttribute('href')))]")
                assert len(links) == 3, links
                for path in [f"/{language}/services/", *links, f"/{language}/shortlist/"]:
                    response = page.goto(base_url + path, wait_until="networkidle")
                    assert response.status == 200, path
                    inspect(page)
                    name = path.strip("/").replace("/", "-")
                    page.screenshot(path=str(output / f"{name}-{width}.png"), full_page=True)
                    pages += 1
                page.goto(base_url + links[0], wait_until="networkidle")
                if not page.locator(".language-link").is_visible():
                    page.locator(".menu-toggle").click()
                page.locator(".language-link").click()
                assert page.url.endswith("/photographie-sportive-montreal/" if language == "en" else "/sports-photography-montreal/")
            page.goto(f"{base_url}/en/work/", wait_until="networkidle")
            first = page.locator(".gallery-grid [data-save-photo]").first
            first_id = first.get_attribute("data-save-photo")
            first.click()
            page.wait_for_function("document.querySelector('[data-shortlist-count]').textContent === '1'")
            assert first.get_attribute("aria-pressed") == "true"
            page.wait_for_load_state("networkidle")
            page.locator("[data-lightbox-index]").nth(1).click()
            lightbox_save = page.locator("dialog [data-save-photo]")
            lightbox_save.click()
            page.wait_for_function("document.querySelector('[data-shortlist-count]').textContent === '2'")
            page.wait_for_load_state("networkidle")
            page.keyboard.press("ArrowRight")
            assert lightbox_save.get_attribute("aria-pressed") == "false"
            third_id = lightbox_save.get_attribute("data-save-photo")
            lightbox_save.click()
            page.wait_for_load_state("networkidle")
            page.keyboard.press("Escape")
            page.goto(f"{base_url}/en/photos/{third_id}/", wait_until="networkidle")
            detail_save = page.locator("main [data-save-photo]")
            assert detail_save.get_attribute("aria-pressed") == "true"
            detail_save.click()
            page.wait_for_load_state("networkidle")
            page.goto(f"{base_url}/fr/contact/", wait_until="networkidle")
            ids = json.loads(page.locator("#id_selected_photos").input_value())
            assert len(ids) == 2 and first_id in ids and third_id not in ids
            assert page.locator("[data-inquiry-selection] .photo-item").count() == 2
            inspect(page)
            page.screenshot(path=str(output / f"fr-contact-selection-{width}.png"), full_page=True)
            page.goto(f"{base_url}/en/shortlist/", wait_until="networkidle")
            assert page.locator("[data-shortlist-root] .photo-item").count() == 2
            assert page.locator("[data-shortlist-inquiry]").is_visible()
            inspect(page)
            page.screenshot(path=str(output / f"en-saved-selection-{width}.png"), full_page=True)
            page.locator("[data-shortlist-root] [data-save-photo]").first.click()
            page.wait_for_function("document.querySelectorAll('[data-shortlist-root] .photo-item').length === 1")
            assert page.locator("[data-shortlist-root] [data-save-photo]").first.evaluate("button => button === document.activeElement")
            page.locator("[data-shortlist-clear]").click()
            page.wait_for_function("document.querySelectorAll('[data-shortlist-root] .photo-item').length === 0")
            assert not page.locator("[data-shortlist-inquiry]").is_visible()
            assert json.loads(page.evaluate(f"localStorage.getItem('{KEY}')")) == []
            if width in (375, 1440):
                page.goto(f"{base_url}/en/work/", wait_until="networkidle")
                for index in range(13):
                    page.locator(".gallery-grid [data-save-photo]").nth(index).click()
                    page.wait_for_load_state("networkidle")
                assert len(json.loads(page.evaluate(f"localStorage.getItem('{KEY}')"))) == 12
                assert page.locator("[data-shortlist-status]").inner_text() == "You can save up to 12 photographs."
                page.goto(f"{base_url}/en/contact/", wait_until="networkidle")
                assert len(json.loads(page.locator("#id_selected_photos").input_value())) == 12
                inspect(page)
                page.screenshot(path=str(output / f"en-contact-limit-{width}.png"), full_page=True)
            page.evaluate(f"localStorage.setItem('{KEY}', '{{corrupt')")
            page.reload(wait_until="networkidle")
            assert page.locator("[data-shortlist-count]").first.inner_text() == "0"
            stale = "00000000-0000-0000-0000-000000000001"
            page.evaluate("([key, ids]) => localStorage.setItem(key, JSON.stringify(ids))", [KEY, [first_id, stale]])
            page.goto(f"{base_url}/en/shortlist/", wait_until="networkidle")
            assert json.loads(page.evaluate(f"localStorage.getItem('{KEY}')")) == [first_id]
            context.close()
        blocked = browser.new_context(viewport={"width": 375, "height": 812})
        blocked.add_init_script("Object.defineProperty(window, 'localStorage', {get() {throw new DOMException('Storage blocked');}})")
        page = blocked.new_page()
        page.goto(f"{base_url}/en/work/", wait_until="networkidle")
        assert page.locator(".gallery-grid [data-save-photo]").first.is_disabled()
        page.locator("[data-lightbox-index]").first.click()
        assert page.locator("dialog").is_visible()
        page.keyboard.press("Escape")
        page.goto(f"{base_url}/en/contact/", wait_until="networkidle")
        assert page.locator("#id_selected_photos").input_value() == "[]"
        blocked.close()
        no_js = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 812})
        page = no_js.new_page()
        page.goto(f"{base_url}/fr/services/photographie-sports-equipe/", wait_until="networkidle")
        assert page.locator("main h1").inner_text().startswith("Photographie de sports")
        page.locator("main .photo-item a").first.click()
        assert "/photos/" in page.url
        assert page.locator("main [data-save-photo]").is_hidden()
        no_js.close()
        browser.close()
    assert not errors, errors
    print(json.dumps({"service_pages_checked": pages, "widths": [320, 375, 768, 1024, 1440],
                      "javascript_errors": errors, "screenshots": str(output),
                      "interactions": "localized service switching, gallery/lightbox/detail saves, persistence, contact preview, keyboard removal, clear, 12-photo limit, corrupt/blocked storage, stale IDs, no-JS browsing"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/discovery"))
    args = parser.parse_args()
    verify(args.url.rstrip("/"), args.output)
