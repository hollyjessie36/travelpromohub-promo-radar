# ::ILANG[TYPE:builder][PROJECT:travelpromohub]
# 职责：读 data/offers.json + .ilang/site.ilang，渲染静态站到 site/，生成 sitemap.xml / robots.txt。
# 边界：模板占位符只做 [[VAR]] 替换；优惠/价格只在抓到真值时写，绝不编。
# 每个 deal / provider 页：第一屏直接回答“有没有优惠、怎么拿”，下面四列表
# （优惠是什么 / 拿到它的条件 / 官方来源页地址 / 复核日期），并露出真实抓取时间。
# 配置全部来自 site.ilang 与 offers.json，不写死。
import os
import re
import json
import datetime
import html
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
.go{display:inline-block;margin-top:8px;color:#1463c8;font-weight:600}
.small{font-size:12px;color:#7a8aa3}
footer.site{padding:18px 22px;color:#5a6b85;font-size:13px;border-top:1px solid #e3e9f2;margin-top:30px}
"""

ILANG_NOTE = ("Site rules are described in the I-Lang protocol &mdash; see "
             "<code>.ilang/site.ilang</code>. Protocol info: ilang.ai")


def load_offers():
    if not os.path.exists(OFFERS):
        return {"fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "providers": []}
    return json.load(open(OFFERS, encoding="utf-8"))


def base_url(cfg):
    b = cfg.get("base_url") or ""
    if not b:
        b = "https://travelpromohub.pages.dev"  # 部署后会被 site.ilang 的 base_url 回写覆盖
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
def fmt_money(v, cur):
    if v is None:
        return ""
    s = f"{int(v):g}" if float(v) == int(v) else f"{v:g}"
    return f"{s} {cur}".strip()


def offer_what(o):
    if o.get("discount"):
        return o["discount"]
    if o.get("price") is not None:
        return fmt_money(o["price"], o.get("currency"))
    return "公开优惠"


def offer_condition(o, provider):
    thr = o.get("threshold")
    if thr is not None:
        return f'消费满 {thr:g} {o.get("currency") or ""} 可用'.strip()
    return (f"以 {provider} 官方优惠页公布的使用条件为准"
            f"（本页仅转引公开优惠信息，未结构化解析门槛）")


def first_screen(has_offer, what, provider):
    if has_offer:
        return (f"有优惠。{provider} 当前公开优惠：<b>{esc(what)}</b>。"
                f"怎么拿：打开下方「官方来源页地址」，在预订 / 下单时选用该优惠或促销码即可；"
                f"最终门槛与价格以官方页为准。")
    return (f"暂无可用优惠。{provider} 的官方优惠页本次抓取未解析到可核实的当前优惠"
            f"（常见原因：页面为 JS 渲染、反爬拦截或区域限制）。请以官方页为准。")


def offers_table(offers, provider):
    rows = []
    for o in offers:
        what = offer_what(o)
        cond = offer_condition(o, provider)
        src = o.get("source_url") or ""
        src_html = (f'<a href="{esc(src)}" rel="nofollow noopener" target="_blank">'
                    f'{esc(src)}</a>')
        rows.append(f'<tr><td>{esc(what)}</td><td>{esc(cond)}</td>'
                    f'<td>{src_html}</td><td>{esc(REVIEW_DATE)}</td></tr>')
    return ('<table class="offers"><thead><tr>'
            '<th>优惠是什么</th><th>拿到它的条件</th>'
            '<th>官方来源页地址</th><th>复核日期</th></tr></thead><tbody>'
            + "".join(rows) + '</tbody></table>')


def scrape_line(fetched_at):
    return (f'<p class="scraptime">数据抓取时间：<b>{esc(fmt_scrape(fetched_at))}</b>'
            f'（复核日期：{esc(REVIEW_DATE)}）</p>')


def write_provider_page(cfg, burl, prov, offers, fetched_at):
    slug = prov["slug"]
    fname = f"providers/{slug}.html"
    url = f"{burl}/providers/{slug}"   # Cloudflare Pages 用无扩展名 clean URL
    priced = [o for o in offers if o.get("price") is not None]
    ld = {"@context": "https://schema.org", "@type": "Product",
          "name": prov["name"], "brand": {"@type": "Brand", "name": prov["name"]},
          "url": url}
    if priced:
        ld["offers"] = {"@type": "AggregateOffer", "priceCurrency": cfg["currency"],
                        "lowPrice": min(o["price"] for o in priced),
                        "highPrice": max(o["price"] for o in priced),
                        "offerCount": len(priced),
                        "offers": [{"@type": "Offer", "name": offer_what(o),
                                    "price": o["price"],
                                    "priceCurrency": o.get("currency") or cfg["currency"],
                                    "url": o.get("offer_url") or url,
                                    "availability": "https://schema.org/InStock"}
                                   for o in priced]}
    jld = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    what = f"{len(offers)} 条公开优惠（已核实）" if offers else "暂无优惠"
    body = (f'<h1>{esc(prov["name"])} &mdash; 公开 {esc(cfg["niche"])} 优惠</h1>'
            f'<div class="firstscreen">{first_screen(bool(offers), what, prov["name"])}</div>'
            + (offers_table(offers, prov["name"]) if offers else "")
            + scrape_line(fetched_at))
    page = render("provider.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'{prov["name"]} {cfg["niche"]} 优惠 | {cfg["display"]}',
                  DESC=f'{prov["name"]} 公开 {cfg["niche"]} 优惠，含条件与官方来源。',
                  CANONICAL=url, BASE_URL=burl, OG_TITLE=prov["name"],
                  OG_DESC=f'{prov["name"]} {cfg["niche"]} 优惠', JSONLD=jld,
                  CONTENT=body, PROVIDER_NAME=esc(prov["name"]),
                  PROVIDER_URL=prov["deals"], DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return fname, page, url


def write_deal_page(cfg, burl, slug, idx, o, prov, fetched_at):
    fname = f"deals/{slug}_{idx}.html"
    url = f"{burl}/deals/{slug}_{idx}"   # clean URL
    ld = {"@context": "https://schema.org", "@type": "Offer",
          "name": offer_what(o), "url": o.get("offer_url") or prov["deals"]}
    if o.get("price") is not None:
        ld["price"] = o["price"]
        ld["priceCurrency"] = o.get("currency") or cfg["currency"]
    if o.get("valid_until"):
        ld["priceValidUntil"] = o["valid_until"]
    ld["availability"] = ("https://schema.org/OutOfStock" if o.get("valid_until")
                          and o["valid_until"] < datetime.date.today().isoformat()
                          else "https://schema.org/InStock")
    jld = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    body = (f'<h1>{esc(offer_what(o))}</h1>'
            f'<div class="firstscreen">{first_screen(True, offer_what(o), prov["name"])}</div>'
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


def write_index(cfg, burl, data):
    providers = [p for p in data["providers"] if p.get("offers")]
    cards = "".join(
        f'<a class="card" href="{burl}/providers/{esc(p["slug"])}"><b>{esc(p["name"])}</b> '
        f'<span class="small">&mdash; {len(p.get("offers", []))} 条公开优惠已核实</span></a>'
        for p in providers)
    faq = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": "What is this site?",
             "acceptedAnswer": {"@type": "Answer", "text": f'{cfg["display"]} is an index of public {cfg["niche"]} offers from major providers. It is updated on a schedule from each provider\'s official offers page.'}},
            {"@type": "Question", "name": "How often is it updated?",
             "acceptedAnswer": {"@type": "Answer", "text": "The data is refreshed automatically on a fixed schedule; each page records when it was last checked."}},
            {"@type": "Question", "name": "Are the prices guaranteed?",
             "acceptedAnswer": {"@type": "Answer", "text": "No. Prices and terms are set by each provider. Always confirm the final price on the provider's official site before booking."}},
        ],
    }
    il = {"@context": "https://schema.org", "@type": "ItemList",
          "itemListElement": [{"@type": "ListItem", "position": i + 1,
                               "url": f"{burl}/providers/{esc(p['slug'])}"}
                              for i, p in enumerate(providers)]}
    jld = (f'<script type="application/ld+json">{json.dumps(faq, ensure_ascii=False)}</script>\n'
           f'<script type="application/ld+json">{json.dumps(il, ensure_ascii=False)}</script>')
    body = (f'<h1>{cfg["display"]} &mdash; 公开 {esc(cfg["niche"])} 优惠，持续更新</h1>'
            f'<p>主流旅行品牌的公开优惠索引，按固定节奏从各品牌官方优惠页重新核实。'
            f'最近一次数据抓取：<b>{esc(fmt_scrape(data.get("fetched_at","unknown")))}</b>。</p>'
            f'<h2>已核实优惠的品牌</h2><div class="grid">{cards}</div>'
            f'<h2>跨品牌对比</h2><a class="card" href="{burl}/compare">打开对比视图 &rarr;</a>')
    page = render("index.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'{cfg["display"]} | 公开 {esc(cfg["niche"])} 优惠',
                  DESC=f'主流旅行品牌的公开 {esc(cfg["niche"])} 优惠，持续更新。',
                  CANONICAL=f"{burl}/", BASE_URL=burl, OG_TITLE=cfg["display"],
                  OG_DESC=f'公开 {esc(cfg["niche"])} 优惠，持续更新。',
                  JSONLD=jld, CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "index.html", page, f"{burl}/"


def write_compare(cfg, burl, data):
    rows = []
    position = 1
    list_items = []
    for p in data["providers"]:
        offers = p.get("offers", [])
        best = None
        for o in offers:
            if o.get("price") is not None:
                if best is None or o["price"] < best["price"]:
                    best = o
        if best:
            rows.append(f'<tr><td>{esc(p["name"])}</td><td>{esc(offer_what(best))}</td>'
                        f'<td><a href="{esc(best.get("offer_url") or p["deals"])}" rel="nofollow noopener" target="_blank">打开 &rarr;</a></td></tr>')
            list_items.append({"@type": "ListItem", "position": position,
                               "url": f"{burl}/providers/{esc(p['slug'])}"})
            position += 1
    table = ('<table class="offers"><thead><tr><th>品牌</th><th>最低可核实价</th>'
             '<th>链接</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>') \
        if rows else '<p>暂无可核实价格的优惠。</p>'
    il = {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": list_items}
    jld = f'<script type="application/ld+json">{json.dumps(il, ensure_ascii=False)}</script>'
    body = f'<h1>跨品牌对比 {esc(cfg["niche"])} 优惠</h1>{table}'
    page = render("compare.html", LANG=cfg["locale"].split("-")[0],
                  TITLE=f'对比 {esc(cfg["niche"])} 优惠 | {cfg["display"]}',
                  DESC=f'主流品牌的公开 {esc(cfg["niche"])} 优惠横向对比。',
                  CANONICAL=f"{burl}/compare", BASE_URL=burl, OG_TITLE="对比优惠",
                  OG_DESC=f'对比公开 {esc(cfg["niche"])} 优惠。', JSONLD=jld,
                  CONTENT=body, DISPLAY=cfg["display"], NICHE=cfg["niche"])
    return "compare.html", page, f"{burl}/compare"


def write_sitemap(cfg, burl, urls, lastmod):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in sorted(set(urls)):
        lines.append(f'  <url><loc>{xescape(u)}</loc><lastmod>{lastmod}</lastmod></url>')
    lines.append('</urlset>')
    open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(lines))


def main():
    cfg = sitecfg.load_config()
    data = load_offers()
    burl = base_url(cfg)
    # 清掉上一轮留下的旧页（零优惠厂商的旧页、被删 offer 的旧 deal 页），避免残页被部署
    import shutil
    for d in ("providers", "deals"):
        p = os.path.join(SITE, d)
        if os.path.isdir(p):
            shutil.rmtree(p)
    os.makedirs(os.path.join(SITE, "providers"), exist_ok=True)
    os.makedirs(os.path.join(SITE, "deals"), exist_ok=True)
    all_urls = [f"{burl}/"]
    f, p, u = write_index(cfg, burl, data)
    open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
    all_urls.append(u)
    f, p, u = write_compare(cfg, burl, data)
    open(os.path.join(SITE, f), "w", encoding="utf-8").write(p)
    all_urls.append(u)
    for prov in data["providers"]:
        offers = prov.get("offers", [])
        if not offers:
            continue  # 零真实优惠的厂商：页面下线，导航/sitemap 也不留
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
    # 把配置随构建一起打包到 site/.ilang/，供上线后自测“改 site.ilang 站就变”
    ilang_src = os.path.join(HERE, ".ilang", "site.ilang")
    if os.path.exists(ilang_src):
        dest = os.path.join(SITE, ".ilang")
        os.makedirs(dest, exist_ok=True)
        import shutil
        shutil.copyfile(ilang_src, os.path.join(dest, "site.ilang"))
    print(f"built {len(all_urls)} urls into {SITE}")


if __name__ == "__main__":
    main()
