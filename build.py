# ::ILANG[TYPE:builder][PROJECT:travelpromohub]
# 职责：读 data/offers.json + .ilang/site.ilang，渲染静态站到 site/，生成 sitemap.xml / robots.txt / 404.html。
# 边界：模板占位符只做 [[VAR]] 替换；优惠/价格只在抓到真值时写，绝不编。
# 每条 deal / provider 页：第一屏直接回答“有没有优惠、怎么拿”，下面四列表
# （What's the offer / How to get it (conditions) / Official source page / Review date），并露出真实抓取时间。
# 全部可见文案英文（locale en-US）；品牌名保持 TravelPromoHub。
# 第二列只写官方页真有的条件；取不到就整行摘掉，绝不写免责句 / 以官方页为准。
# 配置里每一家厂商都建一页；抓不到优惠的厂商页照实写“Official page checked. No public offers currently available.”，不出现任何金额/折扣数字。
import os
import re
import json
import datetime
import html
import shutil
from xml.sax.saxutils import escape as xescape

import sitecfg

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
TPL = os.path.join(HERE, "templates")
OFFERS = os.path.join(HERE, "data", "offers.json")

# 复核日期 = 真实复核当天（构建那一刻的本地日期）
REVIEW_DATE = datetime.date.today().isoformat()

CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif;color:#1a2233;background:#f7f9fc;line-height:1.55}
.site{display:flex;align-items:center;gap:12px;padding:16px 22px;background:#0f2a4a;color:#fff}
.brand{font-weight:700;color:#fff;text-decoration:none;font-size:20px}
.tagline{opacity:.8;font-size:13px}
.crumbs{padding:12px 22px;font-size:13px;color:#5a6b85}
.crumbs a{color:#1463c8;text-decoration:none}
main{max-width:920px;margin:0 auto;padding:22px}
h1{font-size:26px;margin:6px 0 14px}
h2{font-size:20px;margin:24px 0 10px}
.firstscreen{background:#eaf3ff;border:1px solid #bcd8ff;border-radius:10px;padding:14px 16px;margin:14px 0;font-size:16px}
.firstscreen b{color:#0a4ea8}
.scraptime{font-size:13px;color:#5a6b85;margin:12px 0 4px}
a.card{display:block;padding:14px 16px;margin:10px 0;background:#fff;border:1px solid #e3e9f2;border-radius:10px;text-decoration:none;color:#1a2233}
a.card:hover{border-color:#1463c8}
a.card b{color:#1463c8}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
table.offers{border-collapse:collapse;width:100%;background:#fff;margin:12px 0;font-size:14px}
table.offers th,table.offers td{border:1px solid #e3e9f2;padding:9px 10px;text-align:left;vertical-align:top}
table.offers th{background:#0f2a4a;color:#fff}
table.offers td.official{font-style:italic;color:#33415c}
.go{display:inline-block;margin-top:8px;color:#1463c8;font-weight:600}
.small{font-size:12px;color:#7a8aa3}
footer.site{padding:18px 22px;color:#5a6b85;font-size:13px;border-top:1px solid #e3e9f2;margin-top:30px}
footer.site nav.footer-links{display:flex;flex-wrap:wrap;gap:18px;margin:0 0 12px}
footer.site nav.footer-links a{color:#1463c8;text-decoration:none;font-weight:600}
footer.site nav.footer-links a:hover{text-decoration:underline}
"""

ILANG_NOTE = ("Site rules are described in the I-Lang protocol &mdash; see "
             "<code>.ilang/site.ilang</code>. Protocol info: ilang.ai")

# 联系页邮箱：只有真的从外部发过一封测试信、确认转发进了收件箱，才允许写进页面。
# 没测过 = 绝不把地址写上去（不许先写个地址顶上）。
CONTACT_EMAIL = "contact@travelpromohub.com"
CONTACT_EMAIL_LIVE = False


def load_offers():
    if not os.path.exists(OFFERS):
        return {"fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "providers": []}
    return json.load(open(OFFERS, encoding="utf-8"))


def base_url(cfg):
    b = cfg.get("base_url") or ""
    if not b:
        b = "https://travelpromohub.com"
    return b.rstrip("/")


def render(template_name, **kw):
    t = open(os.path.join(TPL, template_name), encoding="utf-8").read()
    kw.setdefault("CSS", CSS)
    kw.setdefault("ILANG_NOTE", ILANG_NOTE)
    kw.setdefault("YEAR", str(datetime.datetime.now().year))
    kw.setdefault("LANG", "en")
    for k, v in kw.items():
        t = t.replace("[[" + k + "]]", str(v))
    return t


def esc(s):
    return html.escape(str(s or ""))


def fmt_scrape(fetched_at):
    try:
        dt = datetime.datetime.fromisoformat(fetched_at)
        if dt.tzinfo:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return fetched_at or "unknown"


# ---- 优惠展示逻辑（只基于真实抓取字段，绝不编） ----
def offer_what(o):
    # 优惠名只取真实名（厂商真名 + 方案真名），绝不裸金额
    if o.get("offer"):
        return o["offer"]
    if o.get("plan"):
        return o["plan"]
    return "Public offer"


def scrape_line(fetched_at):
    return (f'<p class="scraptime">Data scraped at: <b>{esc(fmt_scrape(fetched_at))}</b>'
            f' (Review date: {esc(REVIEW_DATE)})</p>')


def first_screen_offer(provider, what):
    return (f'Available. This {esc(provider)} public offer: <b>{esc(what)}</b>. '
            f'How to get it: open the official source page below and apply the offer '
            f'or promo code when booking. Conditions are listed in the table.')


def first_screen_provider_offers(provider, n):
    return (f'Available. {esc(provider)} currently lists {n} public offer(s), each checked '
            f'against its official page. How to get it: open the official source page below '
            f'and apply the offer or promo code when booking.')


def first_screen_no_offer():
    return ('Official page checked. No public offers with verifiable terms are '
            'available right now.')


def offers_table(offers, provider, burl=None, slug=None):
    rows = []
    for i, o in enumerate(offers):
        offer = o.get("offer")
        cond = o.get("condition")
        official = o.get("official")
        # 缺真实名 / 真条件 / 官方原话 / 未核到原话 → 整行摘掉，绝不编、绝不写核验状态
        if not (offer and cond and official and o.get("verify") == "verified"):
            continue
        src = o.get("source") or ""
        src_html = (f'<a href="{esc(src)}" rel="nofollow noopener" target="_blank">'
                    f'{esc(src)}</a>')
        # 品牌页里优惠名链到它自己的详情页，保证每个 deal 页都有入口（首页→品牌页→详情页）
        what_html = (f'<a href="{burl}/deals/{esc(slug)}_{i}">{esc(offer)}</a>'
                     if burl and slug else esc(offer))
        rows.append(f'<tr><td>{what_html}</td><td>{esc(cond)}</td>'
                    f'<td class="official">{esc(official)}</td>'
                    f'<td>{src_html}</td>'
                    f'<td>{esc(o.get("review_date") or REVIEW_DATE)}</td></tr>')
    return ('<table class="offers"><thead><tr>'
            '<th>What\'s the offer</th><th>How to get it (conditions)</th>'
            '<th>Official page text (verbatim)</th>'
            '<th>Official source page</th><th>Review date</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table>')


def write_provider_page(cfg, burl, prov, offers, fetched_at):
    slug = prov["slug"]
    fname = f"providers/{slug}.html"
    url = f"{burl}/providers/{slug}"   # Cloudflare Pages 用无扩展名 clean URL
    named = [o for o in offers if o.get("offer")]
    ld = {"@context": "https://schema.org", "@type": "Product",
          "name": prov["name"], "brand": {"@type": "Brand", "name": prov["name"]},
          "url": url}
    if named:
        # 只放真实名 + 来源，绝不编价格/金额
        ld["offers"] = [{"@type": "Offer", "name": o["offer"],
                         "url": o.get("source") or url,
                         "availability": "https://schema.org/InStock"} for o in named]
    jld = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    if offers:
        what = f"{len(offers)} public offer(s)"
        body = (f'<h1>{esc(prov["name"])} &mdash; Public travel offers</h1>'
                f'<div class="firstscreen">{first_screen_provider_offers(prov["name"], len(offers))}</div>'
                + offers_table(offers, prov["name"], burl, slug)
                + scrape_line(fetched_at))
    else:
        # 抓不到优惠 / 全部行被摘掉：照实写，不允许出现任何金额或折扣数字
        ourl = prov.get("deals") or prov.get("site") or ""
        body = (f'<h1>{esc(prov["name"])} &mdash; Public travel offers</h1>'
                f'<div class="firstscreen">{first_screen_no_offer()}</div>'
                f'<p>Official offers page: <a href="{esc(ourl)}" rel="nofollow noopener" '
                f'target="_blank">{esc(ourl)}</a></p>'
                + scrape_line(fetched_at))
    page = render("provider.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'{prov["name"]} travel offers | {cfg["display"]}',
                  DESC=f'{prov["name"]} public travel offers, with conditions and the official source.',
                  CANONICAL=url, BASE_URL=burl, OG_TITLE=prov["name"],
                  OG_DESC=f'{prov["name"]} public travel offers', JSONLD=jld,
                  CONTENT=body, PROVIDER_NAME=esc(prov["name"]),
                  PROVIDER_URL=prov["deals"], DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return fname, page, url


def write_deal_page(cfg, burl, slug, idx, o, prov, fetched_at):
    fname = f"deals/{slug}_{idx}.html"
    url = f"{burl}/deals/{slug}_{idx}"   # clean URL
    ld = {"@context": "https://schema.org", "@type": "Offer",
          "name": offer_what(o), "url": o.get("source") or prov["deals"]}
    ld["availability"] = "https://schema.org/InStock"
    jld = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    body = (f'<h1>{esc(offer_what(o))}</h1>'
            f'<div class="firstscreen">{first_screen_offer(prov["name"], offer_what(o))}</div>'
            + offers_table([o], prov["name"])
            + scrape_line(fetched_at))
    page = render("deal.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'{offer_what(o)} | {cfg["display"]}',
                  DESC=esc(offer_what(o)), CANONICAL=url, BASE_URL=burl,
                  OG_TITLE=esc(offer_what(o)), OG_DESC=esc(offer_what(o)),
                  JSONLD=jld, CONTENT=body, PROVIDER_URL=prov["deals"],
                  PROVIDER_NAME=esc(prov["name"]), DISPLAY=cfg["display"],
                  NICHE=cfg["niche"])
    return fname, page, url


def write_index(cfg, burl, providers, filtered, data):
    # 配置里每一家都上首页品牌表：有优惠的标条数，没优惠的标“暂无公开优惠”。
    cards = "".join(
        f'<a class="card" href="{burl}/providers/{esc(p["slug"])}"><b>{esc(p["name"])}</b> '
        f'<span class="small">&mdash; {len(filtered.get(p["slug"], []))} public offer(s)</span></a>'
        if filtered.get(p["slug"])
        else f'<a class="card" href="{burl}/providers/{esc(p["slug"])}"><b>{esc(p["name"])}</b> '
             f'<span class="small">&mdash; No public offers verified yet</span></a>'
        for p in providers)
    faq = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "What is this site?",
             "acceptedAnswer": {"@type": "Answer", "text": f'{cfg["display"]} is an index of public {cfg["niche"]} offers from major providers, each checked against the brand official page.'}},
            {"@type": "Question", "name": "How often is it updated?",
             "acceptedAnswer": {"@type": "Answer", "text": "The data is refreshed automatically on a fixed schedule; each page records when it was last checked."}},
        ],
    }
    il = {"@context": "https://schema.org", "@type": "ItemList",
          "itemListElement": [{"@type": "ListItem", "position": i + 1,
                               "url": f"{burl}/providers/{esc(p['slug'])}"}
                              for i, p in enumerate(providers)]}
    jld = (f'<script type="application/ld+json">{json.dumps(faq, ensure_ascii=False)}</script>\n'
           f'<script type="application/ld+json">{json.dumps(il, ensure_ascii=False)}</script>')
    body = (f'<h1>{cfg["display"]} &mdash; Public travel offers, updated continuously</h1>'
            f'<p>A public-offer index for major travel brands. Each offer links to the brand '
            f'official page and is checked on a fixed schedule. Last data scrape: '
            f'<b>{esc(fmt_scrape(data.get("fetched_at","unknown")))}</b>.</p>'
            f'<h2>Brands we track</h2><div class="grid">{cards}</div>'
            f'<h2>Cross-brand comparison</h2>'
            f'<a class="card" href="{burl}/compare">Open comparison view &rarr;</a>')
    page = render("index.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'{cfg["display"]} | Public travel offers',
                  DESC=f'Public travel offers from major brands, checked against the official page and updated on a schedule.',
                  CANONICAL=f"{burl}/", BASE_URL=burl, OG_TITLE=cfg["display"],
                  OG_DESC=f'Public travel offers, updated on a schedule.',
                  JSONLD=jld, CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "index.html", page, f"{burl}/"


def write_compare(cfg, burl, providers, filtered):
    rows = []
    position = 1
    list_items = []
    for p in providers:
        offers = filtered.get(p["slug"], [])
        best = None
        for o in offers:
            if o.get("price") is not None:
                if best is None or o["price"] < best["price"]:
                    best = o
        if best:
            rows.append(f'<tr><td>{esc(p["name"])}</td><td>{esc(offer_what(best))}</td>'
                        f'<td><a href="{esc(best.get("offer_url") or p["deals"])}" rel="nofollow noopener" target="_blank">Open &rarr;</a></td></tr>')
            list_items.append({"@type": "ListItem", "position": position,
                               "url": f"{burl}/providers/{esc(p['slug'])}"})
            position += 1
    table = ('<table class="offers"><thead><tr><th>Brand</th><th>Lowest verified price</th>'
             '<th>Link</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>') \
        if rows else '<p>No verified prices available right now.</p>'
    il = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": list_items}
    jld = f'<script type="application/ld+json">{json.dumps(il, ensure_ascii=False)}</script>'
    body = f'<h1>Cross-brand travel offer comparison</h1>{table}'
    page = render("compare.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'Compare travel offers | {cfg["display"]}',
                  DESC=f'Side-by-side public travel offers from major brands.',
                  CANONICAL=f"{burl}/compare", BASE_URL=burl, OG_TITLE="Compare offers",
                  OG_DESC=f'Compare public travel offers.', JSONLD=jld,
                  CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "compare.html", page, f"{burl}/compare"


def write_404(burl):
    body = (f'<h1>404 &mdash; Page not found</h1>'
            f'<p>The page you requested does not exist.</p>'
            f'<p><a class="go" href="{burl}/">Return to the homepage &rarr;</a></p>')
    page = render("index.html", LANG="en",
                  TITLE=f'404 | {burl.split("//")[-1]}',
                  DESC="Page not found.", CANONICAL=f"{burl}/", BASE_URL=burl,
                  OG_TITLE="404", OG_DESC="Page not found.", JSONLD="",
                  CONTENT=body, DISPLAY="TravelPromoHub", NICHE="travel")
    return "404.html", page


def write_privacy(cfg, burl):
    url = f"{burl}/privacy"
    body = (
        '<h1>Privacy Policy</h1>'
        '<h2>What this site is</h2>'
        f'<p>{esc(cfg["display"])} is a public index of {esc(cfg["niche"])} offers. '
        'Each offer links to the brand&rsquo;s own official page, where the offer, its '
        'conditions and its price are set and controlled by that brand.</p>'
        '<h2>Advertising and affiliate links</h2>'
        '<p>This site may display third-party advertising and may contain affiliate links. '
        'Where advertising or affiliate links are shown, they are supplied by third parties, '
        'not by this site. Those third parties may set their own cookies or identifiers and '
        'handle information under their own privacy policies. This site does not control what '
        'those third parties do, and their handling of information is governed by their own '
        'policies.</p>'
        '<h2>Offers, prices and terms</h2>'
        '<p>Offer content, prices and terms are set by each provider, not by this site. This '
        'site only indexes publicly listed offers and records when each offer was checked '
        'against the provider&rsquo;s official page. This site does not sell travel services '
        'and takes no part in any transaction. Any booking or purchase is made directly with '
        'the provider, under that provider&rsquo;s own terms.</p>'
        '<h2>Changes</h2>'
        '<p>This policy is updated when what the site does changes. The current version is '
        'always the one published on this page.</p>'
        '<h2>Contact</h2>'
        f'<p>See the <a href="{burl}/contact">Contact page</a>.</p>'
    )
    page = render("index.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'Privacy Policy | {cfg["display"]}',
                  DESC=f'How {cfg["display"]} handles offers, advertising and affiliate links.',
                  CANONICAL=url, BASE_URL=burl, OG_TITLE="Privacy Policy",
                  OG_DESC=f'How {cfg["display"]} handles offers, advertising and affiliate links.',
                  JSONLD="", CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "privacy.html", page, url


def write_about(cfg, burl):
    url = f"{burl}/about"
    body = (
        '<h1>About this site</h1>'
        '<h2>What this site is</h2>'
        f'<p>{esc(cfg["display"])} is a public index of {esc(cfg["niche"])} offers from major '
        'travel brands. It gathers publicly listed offers in one place so they can be compared, '
        'and links every offer back to the brand&rsquo;s own official page.</p>'
        '<h2>How the offers are checked</h2>'
        '<p>Each brand&rsquo;s official offers page is checked on a fixed schedule. The wording '
        'and conditions shown for an offer come from the brand&rsquo;s own official page. Every '
        'page shows a review date &mdash; that date is when that page was last checked.</p>'
        '<h2>What this site is not</h2>'
        '<p>This site is not the official site of any travel brand. It is not affiliated with, '
        'endorsed by, or operated by any of the brands listed here. All brand names, offers and '
        'trademarks belong to their respective owners.</p>'
        '<h2>Who runs it</h2>'
        f'<p>This site is an independent index, published under the name {esc(cfg["display"])}.</p>'
        '<h2>Contact</h2>'
        f'<p>See the <a href="{burl}/contact">Contact page</a>.</p>'
    )
    page = render("index.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'About | {cfg["display"]}',
                  DESC=f'What {cfg["display"]} is and how its offers are checked.',
                  CANONICAL=url, BASE_URL=burl, OG_TITLE="About",
                  OG_DESC=f'What {cfg["display"]} is and how its offers are checked.',
                  JSONLD="", CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "about.html", page, url


def write_contact(cfg, burl):
    url = f"{burl}/contact"
    if CONTACT_EMAIL_LIVE:
        # 只有测试信真的转发进了收件箱，才走这一支
        inner = (
            '<h2>Email</h2>'
            f'<p>For questions, corrections, or requests to remove an offer, email: '
            f'<a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a></p>'
            '<p>Please include the page address (URL) you are writing about, so it can be '
            'found quickly.</p>'
        )
    else:
        # 还没测过一封真信：按规则不写地址
        inner = (
            '<h2>Email</h2>'
            '<p>A dedicated contact address for this site is being set up. It will be '
            'published on this page once it is live.</p>'
        )
    body = (
        '<h1>Contact</h1>'
        f'<p>{esc(cfg["display"])} is an independent index of public {esc(cfg["niche"])} '
        'offers. It is not the official site of any travel brand, and it cannot make changes '
        'to an offer, a booking or a price &mdash; those are handled by the provider '
        'concerned.</p>'
        + inner
    )
    page = render("index.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'Contact | {cfg["display"]}',
                  DESC=f'How to contact {cfg["display"]}.',
                  CANONICAL=url, BASE_URL=burl, OG_TITLE="Contact",
                  OG_DESC=f'How to contact {cfg["display"]}.',
                  JSONLD="", CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "contact.html", page, url


def write_sitemap(cfg, burl, urls, lastmod):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in sorted(set(urls)):
        lines.append(f'  <url><loc>{xescape(u)}</loc><lastmod>{lastmod}</lastmod></url>')
    lines.append('</urlset>')
    open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(lines))


def write_headers():
    # 关键：默认情况下 Cloudflare Pages 会把 HTML 在边缘缓存最多 7 天（s-maxage=604800）。
    # 这会导致“本轮被撤下的优惠页”在线上残留（命中旧缓存），与 no_unverified_published 规则冲突。
    # 这里把所有响应在边缘只缓存 60 秒并要求 revalidate，保证每 6 小时刷新 / 撤下能及时生效。
    # 配合 workflow 部署后清一次边缘缓存，撤下的优惠页不会在线上滞留。
    rules = ["/*", "  Cache-Control: public, max-age=0, s-maxage=60, must-revalidate"]
    open(os.path.join(SITE, "_headers"), "w", encoding="utf-8").write("\n".join(rules) + "\n")


def main():
    global REVIEW_DATE
    cfg = sitecfg.load_config()
    data = load_offers()
    burl = base_url(cfg)
    # 复核日期优先用抓取数据里记录的（scraper 每次刷新），保证页面与数据一致
    REVIEW_DATE = data.get("review_date") or datetime.date.today().isoformat()
    # 清掉上一轮留下的旧页（零优惠厂商的旧页、被删 offer 的旧 deal 页），避免残页被部署
    for d in ("providers", "deals"):
        p = os.path.join(SITE, d)
        if os.path.isdir(p):
            shutil.rmtree(p)
    os.makedirs(os.path.join(SITE, "providers"), exist_ok=True)
    os.makedirs(os.path.join(SITE, "deals"), exist_ok=True)
    write_headers()   # 限制 HTML 边缘缓存，避免撤下的优惠页在线上残留

    # 只发布“核到官方页原话（verify=verified）”的 offer：有真实名 + 真条件 + 官方原话 + 已核验。
    # 核不到原话的只留在 data 里作留痕，不进 site / sitemap / 品牌页 / 对比页。
    providers = data["providers"]
    filtered = {}
    for p in providers:
        filtered[p["slug"]] = [o for o in (p.get("offers") or [])
                               if o.get("offer") and o.get("condition") and o.get("official")
                               and o.get("verify") == "verified"]

    all_urls = [f"{burl}/"]
    f, p, u = write_index(cfg, burl, providers, filtered, data)
    open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
    all_urls.append(u)
    f, p, u = write_compare(cfg, burl, providers, filtered)
    open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
    all_urls.append(u)

    # 三个固定页：隐私政策 / 关于 / 联系（页脚三处都链到，且都进 sitemap）
    for writer in (write_privacy, write_about, write_contact):
        f, p, u = writer(cfg, burl)
        open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
        all_urls.append(u)

    # 配置里每一家厂商都建一页：有核到官方原话的建优惠页，没优惠的建品牌页
    # （写清官方入口 + 核对日期，绝不放任何金额/折扣数字）。这样配置 / 首页 /
    # sitemap / 实际页面四处保持一致。
    for prov in providers:
        offers = filtered.get(prov["slug"], [])
        f, p, u = write_provider_page(cfg, burl, prov, offers, data.get("fetched_at", ""))
        open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
        all_urls.append(u)
        for i, o in enumerate(offers):
            f, p, u = write_deal_page(cfg, burl, prov["slug"], i, o, prov, data.get("fetched_at", ""))
            open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
            all_urls.append(u)

    lastmod = (data.get("fetched_at") or datetime.datetime.now().isoformat())[:10]
    write_sitemap(cfg, burl, all_urls, lastmod)
    open(os.path.join(SITE, "robots.txt"), "w", encoding="utf-8").write(
        f"User-agent: *\nAllow: /\nSitemap: {burl}/sitemap.xml\n")
    # 404 页：不存在的地址返回 404，不回落到首页（Cloudflare Pages 有 404.html 即按 404 返回）
    f, p = write_404(burl)
    open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
    # 把配置随构建一起打包到 site/.ilang/，供上线后自测“改 site.ilang 站就变”
    ilang_src = os.path.join(HERE, ".ilang", "site.ilang")
    if os.path.exists(ilang_src):
        dest = os.path.join(SITE, ".ilang")
        os.makedirs(dest, exist_ok=True)
        shutil.copyfile(ilang_src, os.path.join(dest, "site.ilang"))
    print(f"built {len(all_urls)} urls into {SITE}")


if __name__ == "__main__":
    main()
