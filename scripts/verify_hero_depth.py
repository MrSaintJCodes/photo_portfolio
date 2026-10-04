"""Check the real hero canvas, responsive framing, motion, and still-photo fallbacks."""
import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright


def pixels(data):
    return Image.open(io.BytesIO(data)).convert("RGB")


def check_photo(data):
    image = pixels(data)
    # Inspect the photo above the copy, not text that could conceal a blank canvas.
    top = image.crop((0, 0, image.width, int(image.height * 0.4)))
    stats = ImageStat.Stat(top)
    assert sum(stats.mean) / 3 > 45, stats.mean
    assert sum(stats.stddev) / 3 > 20, stats.stddev
    assert top.getcolors(2048) is None, "Photo contains too few colors"
    for x in (0, image.width - 12):
        edge = top.crop((x, 0, x + 12, top.height))
        assert sum(ImageStat.Stat(edge).mean) / 3 > 15, "Uncovered canvas edge"


def still_photo(page):
    assert not page.locator(".hero").evaluate("hero => hero.classList.contains('has-depth')")
    images = page.locator(".hero-photo img, .mobile-hero-photo img")
    assert images.evaluate_all("images => images.some(image => image.getClientRects().length && image.complete && image.naturalWidth > 0 && getComputedStyle(image.parentElement.parentElement).opacity === '1')")
    check_photo(page.locator(".hero").screenshot())


def ready(page):
    page.wait_for_function("document.querySelector('.hero').dataset.depthState === 'ready'")
    page.wait_for_timeout(1100)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    bounds = page.locator(".hero-depth-canvas").bounding_box()
    assert bounds == page.locator(".hero").bounding_box(), "Canvas is not full-bleed"
    assert page.locator("canvas").evaluate("canvas => canvas.getContext('webgl2').getError() === 0")
    check_photo(page.locator(".hero-depth-canvas").screenshot())


