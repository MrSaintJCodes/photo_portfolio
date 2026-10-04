# MrSaintJ Photography

A Django sports photography portfolio with the owner's Flickr photographs, a cinematic homepage, filtered work gallery, keyboard-accessible lightbox, editorial collections, bilingual service pages, About and Contact pages, photo shortlists, and Django admin. Public copy focuses on decisive moments, effort, and athlete emotion. Company credits remain hidden.

## Local setup

Python 3.13 is the production target; Python 3.14 is also supported by the pinned Django 5.2.17 release. The existing local environment uses 3.14.6.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_portfolio
python manage.py import_portfolio_photos --manifest content/seed_photos.json
python manage.py createsuperuser
python manage.py runserver
```

On Windows, create the environment with `py -3.13 -m venv .venv`, then activate with `.venv\Scripts\Activate.ps1`. Run the remaining commands using `python`.

Open http://127.0.0.1:8000/en/ or http://127.0.0.1:8000/fr/. Owner administration is at http://127.0.0.1:8000/admin/. SQLite and local media work without cloud or email credentials. Optional `.env` values are loaded automatically; `.env.example` documents the available variables. Do not set `DEBUG=False` locally without providing a secret and the intended HTTPS configuration.

The 24 public images from the approved Flickr album plus the owner's additional group portrait (`54645194272`) are included in the import manifest, with original-size URLs and dimensions checked on October 3, 2026. Their existing original files are bundled in `content/photos/` (about 119 MiB) so Docker/Railway startup imports the whole collection without contacting Flickr. The manual importer can use the same files with `--source-dir content/photos`; without that option it requests original Flickr files, up to 6048 pixels on the long edge, before trying the larger preview and small-preview fallbacks. A fallback emits a warning so quality limitations are visible. Repeat imports add missing photographs without replacing existing files or edits. The original homepage selection is retained; the additional photographs appear in Work, across two pages. Failed imports are recorded on the photo and can be resumed by rerunning the command. Nothing is fetched from Flickr during public page requests. Future album additions require updating the manifest and bundling the corresponding original file.

## Managing content

Use **Site settings** to edit the biography, approach, contact introduction, localized hero copy, social links, optional public email/CV, and hero focal points. The wordmark is the fixed MrSaintJ identity. Instagram and LinkedIn use the owner's supplied profile URLs.

The About page uses the owner's supplied portrait, bundled at `static/images/justin-st-laurent.jpg`, with translated alt text and its original proportions. It deploys with static assets and is separate from the Work collection.

Upload a photograph as a **draft** first. Processing generates public JPEG/WebP copies, reports errors, and provides a preview. Then add English/French alt text, categories, focal points, and ordering, and publish it. Replacing a source file regenerates its renditions. Originals remain in private storage and can only be downloaded through the staff route.

Public images use quality-95 JPEG (4:4:4 chroma, progressive) and quality-95 WebP. Responsive renditions include 3840/5120px where the source supports them, plus its exact native dimensions without the former 2560px ceiling. The full-size viewer always receives the native-resolution JPEG; galleries, collections, services, and photo-detail pages choose a sharp rendition for their display size and pixel density. Sharing previews remain separate from full-size viewing. Public derivatives are normalized to sRGB with private metadata removed. Camera JPEGs with MPO auxiliary pictures are supported; only their primary photo is rendered. The `-v3` filename version prevents older compressed copies from being reused from browser/CDN caches.

The work gallery preserves natural proportions. Category entrances use editable covers and focal points. Drafts and failed images are excluded from gallery pages, lightbox data, hero selections, stories, and sitemaps. Unpublishing a story's cover hides that story until it has a valid cover. Empty categories are hidden from filter links.

Stories can be honest thematic **collections** or verified **event stories**. Set a ready cover, edit the introduction, and order photographs in the inline. Add event dates, location, or assignment descriptions only when verified. The starter collections are Race day, In the game, and The people.

Stories is omitted from the main navigation and homepage. Existing collections remain editable in admin, and their direct URLs still work.

**Service pages** have a stable key, separate English/French slugs and copy, coverage topics, SEO overrides, ordered photo/story inlines, and optional visible FAQs. The three starter pages cover sports in Montréal, race/endurance events, and team sports. They use the verified South Shore context, not invented commissions or pricing. A missing translation is omitted from that language's index and alternates; the language switch leads to the other Services index. Changing a published service or story slug creates a direct permanent redirect to the current record. Draft or deleted destinations do not redirect publicly.

The Services index now covers six **Service offerings**: individual athlete portraits, team/group photos, game-day action/training, races/endurance, tournaments/events, and fitness/promotion. Edit both languages, photographs, inquiry labels, order, and publication status in admin. These are index records, not six additional SEO pages; they link to the three existing detail pages where useful. The team card uses the owner's approved 5823 x 3639 group portrait (`54645194272`), with the full photograph contained in its frame rather than cropping additional people. An unavailable or cleared cover becomes text-led without exposing draft images. Site settings controls the localized index heading/introduction and optional cover; otherwise the published "Through the ropes" photograph (`54689682884`, native 5999 x 3749) is used. The Services banner is independent of the homepage hero and offering-card covers. The introduction establishes Longueuil and the South Shore without inventing travel, pricing, or delivery commitments. HTML, Service JSON-LD, and the Markdown mirror use the same published copy.

Optional **Behind the frame** fields on photos and stories start empty. Add your own localized notes when ready; empty notes produce no disclosure. Text is escaped, not treated as trusted HTML. Admin checks highlight incomplete translations, missing alt text, unavailable published covers/renditions, missing service metadata overrides, and invalid public origins.

Useful commands:

```bash
python manage.py seed_portfolio
python manage.py import_portfolio_photos
python manage.py seed_services
python manage.py import_portfolio_photos --flickr-id 54645194272
python manage.py seed_services --set-cover team-photos
python manage.py import_portfolio_photos --replace-files
python manage.py import_portfolio_photos --flickr-id 53984262444 --replace-files
python manage.py import_portfolio_photos --set-hero
python manage.py rebuild_renditions
python manage.py rebuild_renditions --photo PHOTO_UUID
python manage.py retry_inquiry_notifications
```

Seeding and repeat imports preserve subsequent owner edits and the current hero. `--replace-files` replaces source images intentionally, including upgrading earlier 1024px previews to the larger versions now recorded in the manifest; it does not reset copy or publication decisions. Use `--flickr-id` to limit a replacement to one approved photograph without redownloading the rest of Work.

`seed_services --set-cover OFFERING_KEY` explicitly selects that offering's approved manifest photograph, leaving its copy, publication status, and all other offerings unchanged. Ordinary seeding does not replace or fill existing owner-managed covers. Import the photograph first; an unavailable photo is rejected instead of clearing the current cover.

The photo importer runs `seed_services` after importing photos. When upgrading an existing populated installation, run `python manage.py migrate` followed by `python manage.py seed_services` to add the six offerings without replacing owner edits. On a new installation, import photographs before seeding services so appropriate covers are available. Optional company-credit records are seeded inactive and never used as identity links. Leave them inactive to retain the owner's approved no-company-credit presentation.

## Hero depth

The swimming hero now uses Flickr's 4957 x 3098 original source. Responsive JPEG/WebP renditions include the native size, and mobile cover sizing accounts for the portrait crop. Original files remain private. This uses real image detail, without generative changes to the athlete or water.

The homepage progressively enhances its ordinary `<picture>` with a full-bleed Three.js depth mesh. The background drifts automatically in a gentle 24-second loop, independent of mouse movement or scrolling; the swimmer and foreground water have slightly more depth than the background. Text stays fixed. Owner-selected desktop/mobile focal points are retained, with a small overscan to cover the moving edges.

Three.js 0.186.1 is pinned and self-hosted under `static/vendor/three/` with its MIT license. It loads only on a homepage with a public hero and compatible WebGL2 support. Reduced-motion and save-data preferences skip the effect. JavaScript, module, texture, or GPU failures leave the original photograph visible; changing the motion preference or losing/restoring the GPU context is handled without a blank banner. Animation is capped at 30 frames per second and pauses offscreen or in a hidden tab. Device pixel ratio is supported up to 3 for sharp retina rendering.

## Pixel camera arrivals

`PIXEL_CAMERA_TRANSITIONS_ENABLED=True` enables a small original pixel camera after opted-in public link navigation. Setting it to `False` omits the artwork, backdrop, stylesheet, and controller. Artwork uses integer rectangles on a 48 x 32 SVG grid, displayed at 96 x 64px on desktop and 48 x 32px on phones. The camera sits in the center of the viewport above a brief, subtle 2px background blur. Both elements are fixed and reserve no layout space; the camera itself stays sharp.

The sequence lasts 360ms: a four-pixel rise, one-grid-pixel shutter/lens press, a single local cream burst at 140ms, and a fade from 280ms. Cleanup occurs on animation end, with a 600ms fallback. The burst remains within 32 rendered pixels of its flash unit. The actual burst's animation-start event records its timestamp in tab-local storage; a one-second cooldown prevents repeated flashes, and cancellation before the burst does not reserve a future flash. There is no audio, loop, full-screen flash, image-loading wait, navigation interception, or native page blend. The local SVG/CSS/JS total is below 10KB before compression.

The controller records an eligible destination in session storage for at most 15 seconds, then consumes it once on arrival without waiting for images, fonts, or `load`. A per-document initialization guard prevents duplicate listeners. Storage bookkeeping runs after click dispatch (or on `pagehide` for fast navigation), so even a later click handler can cancel without leaving a pending record. Links retain immediate, ordinary full-document navigation and history. Direct entry, reload/history, same-path query changes, fragments, gallery filters, lightbox actions, forms, external/download links, non-default targets, and modified clicks do not trigger it. Cached `pageshow` restorations reset the artwork and discard pending state instead of playing a sequence, consistent with the [page lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/Window/pageshow_event). Malformed or unavailable storage simply omits the decoration. Reduced motion disables both the camera and background blur in CSS and JavaScript; changing that preference cancels a running sequence. Hidden tabs, resizing, scrolling, keyboard focus, or open menus/dialogs suppress or cancel it. Clicking or focusing page controls restores the sharp background immediately without blocking their normal behavior.

The camera and blur are decorative, hidden without JavaScript, unfocusable, and pointer-transparent. The blur fades in and out within the same 360ms sequence, and every reset hides both elements. Photographs retain their original sharpness and resolution after the effect. A missing camera stylesheet skips the effect without bringing its artwork into normal page layout. Flash size, single-burst behavior, and cooldown were reviewed against [W3C flash guidance](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html); this is not a claim of a full accessibility audit. No background tint, full-screen flash, input capture, or scroll lock is introduced.

## Saved photographs

Visitors can bookmark up to 12 photos from Work, the lightbox, or a photo-detail page. The localized `/en/shortlist/` and `/fr/shortlist/` pages show removable thumbnails and an inquiry action. Only stable UUIDs are kept in browser local storage; there are no visitor accounts. A same-origin, non-cacheable endpoint resolves current public photographs. Corrupt or blocked storage and photos that become unpublished do not prevent gallery browsing or ordinary contact submissions. With JavaScript disabled, photo links and the contact form remain usable.

Contact submits the selected identifiers, not image URLs. The server rejects malformed/non-list/excess selections, deduplicates valid UUIDs, and ignores unknown, unpublished, or unready photos. Accepted associations are saved with the inquiry before attempting email delivery, shown read-only with protected thumbnails in admin, and included as public photo-detail links in owner notifications. Duplicate submissions preserve the first inquiry's selection. Unpublishing later retains the private admin association but excludes its public link from notification retries. Shortlist state is not indexed or included in sitemaps.

## Contact and Resend

Valid inquiries are saved before notification. The form uses CSRF protection, a quiet honeypot, session-bound signed submission identifiers, and a database-backed rate limit shared across application workers. A repeated submission saves one inquiry. The public success message confirms receipt without claiming that email was delivered.

Each Services card links to Contact with a stable `service` key. The optional selector uses the same six keys in English and French, accepts only an allowlist, stays editable, and preserves the selection after errors. Unknown query values are ignored; invalid submitted values are rejected. The selected key is saved before notification and displayed with its translated label in admin and the owner's email, including retries. Broad inquiry links leave the selection unspecified. Older assignment values remain preserved on existing inquiries.

Set these variables to enable Resend:

```dotenv
RESEND_API_KEY=your-resend-key
CONTACT_FROM_EMAIL=an-address-on-your-verified-domain
CONTACT_TO_EMAIL=your-inquiry-recipient
```

The sender and recipient must be valid email addresses. The visitor's address becomes Reply-To. Resend is integrated through a Django email backend, with an idempotency key per saved inquiry. SMTP can alternatively be selected with `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` and standard email variables.

Without a sender/recipient, inquiries remain pending in admin. Delivery failures are retained as failed notifications and can be retried using the admin action or the command above. Locally, the default backend prints to the console when addresses are configured. Configure Resend explicitly in production; a console backend does not deliver email.

Rate limits use the direct peer address by default. Only populate `TRUSTED_PROXY_CIDRS` with your deployment's actual trusted proxy networks; forwarded addresses from other peers are ignored. The default limit is five valid new inquiries per peer per one-hour fixed window. Database storage avoids per-worker limits. No marketing signup or analytics is enabled.

## Languages and assets

Pages use `/en/` and `/fr/`; `/` redirects to English. The language switch preserves the equivalent route and gallery filter. Editable content uses explicit English/French fields with English fallback. Admin flags missing French photo/story translations.

Interface translations live in `locale/fr/LC_MESSAGES/django.po`; the compiled catalog is included. After changing interface strings, install GNU gettext and run:

```bash
python manage.py makemessages -l fr --ignore=.venv --ignore=media --ignore=private_media --ignore=staticfiles --ignore=artifacts
python manage.py compilemessages --ignore=.venv
```

The site self-hosts Barlow Condensed and Inter with SIL Open Font License notices in `static/fonts/`. Lucide icons and their license are in `static/icons/`. Photo source metadata is in `content/seed_photos.json`; localized detail-page copy is in `content/services.json` and index-offering copy is in `content/offerings.json`.

Pillow checks format, file size (40 MiB by default), and dimensions (60 megapixels). It applies EXIF orientation, converts valid embedded colour profiles to sRGB, and strips EXIF/GPS metadata from public renditions. Invalid profiles fall back to decoded RGB values and log a warning. Renditions have descriptive scene names, stable identifiers, source-digest versioning, and actual encoded widths. Sources smaller than a target size are never upscaled. Rebuilding identical renditions does not change the photo's modification timestamp. Limits are configurable with `PHOTO_MAX_BYTES` and `PHOTO_MAX_PIXELS`.

## Discovery and launch

Set `PUBLIC_SITE_URL` to one preferred HTTPS origin without a path, credentials, query, or fragment. All absolute canonicals, available language alternates, social metadata, image identities, sitemap entries, Markdown links, and notification links use this origin, never an arbitrary request Host header. Without a valid origin, development uses `http://127.0.0.1:8000` deterministically. Django checks reject enabling indexing with an invalid/non-HTTPS origin. HTML routes use trailing slashes. When indexing is enabled, public GET/HEAD requests to another allowed host permanently redirect to the preferred origin, preserving the path/query. Health, admin, and media routes are excluded from that host redirect; production HTTPS enforcement still applies.

