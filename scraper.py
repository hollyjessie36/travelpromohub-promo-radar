# ::ILANG[TYPE:scraper][PROJECT:travelpromohub]
# 职责：以「人工核过的真实优惠」为唯一真实来源（CURATED_OFFERS），每次运行重新抓取
# 官方优惠页，逐条核对 official 那一句原话是否能在线核到：
#   - 页面能抓到且原话还在 -> verify=verified，发布（进 site/sitemap/品牌页/对比页），写复核日期
#   - 页面能抓到但原话核不到 / 抓不到（JS / 反爬 / 网络）-> verify=unverified，只留 data 作留痕
#     （记 note 说明为什么核不到），绝不发布、不进 site/sitemap、页面上不写任何核验状态
# 说明：线上只许出现核到原话的条；核不到的留在数据里并记下原因，那是留痕，不是发布。
# 条件（condition）只取 official 原话里真有的限定片段（人群/门槛/天数/有效期/城市网点），
# 绝不编优惠、编条件、编价格。
import os
import re
import json
import ssl
import datetime
import urllib.request
import sitecfg

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "offers.json")

# 人工核过的真实优惠。每条的 official 必须是官方页上逐字存在的那一句；
# condition 是该句里真有的限定（人群/门槛/天数/有效期/城市网点），也是原话子串。
CURATED_OFFERS = {
    "avis": [
        {"offer": "10% off at local Avis locations",
         "condition": "at local Avis locations",
         "official": "Save 10% at local Avis locations",
         "source": "https://www.avis.com/en/offers/us-offers"},
        {"offer": "Up to 25% off 5+ day rentals",
         "condition": "on 5+ day rentals",
         "official": "Save up to 25% on 5+ day rentals",
         "source": "https://www.avis.com/en/offers/us-offers"},
        {"offer": "$10 off on $175+ 3+ day rentals",
         "condition": "when you spend $175 on Rental of 3 Days or More",
         "official": "Enjoy $10 off when you spend $175 on Rental of 3 Days or More",
         "source": "https://www.avis.com/en/offers/us-offers"},
    ],
    "wyndham": [
        {"offer": "Wyndham Rewards members: 10-20% off",
         "condition": "Members",
         "official": "Members Get 10-20% Off",
         "source": "https://www.wyndhamhotels.com/wyndham-rewards/hotel-deals"},
        {"offer": "AARP members: 15% off 2+ consecutive nights",
         "condition": "AARP members; two or more consecutive nights",
         "official": ("For a limited time, AARP members enjoy 15% off two or more consecutive "
                      "nights at thousands of participating hotels worldwide."),
         "source": "https://www.wyndhamhotels.com/wyndham-rewards/hotel-deals"},
        {"offer": "$5+ off per night",
         "condition": "per Night",
         "official": "Get $5+ off per Night",
         "source": "https://www.wyndhamhotels.com/wyndham-rewards/hotel-deals"},
        {"offer": "Earn up to 100,000 Bonus Points (Earner Plus Card)",
         "condition": "Limited-Time Offer",
         "official": ("Limited-Time Offer: Earn up to 100,000 Bonus Points with the NEW "
                      "Wyndham Rewards Earner Plus Card."),
         "source": "https://www.wyndhamhotels.com/wyndham-rewards/hotel-deals"},
        {"offer": "2,000 Bonus Points (dining review, $50 min spend)",
         "condition": "requires a $50 minimum spend",
         "official": "Bonus points offer ends Nov. 2, 2026 and requires a $50 minimum spend.",
         "source": "https://www.wyndhamhotels.com/wyndham-rewards/hotel-deals"},
    ],
}

# 没核到优惠的厂商：沿用之前人工确认的状态，不编不猜。
NO_OFFER_STATUS = {
    "priceline": "no_offers_found",
    "hertz": "no_offers_found",
    "getyourguide": "robots_disallowed",
    "sixt": "robots_disallowed",
    "ihg": "http_403",
    "singapore-airlines": "http_404",
}

UA = ("Mozilla/5.0 (compatible; TravelPromoHubBot/1.0; "
      "+https://travelpromohub.pages.dev)")
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def norm(s):
    # 归一化连字符、商标符号与空白，避免因 Unicode 差异（en/em dash、®、™）导致核验失败，
    # 不影响对外展示（展示仍用原始 official 文本）。
    for ch in ("\u2013", "\u2014", "\u2212", "\u00ae", "\u2122"):
        s = s.replace(ch, "-") if ch in ("\u2013", "\u2014", "\u2212") else s.replace(ch, "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch(url):
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
        html = raw.decode(enc, errors="replace")
        html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
        html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", html)
        for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&#x27;", "'"),
                     ("&quot;", '"'), ("&rsquo;", "'"), ("&lsquo;", "'"),
                     ("&ndash;", "-"), ("&mdash;", "-"), ("&times;", "x")]:
            text = text.replace(a, b)
        return re.sub(r"\s+", " ", text).strip()
    except Exception as e:
        print("fetch failed:", url, repr(e))
        return None


def main():
    cfg = sitecfg.load_config()
    now = datetime.datetime.now(datetime.timezone.utc)
    fetched_at = now.isoformat()
    review_date = datetime.date.today().isoformat()
    out = {"fetched_at": fetched_at, "brand": cfg["brand"], "display": cfg["display"],
           "currency": cfg["currency"], "locale": cfg["locale"],
           "review_date": review_date, "providers": []}
    for p in cfg["providers"]:
        slug = p["slug"]
        curated = CURATED_OFFERS.get(slug)
        if not curated:
            out["providers"].append(
                {**p, "offers": [], "status": NO_OFFER_STATUS.get(slug, "no_offers_found")})
            continue
        text = fetch(p["deals"])
        kept = []
        if text is None:
            # 抓不到（JS/反爬/网络）：核不到原话 -> 只留 data 作留痕，绝不发布
            for o in curated:
                kept.append({**o, "verify": "unverified",
                             "note": "not published: official page could not be fetched "
                                     "(network / JS-rendered / anti-crawl)"})
            status = "ok_unverified"
        else:
            nt = norm(text)
            for o in curated:
                if norm(o["official"]) in nt:
                    # 核到原话 -> 发布并写复核日期
                    kept.append({**o, "verify": "verified", "review_date": review_date})
                else:
                    # 抓到了但原话核不到 -> 只留 data 作留痕，记原因，绝不发布
                    kept.append({**o, "verify": "unverified",
                                 "note": "not published: official sentence not found on "
                                         "fetched page (cannot verify verbatim)"})
                    print(f"WARN {slug}: official sentence NOT found -> held in data, "
                          f"not published: {o['offer']}")
            status = "ok" if any(o.get("verify") == "verified" for o in kept) else "ok_unverified"
        out["providers"].append({**p, "offers": kept, "status": status})
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump(out, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    published = sum(1 for p in out["providers"] for o in p["offers"]
                    if o.get("verify") == "verified")
    held = sum(1 for p in out["providers"] for o in p["offers"]
               if o.get("verify") != "verified")
    print(f"published(verified)={published}  held_in_data(unverified)={held} "
          f"across {len(out['providers'])} providers")


if __name__ == "__main__":
    main()
