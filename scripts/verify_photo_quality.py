"""Verify imported native sizes and public quality without exposing private originals."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photo_portfolio.settings")

import django
from PIL import Image
from PIL.JpegImagePlugin import get_sampling
from playwright.sync_api import sync_playwright

django.setup()

from portfolio.models import Photo
from portfolio.services.content import rendition_data


def verify(base_url, output):
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "content/seed_photos.json").read_text())
    expected = {}
    for entry in manifest:
        photo = Photo.objects.get(flickr_id=entry["id"])
        native = (entry["original_width"], entry["original_height"])
        assert photo.is_public, (entry["id"], photo.processing_status)
        assert (photo.width, photo.height) == native, (entry["id"], photo.width, photo.height, native)
        for fmt in ("jpeg", "webp"):
            largest = photo.renditions.filter(format=fmt).order_by("-width").first()
            assert (largest.width, largest.height) == native
            assert "-v3/" in largest.file.name
            with largest.file.open("rb") as file, Image.open(file) as image:
                assert image.size == native
                assert not image.getexif()
                if fmt == "jpeg":
                    assert get_sampling(image) == 0, "JPEG chroma detail is subsampled"
                    assert image.quantization[0][0] == 2, "JPEG quality is not 95"
        data = rendition_data(photo)
        assert f"{photo.width}w" in data["jpeg_srcset"]
        assert f"{photo.width}w" in data["webp_srcset"]
        full = photo.renditions.get(format="jpeg", width=photo.width)
        assert data["full"] == full.file.url
        expected[str(photo.identifier)] = {"flickr_id": entry["id"], "size": native, "url": full.file.url}

    errors = []
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for width, density in ((1440, 2), (375, 3)):
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=density)
            page.on("pageerror", lambda error: errors.append(str(error)))
            seen = set()
            for number in (1, 2):
                page.goto(f"{base_url}/en/work/?page={number}", wait_until="networkidle")
                photos = json.loads(page.locator("#lightbox-data").text_content())
                for photo in photos:
                    native = expected[photo["id"]]
                    assert photo["url"].endswith(native["url"])
                    seen.add(photo["id"])
                page.locator(".gallery-grid img").evaluate_all("images => images.forEach(image => image.loading = 'eager')")
                page.wait_for_function("Array.from(document.querySelectorAll('.gallery-grid img')).every(image => image.complete && image.naturalWidth > 0)")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / f"work-{number}-{width}-dpr{density}.png"))
                for index in (0, len(photos) - 1):
                    page.locator("[data-lightbox-index]").nth(index).click()
                    native = expected[photos[index]["id"]]
                    page.wait_for_function("size => {const image=document.querySelector('.lightbox-image'); return image.complete && image.naturalWidth === size[0] && image.naturalHeight === size[1];}", arg=list(native["size"]))
                    page.screenshot(path=str(output / f"viewer-{native['flickr_id']}-{width}.png"))
                    page.keyboard.press("Escape")
                checks.append(f"Work page {number} at {width}px/DPR {density}: all full-size URLs, real native viewer images")
            assert seen == set(expected), "Some portfolio photos are missing from Work"
            page.goto(f"{base_url}/en/about/", wait_until="networkidle")
            portrait = page.locator(".about-image img")
            assert portrait.evaluate("image => image.complete && image.naturalWidth === 959 && image.naturalHeight === 960")
            checks.append(f"About {width}px/DPR {density}: original supplied portrait retained")
            page.close()
        browser.close()
    assert not errors, errors
    report = {"native_photos_checked": len(expected), "largest_long_edge": max(max(item["size"]) for item in expected.values()),
              "public_formats": ["JPEG 95, 4:4:4", "WebP 95"], "browser_checks": checks,
              "javascript_errors": errors, "screenshots": str(output),
              "source_limits": ["Keep moving: 800 x 534 on Flickr", "About portrait: 959 x 960 supplied attachment"]}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, default=Path("artifacts/photo-quality"))
    args = parser.parse_args()
    verify(args.url.rstrip("/"), args.output)