def verify(base_url, output):
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    warnings = []
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)

        def new_page(**kwargs):
            page = browser.new_page(**kwargs)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("console", lambda message: warnings.append(message.text) if "GL_INVALID" in message.text else None)
            return page

        for width in (320, 375, 768, 1024, 1440, 1920):
            page = new_page(viewport={"width": width, "height": 900 if width >= 768 else 812})
            for language in ("en", "fr"):
                response = page.goto(f"{base_url}/{language}/", wait_until="networkidle")
                assert response.status == 200
                ready(page)
                hero = page.locator(".hero")
                heading = page.locator("#hero-heading").bounding_box()
                assert heading["x"] >= 0 and heading["x"] + heading["width"] <= width
                assert heading["y"] + heading["height"] <= hero.bounding_box()["y"] + hero.bounding_box()["height"]
                page.screenshot(path=str(output / f"{language}-{width}.png"))
                checks.append(f"{language} {width}px: full-bleed canvas, photo pixels, text bounds")
            page.close()

        page = new_page(viewport={"width": 1440, "height": 900})
        page.add_init_script("""(() => {
            window.heroDrawCalls = 0;
            window.heroPointerListeners = 0;
            const addListener = EventTarget.prototype.addEventListener;
            EventTarget.prototype.addEventListener = function(type, ...args) {
                if (this instanceof Element && this.matches('[data-hero-depth]') && type.startsWith('pointer')) window.heroPointerListeners++;
                return addListener.call(this, type, ...args);
            };
            for (const method of ['drawElements', 'drawArrays']) {
                const original = WebGL2RenderingContext.prototype[method];
                WebGL2RenderingContext.prototype[method] = function(...args) {
                    window.heroDrawCalls++;
                    return original.apply(this, args);
                };
            }
        })();""")
        page.goto(f"{base_url}/en/", wait_until="networkidle")
        ready(page)
        canvas = page.locator(".hero-depth-canvas")
        before = pixels(canvas.screenshot())
        heading = page.locator("#hero-heading").bounding_box()
        page.wait_for_timeout(2500)
        after = pixels(canvas.screenshot())
        difference = sum(ImageStat.Stat(ImageChops.difference(before, after)).mean) / 3
        assert difference > 0.5, ("Automatic animation did not change the photo", difference)
        assert page.evaluate("window.heroPointerListeners") == 0, "Hero still follows the pointer"
        assert page.locator("#hero-heading").bounding_box() == heading, "Copy moves with the camera"
        check_photo(canvas.screenshot())
        page.screenshot(path=str(output / "desktop-animation.png"))
        calls = page.evaluate("window.heroDrawCalls")
        page.wait_for_timeout(500)
        rendered = page.evaluate("window.heroDrawCalls") - calls
        assert 1 <= rendered <= 24, ("Animation is not active or exceeds its frame-rate limit", rendered)
        page.evaluate("scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        calls = page.evaluate("window.heroDrawCalls")
        page.wait_for_timeout(400)
        assert page.evaluate("window.heroDrawCalls") == calls, "Offscreen canvas keeps drawing"
        page.evaluate("scrollTo(0, 0)")
        ready(page)
        checks.append("Automatic drift with fixed copy and no pointer tracking; frame rate capped, offscreen rendering paused")

        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: true}); document.dispatchEvent(new Event('visibilitychange'))")
        calls = page.evaluate("window.heroDrawCalls")
        page.wait_for_timeout(400)
        assert page.evaluate("window.heroDrawCalls") == calls, "Hidden-tab canvas keeps drawing"
        page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: false}); document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(500)
        assert page.evaluate("window.heroDrawCalls") > calls
        checks.append("Animation pauses in a hidden tab and resumes when visible")

        page.emulate_media(reduced_motion="reduce")
        page.wait_for_function("!document.querySelector('.hero-depth-canvas')")
        still_photo(page)
        page.emulate_media(reduced_motion="no-preference")
        ready(page)
        checks.append("Live reduced-motion change restores the still photo and can resume")

        page.evaluate("""() => {
            window.heroContext = document.querySelector('canvas').getContext('webgl2').getExtension('WEBGL_lose_context');
            window.heroContext.loseContext();
        }""")
        page.wait_for_function("document.querySelector('.hero').dataset.depthState === 'fallback'")
        still_photo(page)
        page.evaluate("window.heroContext.restoreContext()")
        ready(page)
        checks.append("GPU context loss shows the still photo; context restoration redraws")
        page.close()

        page = new_page(viewport={"width": 375, "height": 812}, device_scale_factor=2, is_mobile=True, has_touch=True)
        page.goto(f"{base_url}/en/", wait_until="networkidle")
        ready(page)
        assert page.locator("canvas").evaluate("canvas => Math.abs(canvas.width - canvas.getBoundingClientRect().width * devicePixelRatio) <= 1"), "Retina canvas is undersampled"
        before = pixels(page.locator("canvas").screenshot())
        page.wait_for_timeout(2000)
        after = pixels(page.locator("canvas").screenshot())
        assert sum(ImageStat.Stat(ImageChops.difference(before, after)).mean) / 3 > 0.3
        page.evaluate("scrollTo(0, 90)")
        page.wait_for_timeout(500)
        assert page.evaluate("scrollY") == 90
        check_photo(page.locator("canvas").screenshot())
        page.screenshot(path=str(output / "mobile-retina-scroll.png"))
        page.evaluate("scrollTo(0, 0)")
        page.set_viewport_size({"width": 1024, "height": 900})
        ready(page)
        page.set_viewport_size({"width": 375, "height": 812})
        ready(page)
        checks.append("Retina touch viewport animates automatically, scrolls normally, and survives resizing")
        page.close()

        for mode in ("reduced-motion", "no-javascript", "no-webgl", "module-failure", "save-data", "texture-failure"):
            options = {"viewport": {"width": 375, "height": 812}}
            if mode == "reduced-motion":
                options["reduced_motion"] = "reduce"
            if mode == "no-javascript":
                options["java_script_enabled"] = False
            page = new_page(**options)
            if mode == "no-webgl":
                page.add_init_script("""(() => {
                    const original = HTMLCanvasElement.prototype.getContext;
                    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                        return type === 'webgl2' ? null : original.call(this, type, ...args);
                    };
                })();""")
            if mode == "save-data":
                page.add_init_script("Object.defineProperty(navigator, 'connection', {value: {saveData: true}})")
            if mode == "module-failure":
                page.route("**/vendor/three/**", lambda route: route.abort())
            if mode == "texture-failure":
                page.add_init_script("""(() => {
                    const original = document.createElementNS.bind(document);
                    document.createElementNS = function(namespace, tag, ...args) {
                        const element = original(namespace, tag, ...args);
                        if (tag === 'img') Object.defineProperty(element, 'src', {set() {
                            queueMicrotask(() => element.dispatchEvent(new Event('error')));
                        }});
                        return element;
                    };
                })();""")
            page.goto(f"{base_url}/en/", wait_until="networkidle")
            page.wait_for_timeout(500)
            still_photo(page)
            assert not page.locator(".hero-depth-canvas").count()
            if mode in ("reduced-motion", "no-javascript", "save-data"):
                assert not page.evaluate("performance.getEntriesByType('resource').some(entry => entry.name.includes('/vendor/three/'))")
            page.screenshot(path=str(output / f"fallback-{mode}.png"))
            checks.append(f"Still-photo fallback: {mode}")
            page.close()
        browser.close()
    assert not errors, errors
    assert not warnings, warnings
    print(json.dumps({"checks_passed": len(checks), "checks": checks, "javascript_errors": errors,
                      "gpu_errors": warnings, "screenshots": str(output)}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/hero-depth"))
    args = parser.parse_args()
    verify(args.url.rstrip("/"), args.output)
