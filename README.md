# TravelPromoHub

An informational index of **public travel offers** from major providers — car rental,
hotels, cruises, flights, and activities. Every offer links straight to the provider's
own official deals page.

## What it is
- **Zero server, zero cost.** Static HTML built by pure Python, hosted free on
  Cloudflare Pages (`*.pages.dev`).
- **Self-updating.** A GitHub Actions cron re-scrapes the official offers pages and
  rebuilds every 6 hours.
- **Real data only.** No invented offers, prices, or commissions. If a price can't be
  confirmed from a provider's public page, it's shown as "terms on provider page" and the
  provider is flagged honestly (some sites block automated fetches or are JS-rendered).
- **I-Lang native.** The site's brand, tracked providers, language, currency, and update
  schedule are defined in `.ilang/site.ilang` — the single source of truth. Change that
  file and the site changes.

## How it works
```
.ilang/site.ilang   ->  sitecfg.py  ->  scraper.py  ->  data/offers.json
                                            |
                                            v
                                        build.py  ->  site/  ->  Cloudflare Pages
```
- `scraper.py` fetches each provider's official deals URL (respecting `robots.txt`),
  extracts current public offers, and writes `data/offers.json`.
- `build.py` renders `site/` with schema.org structured data (Product / AggregateOffer /
  Offer / ItemList / FAQPage), a `sitemap.xml`, and `robots.txt`.

## Run it yourself
```bash
python scraper.py     # refresh data/offers.json
python build.py       # regenerate site/
```
Open `site/index.html` locally to preview.

## Add or remove a provider
Edit the `::MODULE{PROVIDERS}` block in `.ilang/site.ilang`. Re-run the two commands
above. No code changes needed.

## Deploy
Push to GitHub, then connect the repo to Cloudflare Pages (or let the included
`.github/workflows/update.yml` deploy via `cloudflare/pages-action`). The workflow needs
two repo secrets: `CF_API_TOKEN` and `CF_ACCOUNT_ID`.

## Honest notes
- This is an **informational index**, not a booking site. Prices and terms are set by each
  provider — always confirm on the provider's official site before booking.
- Affiliate links are **off by default**: outbound links point to the provider's official
  deals page. To monetize later, fill the 4th column of `::MODULE{PROVIDERS}` with an
  affiliate URL; the builder will use it automatically.
- `pages.dev` subdomains accrue to Cloudflare, not to you. Register your own domain and
  point it at this Pages project when you're ready to own the asset. Exit cost is zero.

---
Site rules are described in the I-Lang protocol — see `.ilang/site.ilang`.
Protocol info: ilang.ai