Leave `INDEXING_ENABLED=False` locally and on staging: responses send `X-Robots-Tag: noindex, nofollow` and robots.txt disallows crawling. Noindex/robots are not access control; use actual authentication for private staging. Set `INDEXING_ENABLED=True` only on the real public deployment after content, canonical host, and storage checks. Gallery filter variants remain shareable but canonicalize to the unfiltered gallery and are noindex. Unfiltered pagination has distinct canonical page URLs. Shortlists and Markdown mirrors are not included in `/sitemap.xml`.

The generated XML sitemap includes current indexable localized pages, safe public image renditions, and stored content modification times. It is regenerated from database content, not from request time. Incomplete photo/story translations are omitted from alternates and the sitemap; their fallback HTML is noindex. The sitemap and text mirrors use content-derived ETags and revalidation rather than stale long-lived caches. Publishing, editing, and unpublishing affect generated output immediately. Originals are never listed.

JSON-LD describes the actual photographer (`Person`), `WebSite`, public page/service, relevant `ImageObject` records with encoded dimensions and credit, and breadcrumbs. `sameAs` contains only Justin's own supplied profiles. No storefront address, `LocalBusiness`, licensing promises, invented testimonials, employer identities, or invisible FAQ content is generated. Structured data explains visible content; it is not a promise of search features or rankings.

