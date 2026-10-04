"""Prepare deployment image sizes using an isolated database and one worker per photo."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=repo / "content/seed_photos.json")
    parser.add_argument("--source-dir", type=Path, default=repo / "content/photos")
    parser.add_argument("--output-dir", type=Path, default=repo / "content/renditions")
    args = parser.parse_args()
    entries = json.loads(args.manifest.read_text())
    sys.path.insert(0, str(repo))
    with tempfile.TemporaryDirectory(prefix="portfolio-build-") as directory:
        root = Path(directory)
        # Build preparation never uses production credentials, databases, or volumes.
        os.environ.update(
            DJANGO_SETTINGS_MODULE="photo_portfolio.settings", DEBUG="True", USE_S3="False",
            DATABASE_URL=f"sqlite:///{root / 'build.sqlite3'}", RESEND_API_KEY="",
            MEDIA_ROOT=str(root / "public"), PRIVATE_MEDIA_ROOT=str(root / "private"),
        )
        import django
        django.setup()
        from django.core.management import call_command
        from portfolio.models import Photo

        call_command("migrate", interactive=False, verbosity=0)
        for entry in entries:
            result = subprocess.run(
                [sys.executable, str(repo / "manage.py"), "import_portfolio_photos",
                 "--manifest", str(args.manifest.resolve()), "--source-dir", str(args.source_dir.resolve()),
                 "--flickr-id", entry["id"]],
                cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            if result.returncode:
                raise RuntimeError(f"Could not prepare {entry['id']}:\n{result.stdout}")
            photo = Photo.objects.get(flickr_id=entry["id"])
            target = args.output_dir / entry["id"]
            target.mkdir(parents=True, exist_ok=True)
            with photo.source.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            bundle = {"source_sha256": digest, "width": photo.width, "height": photo.height, "renditions": []}
            for rendition in photo.renditions.all():
                filename = f"{rendition.width}.{rendition.format}"
                with rendition.file.open("rb") as source, (target / filename).open("wb") as output:
                    shutil.copyfileobj(source, output)
                bundle["renditions"].append({
                    "file": filename, "width": rendition.width, "height": rendition.height,
                    "format": rendition.format, "byte_size": rendition.byte_size,
                })
            (target / "manifest.json").write_text(json.dumps(bundle, indent=2) + "\n")
            print(f"Prepared: {entry['id']} ({photo.width} x {photo.height})", flush=True)


if __name__ == "__main__":
    main()
