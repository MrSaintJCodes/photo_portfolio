"""Focused lifecycle and flash checks; no valid inquiry is submitted."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from verify_signature_services import FLASH, PENDING, TRACK, nav, settled


FLASH_TRACK = """
window.cameraFlashes = [];
document.addEventListener('animationstart', event => {
  if (event.animationName === 'pixel-camera-flash') {
    cameraFlashes.push({wall: Date.now(), stamp: Number(sessionStorage.getItem('mrsaintj.camera.flash.v1'))});
  }
});
"""
FREEZE = """
new MutationObserver(() => {
  const camera = document.querySelector('[data-pixel-camera].is-playing');
  if (camera) document.querySelectorAll('[data-pixel-camera], [data-pixel-camera-backdrop]').forEach(element => element.getAnimations({subtree: true}).forEach(animation => {
    animation.pause(); animation.currentTime = 80;
  }));
}).observe(document, {subtree: true, attributes: true, attributeFilter: ['class']});
"""


def advance(page, milliseconds):
    page.evaluate(
        "time => document.querySelectorAll('[data-pixel-camera], [data-pixel-camera-backdrop]').forEach(element => element.getAnimations({subtree:true}).forEach(animation => animation.currentTime=time))",
        milliseconds,
    )
    page.evaluate("() => new Promise(requestAnimationFrame)")


def verify(base, output, disabled_base=None):
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)

        def isolated(setup="", width=1440):
            context = browser.new_context(viewport={"width": width, "height": 1000})
            context.add_init_script(TRACK)
            context.add_init_script(FLASH_TRACK)
            if setup:
                context.add_init_script(setup)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            return context, page

        controller = browser.new_context()
        source = controller.request.get(f"{base}/static/js/pixel-camera.js").text()
        controller.close()

        context, page = isolated()
        page.goto(f"{base}/en/services/", wait_until="networkidle")
        settled(page, 0)
        assert page.evaluate("cameraFlashes.length") == 0
        checks.append("direct-entry-no-flash")
        page.evaluate("key => sessionStorage.setItem(key, JSON.stringify({destination:location.pathname,createdAt:Date.now()}))", PENDING)
        for _ in range(3):
            page.evaluate(source)
        assert page.evaluate(f"sessionStorage.getItem('{PENDING}')") is not None
        assert page.evaluate('cameraRuns.length') == 0
        assert page.locator('[data-pixel-camera]').is_hidden()
        checks.append("reinitialization-does-not-consume-or-play")
        page.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
        settled(page, 0)
        checks.append("cached-restoration-discards-pending")

        writes = []
        context.expose_binding("cameraWrite", lambda source, key: writes.append(key))
        page.evaluate("""() => {
          const set = Storage.prototype.setItem;
          Storage.prototype.setItem = function(key, value) {
            if (key.startsWith('mrsaintj.camera.')) window.cameraWrite(key);
            return set.call(this, key, value);
          };
        }""")
        nav(page, '.site-nav a[href="/en/about/"]')
        settled(page, 1)
        assert writes.count(PENDING) == 1, writes
        flashes = page.evaluate("cameraFlashes")
        assert len(flashes) == 1 and abs(flashes[0]["wall"] - flashes[0]["stamp"]) < 50, flashes
        checks.append("reinitialization-single-listener-and-actual-flash-stamp")
        page.evaluate("sessionStorage.clear()")
        page.evaluate("window.addEventListener('click', event => event.preventDefault(), {once:true})")
        page.locator('.site-nav a[href="/en/services/"]').click()
        assert page.url.endswith("/en/about/")
        assert page.evaluate(f"sessionStorage.getItem('{PENDING}')") is None
        checks.append("late-window-cancellation-no-pending")
        context.close()

        for width in (375, 1440):
            context, page = isolated(FREEZE, width)
            page.goto(f"{base}/en/about/", wait_until="networkidle")
            page.evaluate("sessionStorage.clear()")
            nav(page, '.site-nav a[href="/en/services/"]')
            camera = page.locator('[data-pixel-camera]')
            assert camera.is_visible()
            assert page.evaluate(f"Number(sessionStorage.getItem('{FLASH}'))") == 0
            assert camera.locator('.pixel-camera-burst').evaluate("element => getComputedStyle(element).opacity") == "0"
            assert camera.locator('.pixel-camera-shutter').evaluate("element => new DOMMatrixReadOnly(getComputedStyle(element).transform).m42") == 1
            advance(page, 165)
            page.wait_for_function("cameraFlashes.length === 1")
            assert camera.locator('.pixel-camera-burst').evaluate("element => getComputedStyle(element).opacity") == "1"
            assert camera.locator('svg').get_attribute('viewBox') == '0 0 48 32'
            assert camera.locator('svg').evaluate("element => getComputedStyle(element).shapeRendering") == 'crispedges'
            assert camera.evaluate("element => getComputedStyle(element).pointerEvents") == 'none'
            assert camera.get_attribute('aria-hidden') == 'true'
            assert camera.evaluate("element => {const r=element.getBoundingClientRect();return Math.abs(r.left+r.width/2-innerWidth/2)<1 && Math.abs(r.top+r.height/2-innerHeight/2)<1;}")
            backdrop = page.locator('[data-pixel-camera-backdrop]')
            assert backdrop.evaluate("element => getComputedStyle(element).backdropFilter") == 'blur(2px)'
            assert backdrop.evaluate("element => getComputedStyle(element).opacity") == '1'
            assert backdrop.evaluate("element => getComputedStyle(element).pointerEvents") == 'none'
            assert backdrop.bounding_box() == {'x':0, 'y':0, 'width':width, 'height':1000}
            advance(page, 240)
            opacity = float(camera.locator('.pixel-camera-burst').evaluate("element => getComputedStyle(element).opacity"))
            assert 0 < opacity < 1, (opacity, camera.is_hidden())
            assert camera.locator('.pixel-camera-shutter').evaluate("element => new DOMMatrixReadOnly(getComputedStyle(element).transform).m42") == 0
            advance(page, 165)
            camera.screenshot(path=str(output / f'camera-{width}.png'))
            settled(page, 1, fallback=True)
            assert page.evaluate("cameraFlashes.length") == 1
            checks.append(f"phases-pixels-actual-flash-and-fallback-{width}")
            context.close()

        context, page = isolated(FREEZE)
        page.goto(f"{base}/en/about/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        nav(page, '.site-nav a[href="/en/services/"]')
        page.evaluate("window.dispatchEvent(new Event('resize'))")
        assert page.locator('[data-pixel-camera]').is_hidden()
        assert page.evaluate(f"Number(sessionStorage.getItem('{FLASH}'))") == 0
        assert page.evaluate('cameraFlashes.length') == 0
        nav(page, '.site-nav a[href="/en/about/"]')
        advance(page, 165)
        page.wait_for_function('cameraFlashes.length === 1')
        checks.append('cancel-before-burst-does-not-reserve-cooldown')
        context.close()

        context, page = isolated(FREEZE)
        page.goto(f"{base}/en/about/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        nav(page, '.site-nav a[href="/en/services/"]')
        page.evaluate("""() => {
          Object.defineProperty(document, 'hidden', {configurable:true,get:()=>true});
          document.dispatchEvent(new Event('visibilitychange'));
        }""")
        assert page.locator('[data-pixel-camera]').is_hidden()
        page.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
        assert page.locator('[data-pixel-camera]').is_hidden()
        assert page.evaluate('cameraFlashes.length') == 0
        checks.append('hidden-tab-cancellation-no-return-replay')
        context.close()

        context, page = isolated(FREEZE)
        page.goto(f"{base}/en/about/", wait_until="networkidle")
        page.evaluate('sessionStorage.clear()')
        nav(page, '.site-nav a[href="/en/services/"]')
        page.evaluate("""() => {
          const dialog = document.createElement('dialog');
          dialog.textContent = 'Contact'; document.body.append(dialog); dialog.showModal();
        }""")
        page.wait_for_function("document.querySelector('[data-pixel-camera]').hidden")
        assert page.evaluate('cameraFlashes.length') == 0
        assert page.locator('[data-pixel-camera-backdrop]').is_hidden()
        checks.append('late-opened-dialog-cancels-camera-and-blur')
        context.close()

        for interaction in ('pointer', 'keyboard'):
            context, page = isolated(FREEZE)
            page.goto(f"{base}/en/about/", wait_until="networkidle")
            page.evaluate('sessionStorage.clear()')
            nav(page, '.site-nav a[href="/en/services/"]')
            page.evaluate("""() => {
              window.controlClicks = 0;
              const button = document.createElement('button');
              button.id = 'under-camera-control'; button.textContent = 'Contact';
              button.style = 'position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:160px;height:80px;z-index:1';
              button.addEventListener('click', () => controlClicks++);
              document.body.append(button);
            }""")
            assert page.locator('[data-pixel-camera-backdrop]').is_visible()
            assert page.evaluate('document.elementFromPoint(innerWidth/2,innerHeight/2).id') == 'under-camera-control'
            control = page.locator('#under-camera-control')
            if interaction == 'pointer':
                control.click()
            else:
                control.focus()
                assert page.locator('[data-pixel-camera-backdrop]').is_hidden()
                page.keyboard.press('Enter')
            assert page.evaluate('controlClicks') == 1
            assert page.evaluate('document.activeElement.id') == 'under-camera-control'
            assert page.locator('[data-pixel-camera]').is_hidden()
            assert page.locator('[data-pixel-camera-backdrop]').is_hidden()
            checks.append(f'{interaction}-control-clears-blur-without-blocking')
            context.close()

        context, page = isolated()
        page.goto(f"{base}/en/work/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        page.evaluate("""() => {
          const anchor = document.createElement('a');
          anchor.href = '/en/work/?category=race-day';
          anchor.dataset.cameraTransition = ''; anchor.id = 'query-link';
          anchor.textContent = 'Filter'; document.body.prepend(anchor);
        }""")
        nav(page, '#query-link')
        settled(page, 0)
        assert 'category=race-day' in page.url
        checks.append('marked-query-only-gallery-navigation-no-effect')
        context.close()

        context, page = isolated("""
          const set = Storage.prototype.setItem;
          Storage.prototype.setItem = function(key, value) {
            if (key === 'mrsaintj.camera.flash.v1') throw new DOMException('Blocked');
            return set.call(this, key, value);
          };
        """)
        page.goto(f"{base}/en/about/", wait_until="networkidle")
        nav(page, '.site-nav a[href="/en/services/"]')
        settled(page, 0)
        checks.append('unwritable-cooldown-storage-skips-decoration')
        context.close()

        context, page = isolated()
        page.route('**/css/pixel-camera.css', lambda route: route.abort())
        page.goto(f"{base}/en/about/", wait_until="networkidle")
        nav(page, '.site-nav a[href="/en/services/"]')
        settled(page, 0)
        assert page.locator('main h1').is_visible()
        assert page.locator('[data-pixel-camera]').evaluate("element => element.hidden")
        checks.append('missing-stylesheet-keeps-camera-out-of-layout')
        context.close()

        context, page = isolated()
        held = []
        page.goto(f"{base}/en/services/", wait_until="networkidle")
        page.evaluate("sessionStorage.clear()")
        page.route('**/images/justin-st-laurent.jpg', lambda route: held.append(route))
        nav(page, '.site-nav a[href="/en/about/"]')
        page.wait_for_function('cameraFlashes.length === 1')
        assert page.evaluate('document.readyState') != 'complete'
        assert page.locator('main h1').is_visible()
        assert page.locator('.hero').count() == 0
        settled(page, 1)
        for route in held:
            route.continue_()
        checks.append('arrival-and-usable-content-before-images-and-load')
        context.close()

        for selector, destination, expected, height in (
            ('.site-nav .shortlist-link', 'shortlist', 1, 1000),
            ('.footer-links a[href="/en/privacy/"]', 'privacy', 1, 1000),
            ('.footer-links a[href="/en/privacy/"]', 'privacy', 1, 1100),
            ('.contact-invitation a', 'contact', 1, 900),
        ):
            context, page = isolated()
            page.set_viewport_size({'width':1440,'height':height})
            page.goto(f"{base}/en/about/", wait_until="networkidle")
            page.evaluate('sessionStorage.clear()')
            nav(page, selector)
            assert page.url.endswith(f'/en/{destination}/')
            settled(page, expected)
            checks.append(f'shared-link-{destination}-{height}')
            context.close()

        if disabled_base:
            context, page = isolated()
            for language in ('en', 'fr'):
                page.goto(f'{disabled_base}/{language}/about/', wait_until='networkidle')
                assert page.locator('[data-pixel-camera]').count() == 0
                assert page.locator('script[src*="pixel-camera"], link[href*="pixel-camera"]').count() == 0
                nav(page, f'.site-nav a[href="/{language}/services/"]')
                assert page.locator('.offering-card').count() == 6
                assert page.evaluate('cameraRuns.length') == 0
            checks.append('disable-flag-omits-artwork-and-assets-in-both-languages')
            context.close()
        browser.close()
    assert not errors, errors
    print(json.dumps({'checks': len(checks), 'passed': checks, 'javascript_errors': errors,
                      'disable_flag_checked': bool(disabled_base), 'screenshots': str(output)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--disabled-url')
    parser.add_argument('--output', type=Path, default=Path('artifacts/pixel-camera'))
    args = parser.parse_args()
    verify(args.url.rstrip('/'), args.output, args.disabled_url.rstrip('/') if args.disabled_url else None)
