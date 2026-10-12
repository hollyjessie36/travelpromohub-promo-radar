# AGENTS.md — travelpromohub

::ILANG[PROJECT:travelpromohub]

This repo is an **I-Lang-native** static site. The single source of truth for what
the site is and tracks lives in `.ilang/site.ilang`. Both `scraper.py` and `build.py`
read that file — they contain **no hardcoded provider list or brand text**.

## What this project is
An informational index of **public travel offers** from major providers. Pure Python,
no server, no API keys, no LLM at runtime. Built once with the data we have; refreshed
on a schedule by GitHub Actions.

## Allowed actions (boundary)
- Read `.ilang/site.ilang` and change it to change the site.
- Add / remove / rename a provider by editing the `::MODULE{PROVIDERS}` block.
- Change brand name, locale, currency, cron, or render rules in `site.ilang`.
- Run `python scraper.py` then `python build.py` to regenerate `site/`.
- Deploy `site/` to Cloudflare Pages.

## Never (permanent boundary)
- **Never fabricate** an offer, a price, a discount, or a commission/affiliate link.
  If a price can't be verified from the provider's public page, leave it empty and
  mark the provider `no_offers_found` / `robots_disallowed` / with the HTTP error.
- Never bypass a site's `robots.txt` or anti-crawl controls.
- Never hardcode the provider list or brand strings into `.py` files — keep them in
  `site.ilang` so the config stays the single source of truth.

## Files
- `.ilang/site.ilang` — config (single source of truth).
- `sitecfg.py` — loads `site.ilang` into a Python dict.
- `scraper.py` — fetches each provider's official deals page, extracts real offers → `data/offers.json`.
- `build.py` — renders `site/` (HTML + JSON-LD + sitemap.xml + robots.txt).
- `templates/` — HTML skeletons with `[[VAR]]` placeholders (no template engine).
- `data/offers.json` — last scrape result (committed, refreshed by the workflow).
- `site/` — generated output (committed, deployed to Pages).
- `site/.ilang/site.ilang` — a copy of the config shipped with the build, used by the
  self-test that proves "changing `site.ilang` changes the site".

## Self-test (proves I-Lang is real, not decoration)
1. Edit `.ilang/site.ilang` (e.g. rename a provider or change `@BRAND display`).
2. Run `python build.py`.
3. The corresponding page in `site/` must change. If it doesn't, the pipeline is broken.

## Deploy
GitHub Actions builds and deploys `site/` to Cloudflare Pages (`cloudflare/pages-action`)
every 6h and on manual dispatch. Needs two repo secrets: `CF_API_TOKEN` and `CF_ACCOUNT_ID`.
Protocol reference: ilang.ai