With `LLMS_TXT_ENABLED=True`, `/llms.txt` provides a small, UTF-8, database-derived guide to localized public Markdown mirrors. Mirrors use `/en/about/index.md`, `/fr/contact/index.md`, and equivalent services/story routes. They contain public copy and links, never forms, session/CSRF tokens, inquiry records, or source URLs. HTML links to its Markdown alternate; mirrors send a canonical Link header to HTML and `noindex, follow`. Turning the flag off removes these routes and alternate/footer links. No network call occurs while rendering. [llms.txt is a proposal](https://llmstxt.org/), not access control, a training-preference mechanism, or an indexing/ranking guarantee. Google's [AI-feature guidance](https://developers.google.com/search/docs/appearance/ai-features) does not require special AI text files.

Owner launch steps:

1. Review service copy, translations, captions, public photos, and the real preferred domain. Enable indexing only on production and check `/robots.txt`, `/sitemap.xml`, canonical links, and redirects there.
2. Verify the actual domain in [Google Search Console](https://search.google.com/search-console) and [Bing Webmaster Tools](https://www.bing.com/webmasters/). Prefer each provider's domain/DNS method, or set its actual `GOOGLE_SITE_VERIFICATION` or `BING_SITE_VERIFICATION` tag value. Defaults are empty. This application does not register or verify accounts for you.
3. Submit the production `/sitemap.xml`; inspect representative English/French service and photo-detail URLs, plus image discovery. Track relevant impressions/clicks and resulting inquiries using provider reports. Where an account offers AI/citation reports, treat those counts as observations, not conversion attribution or a universal AI ranking. No analytics or arbitrary referrer capture is enabled here.
4. Consider a service-area Business Profile only if the actual business qualifies under provider rules. Enter truthful availability and business information; do not invent a storefront or publish a home address just to populate markup. Account/profile changes remain owner actions.

Optional [IndexNow](https://www.indexnow.org/documentation) is disabled by default and does not contact a provider until explicitly invoked. On the real preferred domain, choose an 8-128 character alphanumeric/hyphen ownership key, set `INDEXNOW_KEY`, and enable `INDEXNOW_ENABLED=True` with `INDEXING_ENABLED=True`. The key is a public ownership token, not an email/API secret; its verification route is `/indexnow/KEY.txt`. Confirm that the route returns the exact key publicly, then review a dry run:

```bash
python manage.py notify_indexnow --dry-run
python manage.py notify_indexnow --url /en/services/sports-photography-montreal/
```

Omitting `--url` sends current public canonical URLs. External hosts, query variants, drafts, shortlists, and mirrors are rejected. Requests use a connection/read timeout and up to three attempts for transient failures. Tests mock all submissions. Acceptance is a notification to participating engines, not guaranteed indexing and not a Google-specific integration. Domain verification, IndexNow activation, and production ranking/performance measurements are not performed by local tests.

## Railway deployment

`railway.json` builds the included Dockerfile. The image targets Python 3.13, compiles translations, collects static assets, and starts Gunicorn. `scripts/start.sh` applies migrations and imports all 25 bundled photographs, site settings, categories, collections, and services before starting the server. The first startup generates full-quality JPEG/WebP renditions and can take several minutes; the Railway healthcheck allows up to 30 minutes for this initialization. Subsequent startups skip already imported files and preserve owner edits, publication decisions, and the current hero. Import failures stop startup and can be retried on the next deployment. The app automatically accepts Railway's healthcheck hostname. It does not create an admin password.

Create a Railway PostgreSQL service and provide its `DATABASE_URL` to the web service. Configure:

- `DEBUG=False` and a strong, unique `SECRET_KEY`.
- `ALLOWED_HOSTS` for any custom domain. Railway's provided `RAILWAY_PUBLIC_DOMAIN` is added automatically.
- `PUBLIC_SITE_URL=https://your-actual-domain` and `CSRF_TRUSTED_ORIGINS` for custom HTTPS domains. Enable `INDEXING_ENABLED=True` only when the real public installation is ready; staging remains disabled.
- The Resend settings above when ready.
- Durable media storage, using either option below.

For a simple single-instance setup, mount a Railway volume at `/data`, set `MEDIA_ROOT=/data/media` and `PRIVATE_MEDIA_ROOT=/data/private`, and leave `USE_S3=False`. The application serves only ready published renditions and the optional public CV through its media route. WhiteNoise serves static files, not uploads. A volume prevents images disappearing when the container is replaced.

For object storage, set `USE_S3=True`, S3 endpoint/region/credentials, `PUBLIC_MEDIA_BUCKET`, and `PRIVATE_MEDIA_BUCKET`. Use a public bucket/CDN for derivatives and a separate private bucket for sources. `PUBLIC_MEDIA_DOMAIN` is optional and accepts a hostname without a scheme. Keep the original bucket private through provider policy; its backend does not issue public or signed source URLs. This storage mode works across replicas.

After the first deployment, run `python manage.py createsuperuser` in the running service environment, with the same database/storage settings. The gallery is populated automatically. To retry the bundled import manually, run `python manage.py import_portfolio_photos --source-dir content/photos`. A manual import without `--source-dir` uses Flickr and needs no Flickr API key.

The `/healthz/` route returns minimal process health information. Secure cookies, HTTPS redirect, HSTS, and the deployment proxy header are configured for production. Only expose the application behind the trusted HTTPS reverse proxy. Back up the PostgreSQL database and both media stores; restoring one does not restore the others.

Unpublishing removes photos from public pages and from new application-served media requests. Files already in a browser/CDN cache may remain accessible until expiry; object-storage URLs require provider deletion/purge if immediate revocation is needed. Replaced source files and older rendition versions are retained for recovery and can be cleaned up under a deliberate retention policy.

## Docker development

```bash
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Compose imports the bundled collection on startup and persists PostgreSQL and public/private media in separate named volumes. The local Python setup remains the lightest way to develop templates/styles. Docker is not installed on the implementation machine, so the container build has not been executed here.

## Verification

```bash
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
python -m pip install -r requirements-dev.txt
python scripts/verify_browser.py
python scripts/verify_discovery.py
python scripts/verify_hero_depth.py
python scripts/verify_photo_quality.py
python scripts/verify_signature_services.py
python scripts/verify_pixel_camera.py
```

The browser script uses installed Google Chrome through Playwright. It inspects 60 page/locale/viewport combinations at 320, 375, 768, 1024, and 1440px, then traverses every additional Work page at each width and checks that all photographs are reachable without duplicates. It captures screenshots under ignored `artifacts/screenshots/`, checks image loading/overflow, and exercises lightbox focus on both gallery pages, arrow/Escape navigation, mobile menu, language/filter retention, validation, and no-JavaScript navigation. It does not submit a real inquiry or send an email.

`verify_discovery.py` checks 50 localized service/shortlist page and viewport combinations at the same widths. It also exercises saves in gallery/lightbox/photo detail, persistence into the Contact preview, keyboard focus after removal, clear, the 12-photo limit, corrupt/blocked browser storage, stale IDs, and service browsing without JavaScript. Screenshots are under `artifacts/discovery/`. It never submits a real inquiry.

`verify_hero_depth.py` checks actual canvas pixels and full-bleed framing at 320, 375, 768, 1024, 1440, and 1920px in both languages. It also verifies automatic motion without pointer tracking, fixed text, retina touch/resizing, frame-rate limits, offscreen/hidden-tab pauses, live reduced-motion changes, GPU context recovery, and still-photo fallbacks. Screenshots are under `artifacts/hero-depth/`.

`verify_photo_quality.py` checks all 25 imported photos against the original dimensions recorded in the manifest, native JPEG/WebP output, JPEG quality/chroma settings, metadata removal, and versioned URLs. It inspects both Work pages and native-size viewer images on desktop DPR 2 and mobile DPR 3. Screenshots and its report are under `artifacts/photo-quality/`. It explicitly records the current source limits: "Keep moving" is only 800 x 534 on Flickr, and the supplied About portrait is 959 x 960. Higher-resolution owner originals are needed to improve those two files.

Automated Django tests additionally cover localized services, slug redirects without loops, secure origin handling, publication boundaries across metadata/sitemaps/mirrors, safe JSON-LD, ETags, optional discovery switches, shortlist validation/associations/admin, and mocked IndexNow behavior. Email tests use mocks or the in-memory backend. Railway deployment, live Resend delivery, and real-user performance have not been measured by these local checks.

`verify_signature_services.py` checks all six localized offerings at five viewport widths, service-specific links and editable selections after invalid submissions, normal and keyboard arrival navigation, language/story links, timing/cleanup, rapid-navigation cooldown, history/reload, reduced motion, corrupt/blocked storage, no-JavaScript behavior, and crisp desktop/tablet/phone artwork. Screenshots are under `artifacts/signature-services/`. It never submits a valid inquiry or sends an email. Django tests cover admin edits, native image selection, publication/translation boundaries, mirrored metadata, migration-compatible legacy inquiries, selection persistence, translated notifications, retries, and the camera's disable setting.

`verify_pixel_camera.py` adds lifecycle regressions for repeated initialization, cached restorations, actual flash timestamps, pre-burst cancellation, query-only gallery links, hidden-tab cancellation, newly opened dialogs, write-blocked storage, a missing stylesheet, and usable content while an image is still loading. It checks centered positioning, a pointer-transparent fullscreen blur, shutter/burst/fade phases, and crisp 48px/96px artwork, including cleanup of both elements when test animations are paused. Use `--disabled-url` to also check a local instance started with `PIXEL_CAMERA_TRANSITIONS_ENABLED=False`. Screenshots are under `artifacts/pixel-camera/`.

Latest group-photo verification: 85 Django tests, 56 focused service/camera checks, and all 25 native-size photo audits plus six retina gallery/viewer/About checks passed. The team card displays the approved 5823 x 3639 photograph in both languages without an additional crop, and all prior photographs and hero settings were confirmed unchanged. Earlier broad verification also passed 65 general browser page/locale/viewport checks, 50 discovery/shortlist checks, and 23 hero checks. There were no JavaScript/GPU errors, missing images, or horizontal overflow. The original swimming photograph (`53984262444`) retains its 4957 x 3098 source and automatic motion; all Work photographs match their recorded original dimensions, up to 6048 pixels on the long edge. The supplied portrait remains unchanged. Six localized index offerings and three existing service-detail pages are populated, company credits remain inactive, and owner-written notes are untouched. The cached-arrival controller branch is additionally tested with persisted `pageshow` simulations; real browser Back/Forward navigation is checked separately.

Bundled deployment verification: 92 Django tests, production `check --deploy`, and migration consistency passed. A local `DEBUG=False` startup through `scripts/start.sh`, using an empty temporary SQLite database and filesystem storage, imported all 25 originals and generated 402 renditions in 468 seconds. English/French home, both Work pages, Services, and About returned successful responses; the hero JPEG retained its 4957 x 3098 dimensions. Railway's healthcheck hostname was accepted. Repeat initialization reused every image file in 0.9 seconds. The temporary server and storage were cleaned up. These timings are local measurements, not Railway performance results.

Production `check --deploy`, migration consistency, and static collection passed using a temporary test secret and example HTTPS origin, without activating a real indexing account or sending email. Six current `DEBUG=False` Gunicorn/WhiteNoise smoke checks verified localized Services, hashed local assets, camera arrivals, inquiry selection, and the disabled camera setting at desktop DPR 2 and mobile DPR 3. Earlier production smoke checks also verified the existing hero's nonblank pixels, automatic motion, and retina canvas. Temporary HTTP smoke servers were stopped; production HTTPS defaults remain enabled. Container execution, Railway deployment, production PostgreSQL/object storage, and live Resend delivery remain unverified locally.
