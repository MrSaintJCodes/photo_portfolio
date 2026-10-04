"""Exercise six-service inquiries and the decorative, full-document arrival effect."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


PENDING = "mrsaintj.camera.pending.v1"
FLASH = "mrsaintj.camera.flash.v1"
KEYS = ["athlete-portraits", "team-photos", "sports-action", "race-events", "sports-events", "fitness-promotion"]
TRACK = """
window.cameraRuns = [];
new MutationObserver(records => {
  for (const record of records) {
    const camera = record.target;
    if (!camera.matches?.('[data-pixel-camera]')) continue;
    const run = cameraRuns.at(-1);
    if (camera.classList.contains('is-playing')) {
      if (!run || run.end) cameraRuns.push({start: performance.now(), wall: Date.now()});
    } else if (run && !run.end) run.end = performance.now();
  }
}).observe(document, {subtree: true, attributes: true, attributeFilter: ['class']});
"""


def ready(page):
    page.evaluate("document.querySelectorAll('img').forEach(image => image.loading = 'eager')")
    page.wait_for_function("Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), page.url


def nav(page, selector):
    if selector.startswith(".site-nav") and not page.locator(selector).is_visible():
        page.locator(".menu-toggle").click()
    with page.expect_navigation(wait_until="domcontentloaded"):
        page.locator(selector).first.click()


def settled(page, expected, fallback=False):
    page.wait_for_timeout(650 if fallback else 480)
    assert len(page.evaluate("cameraRuns")) == expected, (page.url, page.evaluate("cameraRuns"))
    assert page.locator("[data-pixel-camera]").is_hidden()
    assert page.locator("[data-pixel-camera-backdrop]").is_hidden()
    for run in page.evaluate("cameraRuns"):
        assert run.get("end") and run["end"] - run["start"] <= (650 if fallback else 450), run
    assert page.evaluate(f"sessionStorage.getItem('{PENDING}')") is None


def verify(base, output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(TRACK)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        for width in (320, 375, 768, 1024, 1440):
            page.set_viewport_size({"width": width, "height": 900 if width >= 768 else 812})
            for language in ("en", "fr"):
                page.goto(f"{base}/{language}/services/", wait_until="networkidle")
                ready(page)
                assert page.locator(f'.site-nav a[href="/{language}/stories/"]').count() == 0
                assert page.locator(".offering-card").count() == 6
                assert page.locator(".offering-inquiry").evaluate_all("links => links.map(link => new URL(link.href).searchParams.get('service'))") == KEYS
                columns = page.locator(".offering-grid").evaluate("grid => getComputedStyle(grid).gridTemplateColumns.split(' ').length")
                assert columns == (1 if width < 700 else 2)
                assert "54689682884" in page.locator(".services-hero img").get_attribute("src")
                assert page.locator(".services-hero img").evaluate("img => img.naturalWidth >= img.clientWidth")
                assert page.locator("#team-photos img").count() == 1
                assert "54645194272" in page.locator("#team-photos img").get_attribute("src")
                assert page.locator("#team-photos img").evaluate("img => getComputedStyle(img).objectFit === 'contain'")
                assert len(page.locator(".services-planning li").all()) == 4
                assert page.locator(".services-overview .text-link").first.get_attribute("href") == f"/{language}/contact/"
                for name in ("Epic Action Imagery", "Sportograf", "FinisherPix"):
                    assert name not in page.locator("body").inner_text()
                assert page.locator(".services-hero").bounding_box()["y"] < (812 if width < 768 else 900)
                assert page.locator("main h1").evaluate("h => h.getBoundingClientRect().bottom < innerHeight")
                page.screenshot(path=str(output / f"services-{language}-{width}.png"), full_page=True)
                checks.append(f"services-{language}-{width}")
        page.set_viewport_size({"width": 1440, "height": 900})
        for language in ("en", "fr"):
            for key in KEYS:
                page.goto(f"{base}/{language}/services/", wait_until="domcontentloaded")
                nav(page, f"#{key} .offering-inquiry")
                assert page.locator("#id_service").input_value() == key
                page.locator("#id_service").select_option("team-photos")
                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.locator(".submit-button").click()
                assert page.locator("#id_service").input_value() == "team-photos"
                assert page.locator(".field-errors").count() >= 2
                assert page.evaluate("cameraRuns.length") == 0  # Invalid POST, no inquiry sent.
                checks.append(f"inquiry-{language}-{key}")

        for destination in ("work", "services", "about", "contact"):
            page.set_viewport_size({"width": 1440, "height": 900 if destination == "contact" else 1000})
            page.goto(f"{base}/en/", wait_until="networkidle")
            assert page.locator(".stories-section").count() == 0
            page.evaluate("sessionStorage.clear()")
            nav(page, f'.site-nav a[href="/en/{destination}/"]')
            settled(page, 1)
            assert page.evaluate("document.activeElement === document.body"), destination
            assert page.evaluate("scrollY") == 0
            checks.append(f"arrival-{destination}")

        page.goto(f"{base}/en/stories/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        nav(page, ".story-row:first-child .story-row-photo")
        settled(page, 1)
        page.wait_for_timeout(1100)
        nav(page, ".language-link")
        settled(page, 1)
        assert "/fr/stories/" in page.url
        checks.extend(["story-card", "language-switch"])

        page.goto(f"{base}/en/about/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        page.locator('.site-nav a[href="/en/contact/"]').focus()
        with page.expect_navigation(wait_until="domcontentloaded"):
            page.keyboard.press("Enter")
        settled(page, 1)
        page.reload(wait_until="domcontentloaded")
        settled(page, 0)
        page.go_back(wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        assert page.locator("[data-pixel-camera]").is_hidden()
        page.go_forward(wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        assert page.locator("[data-pixel-camera]").is_hidden()
        checks.extend(["keyboard", "reload", "history"])

        # Immediate subsequent navigation must clear the old sequence and honor cooldown.
        page.goto(f"{base}/en/about/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        nav(page, '.site-nav a[href="/en/contact/"]')
        page.wait_for_function(f"Number(sessionStorage.getItem('{FLASH}')) > 0")
        first = page.evaluate(f"Number(sessionStorage.getItem('{FLASH}'))")
        nav(page, '.site-nav a[href="/en/services/"]')
        second = page.evaluate(f"Number(sessionStorage.getItem('{FLASH}'))")
        assert first == second, (first, second)
        settled(page, 0)
        checks.append("rapid-navigation")

        for width in (375, 768, 1440):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(f"{base}/en/about/", wait_until="networkidle")
            page.evaluate("sessionStorage.clear()")
            # Freeze only browser-test animations for a deterministic artwork screenshot.
            page.add_init_script("new MutationObserver(() => { if(document.querySelector('[data-pixel-camera].is-playing')) document.querySelectorAll('[data-pixel-camera], [data-pixel-camera-backdrop]').forEach(e => e.getAnimations({subtree:true}).forEach(a => {a.pause();a.currentTime=165;})); }).observe(document,{subtree:true,attributes:true,attributeFilter:['class']});")
            nav(page, '.site-nav a[href="/en/services/"]')
            camera = page.locator("[data-pixel-camera]")
            assert camera.evaluate("e => e.getBoundingClientRect().width") == (48 if width <= 600 else 96)
            assert camera.evaluate("e => {const r=e.getBoundingClientRect();return Math.abs(r.left+r.width/2-innerWidth/2)<1 && Math.abs(r.top+r.height/2-innerHeight/2)<1;}")
            assert page.locator('[data-pixel-camera-backdrop]').evaluate("e => getComputedStyle(e).backdropFilter === 'blur(2px)' && getComputedStyle(e).pointerEvents === 'none'")
            assert camera.locator("rect").evaluate_all("rects => rects.every(r => ['x','y','width','height'].every(a => Number.isInteger(Number(r.getAttribute(a)))))")
            page.screenshot(path=str(output / f"camera-{width}.png"))
            settled(page, 1, fallback=True)  # Also clean up paused test animations.
            checks.append(f"camera-art-{width}")
        context.close()

        # Isolated contexts avoid screenshot-freezing hooks in behavioral checks.
        def isolated(initial="", reduced="no-preference", js=True):
            c = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion=reduced, java_script_enabled=js)
            if js:
                c.add_init_script(TRACK)
                if initial:
                    c.add_init_script(initial)
            p = c.new_page()
            p.on("pageerror", lambda error: errors.append(str(error)))
            return c, p

        for raw in ("{corrupt", "[]", "null", '{"destination":"/en/about/","createdAt":"bad"}',
                    json.dumps({"destination": "/en/work/", "createdAt": 0})):
            c, p = isolated()
            p.goto(f"{base}/en/about/", wait_until="domcontentloaded")
            p.evaluate("([key,value])=>sessionStorage.setItem(key,value)", [PENDING, raw])
            p.goto(f"{base}/en/services/", wait_until="domcontentloaded")
            settled(p, 0)
            c.close()
        checks.append("invalid-storage-records")
        for offset, destination in ((-16000, "/en/services/"), (1000, "/en/services/"), (0, "/en/services/?different=1")):
            c, p = isolated()
            p.goto(f"{base}/en/about/", wait_until="domcontentloaded")
            p.evaluate("([key,offset,destination])=>sessionStorage.setItem(key,JSON.stringify({destination,createdAt:Date.now()+offset}))", [PENDING, offset, destination])
            p.goto(f"{base}/en/services/", wait_until="domcontentloaded")
            settled(p, 0)
            c.close()
        checks.append("expired-future-mismatched-records")

        for setup, reduced in (("", "reduce"), ("Object.defineProperty(window,'sessionStorage',{get(){throw new DOMException('Blocked');}})", "no-preference")):
            c, p = isolated(setup, reduced)
            p.goto(f"{base}/en/about/", wait_until="networkidle")
            nav(p, '.site-nav a[href="/en/contact/"]')
            p.wait_for_timeout(480)
            assert p.evaluate("cameraRuns.length") == 0
            assert p.locator("[data-pixel-camera]").is_hidden()
            assert p.locator("#id_service").count() == 1
            c.close()
        checks.extend(["reduced-motion", "blocked-storage"])
        c, p = isolated(js=False)
        p.goto(f"{base}/fr/services/", wait_until="networkidle")
        p.locator("#team-photos .offering-inquiry").click()
        assert p.locator("#id_service").input_value() == "team-photos"
        assert p.locator("[data-pixel-camera]").is_hidden()
        c.close()
        checks.append("no-javascript")

        c, p = isolated()
        p.goto(f"{base}/en/about/", wait_until="networkidle")
        nav(p, '.site-nav a[href="/en/services/"]')
        p.emulate_media(reduced_motion="reduce")
        assert p.locator("[data-pixel-camera]").is_hidden()
        p.emulate_media(reduced_motion="no-preference")
        assert p.locator("[data-pixel-camera]").is_hidden()
        checks.append("live-motion-change")
        p.goto(f"{base}/en/work/", wait_until="networkidle")
        p.locator("[data-lightbox-index]").first.click()
        assert p.locator("dialog").is_visible()
        assert p.evaluate("cameraRuns.length") == 0
        p.keyboard.press("Escape")
        checks.append("lightbox-no-effect")
        p.evaluate("sessionStorage.clear()")
        nav(p, '.gallery-filters a[href*="category="]')
        settled(p, 0)
        checks.append("gallery-filter-no-effect")
        p.set_viewport_size({"width": 1440, "height": 1000})
        nav(p, ".language-link")
        settled(p, 1)
        assert "/fr/work/" in p.url and "category=" in p.url
        checks.append("filtered-gallery-language-switch")
        p.goto(f"{base}/en/services/", wait_until="networkidle")
        p.evaluate("sessionStorage.clear()")
        p.locator(".skip-link").focus()
        p.keyboard.press("Enter")
        assert p.url.endswith("#main")
        assert p.evaluate(f"sessionStorage.getItem('{PENDING}')") is None
        checks.append("same-page-anchor")
        p.evaluate("document.querySelector('.site-nav a[href=\"/en/about/\"]').addEventListener('click',e=>e.preventDefault(),{once:true})")
        p.locator('.site-nav a[href="/en/about/"]').click()
        assert "/en/services/" in p.url
        assert p.evaluate(f"sessionStorage.getItem('{PENDING}')") is None
        checks.append("cancelled-click")
        p.evaluate("""() => {const a=document.createElement('a');a.href='/en/about/';a.download='about.html';a.dataset.cameraTransition='';a.id='test-download';a.textContent='Download';document.body.append(a);}""")
        with p.expect_download():
            p.locator("#test-download").click()
        assert p.evaluate(f"sessionStorage.getItem('{PENDING}')") is None
        checks.append("download-no-effect")
        p.evaluate("""() => {const a=document.createElement('a');a.href='/en/about/';a.target='_blank';a.dataset.cameraTransition='';a.id='test-target';a.textContent='New tab';document.body.append(a);}""")
        with p.expect_popup() as popup:
            p.locator("#test-target").click()
        popup.value.close()
        assert p.evaluate(f"sessionStorage.getItem('{PENDING}')") is None
        checks.append("new-tab-no-effect")
        # Observe writes even when a navigation leaves the current document.
        writes = []
        c.expose_binding("cameraWrite", lambda source, key: writes.append(key))
        c.add_init_script("const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k.startsWith('mrsaintj.camera.'))window.cameraWrite(k);return set.call(this,k,v)}")
        for attributes in ({"href": "https://example.invalid/"}, {"href": "/admin/"}):
            p.goto(f"{base}/en/services/", wait_until="networkidle")
            c.route("https://example.invalid/**", lambda route: route.fulfill(body="<html><title>External</title></html>", content_type="text/html"))
            p.evaluate("attrs => {const a=document.createElement('a');Object.assign(a,attrs);a.dataset.cameraTransition='';a.id='test-ignored';a.textContent='Link';document.body.append(a)}", attributes)
            with p.expect_navigation(wait_until="domcontentloaded"):
                p.locator("#test-ignored").click()
            assert not writes, writes
        checks.extend(["external-no-effect", "admin-no-effect"])
        for button, modifiers in (("left", ["Meta"]), ("middle", [])):
            p.goto(f"{base}/en/services/", wait_until="networkidle")
            existing = set(c.pages)
            p.locator('.site-nav a[href="/en/about/"]').click(button=button, modifiers=modifiers)
            p.wait_for_timeout(250)
            for popup in set(c.pages) - existing:
                popup.close()
            assert not writes, writes
            assert p.evaluate(f"sessionStorage.getItem('{PENDING}')") is None
        checks.append("modified-and-middle-clicks")
        p.goto(f"{base}/en/services/", wait_until="networkidle")
        nav(p, '.site-nav a[href="/en/contact/"]')
        assert PENDING in writes  # Validate the write observer against an ordinary click.
        c.close()

        for injection, label in (
            ("document.querySelector('.menu-toggle').setAttribute('aria-expanded','true');", "open-menu-suppression"),
            ("const d=document.createElement('dialog');document.body.append(d);d.showModal();", "dialog-suppression"),
        ):
            c, p = isolated()
            p.goto(f"{base}/en/about/", wait_until="domcontentloaded")
            p.evaluate("key=>sessionStorage.setItem(key,JSON.stringify({destination:'/en/services/',createdAt:Date.now()}))", PENDING)
            def inject(route):
                response = route.fetch()
                route.fulfill(response=response, body=injection + response.text())
            p.route("**/js/pixel-camera.js", inject)
            p.goto(f"{base}/en/services/", wait_until="domcontentloaded")
            settled(p, 0)
            checks.append(label)
            c.close()

        c, p = isolated()
        p.goto(f"{base}/en/services/", wait_until="networkidle")
        p.evaluate("key=>sessionStorage.setItem(key,JSON.stringify({destination:location.pathname+location.search,createdAt:Date.now()}))", PENDING)
        p.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        settled(p, 0)
        p.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        settled(p, 0)
        checks.append("cached-arrival-discards-pending")
        c.close()
        browser.close()
    assert not errors, errors
    print(json.dumps({"checks": len(checks), "passed": checks, "javascript_errors": errors,
                      "screenshots": str(output)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/signature-services"))
    args = parser.parse_args()
    verify(args.url.rstrip("/"), args.output)
