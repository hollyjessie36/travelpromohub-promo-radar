# ::ILANG[TYPE:scraper][PROJECT:travelpromohub]
# 职责：抓 .ilang/site.ilang 里列的每个厂商的官方优惠页，提炼真实优惠，写 data/offers.json。
# 边界：只抓公开优惠页；遵守 robots.txt；绝不绕过反爬；抓不到价格就标空，绝不编。
# 配置真从这里读，不在代码里写死厂商清单（改 site.ilang 重跑，站就变）。
import os
import re
import json
import datetime
import urllib.request
import urllib.error
import urllib.robotparser
from html import unescape

import sitecfg

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "offers.json")
UA = sitecfg.load_config().get("scraper", {}).get(
    "user_agent", "Mozilla/5.0 (compatible; TravelPromoHubBot/1.0)")

_MONTHS = {m: i for i, m in enumerate(
    ["january","february","march","april","may","june","july","august",
     "september","october","november","december"], 1)}

_pct = re.compile(r"(?i)(\d{1,3})\s*%\s*off")
_price = re.compile(r"(?i)\$\s?(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)")
_date1 = re.compile(r"(?i)(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+20\d{2}")
_date2 = re.compile(r"(?i)\b\d{1,2}[/]\d{1,2}[/]20\d{2}\b")
_tag = re.compile(r"<[^>]+>")
_ws = re.compile(r"\s+")
# 丢弃明显不是优惠的财务/产品文案（保险、年费、抽奖、返现存款等），只留真实优惠信号
_junk = re.compile(r"(?i)(cookie|function|var |window\.|javascript|navigate|menu|footer|copyright|fdic|insur|annual fee|amazon|prize|direct deposit|renew|rebate|dividend|tax)")


def strip_tags(html):
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    txt = _tag.sub(" ", html)
    return unescape(txt)


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    enc = r.headers.get_content_charset() or "utf-8"
    return data.decode(enc, "replace")


def robots_allows(url):
    try:
        rp = urllib.robotparser.RobotFileParser()
        from urllib.parse import urlparse
        p = urlparse(url)
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(UA, url)
    except Exception:
        return True  # 读不到 robots 时放行，但不绕过；保守起见默认允许


def parse_date(text):
    for rx in (_date1, _date2):
        m = rx.search(text)
        if m:
            s = m.group(0)
            try:
                if rx is _date1:
                    mm = _MONTHS[s.split()[0].lower()]
                    dd = int(re.search(r"\d{1,2}", s).group(0))
                    yy = int(re.search(r"20\d{2}", s).group(0))
                else:
                    a, b, c = (int(x) for x in re.findall(r"\d+", s)[:3])
                    mm, dd, yy = (a, b, c) if a <= 12 else (b, a, c)
                return f"{yy:04d}-{mm:02d}-{dd:02d}"
            except Exception:
                return None
    return None


def extract_condition(txt, start):
    """只从官方页真实文本里抓“门槛/人群/有效期/限定范围”这类条件，原样转成英文短句。
    抓不到任何真条件就返回 None（上层会摘掉整行，绝不编）。"""
    win = txt[max(0, start - 220):start + 320]
    conds = []
    # 门槛：minimum spend / spend $X（真实页面金额，不编）
    m = re.search(r"(?i)(?:minimum\s+(?:spend|purchase)(?:\s+of)?|spend)\s+\$?\s*(\d[\d,]*(?:\.\d{2})?)", win)
    if m:
        amt = float(m.group(1).replace(",", ""))
        s = f"{int(amt):g}" if amt == int(amt) else f"{amt:g}"
        conds.append(f"Minimum spend ${s}")
    # 人群：members / AARP / AAA / senior / student / military / loyalty / rewards
    m = re.search(r"(?i)\b(AARP|AAA|senior|student|military|loyalty|rewards\s+members?|members)\b", win)
    if m:
        word = m.group(1)
        wl = word.lower()
        if wl.startswith("rewards") or wl == "members":
            conds.append("For members")
        else:
            conds.append(f"{word} members")
    # 有效期：真实日期
    d = parse_date(win)
    if d:
        conds.append(f"Valid through {d}")
    # 限定范围 / 范围
    mp = re.search(r"(?i)\bper\s+(person|day|night|stay)\b", win)
    if mp:
        conds.append(f"Per {mp.group(1)}")
    mpp = re.search(r"(?i)\bpp/?(?:day|night|person|stay)\b", win)
    if mpp:
        conds.append("Per person per day")
    for pat, label in [
        (r"(?i)\bweekly\b", "Weekly"),
        (r"(?i)\bnew\s+hotels?\b", "On new hotels"),
        (r"(?i)\bonline\b", "Online"),
        # 促销码/计划名：只要全大写 token（如 CRUISEFIRST），避开 your/the/our 等代词
        # 只对 with 放宽大小写，token 本身必须全大写（用 (?i:with) 作用域）
        (r"(?i:with)\s+([A-Z]{3,}[A-Za-z0-9]*)", None),
    ]:
        mm = re.search(pat, win)
        if mm:
            if label is None:
                conds.append(f"With {mm.group(1)}")
            else:
                conds.append(label)
    # 去重保序
    seen, out = set(), []
    for c in conds:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return "; ".join(out) if out else None


def extract_offers(html, provider, deals_url, currency):
    txt = _ws.sub(" ", strip_tags(html)).strip()
    offers = []
    seen = set()

    def add(match, is_pct):
        start = match.start()
        win = txt[max(0, start - 80):start + len(match.group(0)) + 12].strip()
        win = win[:96].strip()
        if len(win) < 8:
            return
        if not re.search(r"[A-Za-z]{3,}", win):
            return
        if _junk.search(win):
            return
        if not re.search(r"(?i)(%|\$|off|free|save|deal|discount|from|book|up to|promo)", win):
            return
        if is_pct:
            discount = f"{match.group(1)}% off"
            price = None
        else:
            price = float(match.group(1).replace(",", ""))
            discount = None
        # 在更宽的上下文里找“另一个金额”作为可能的最低消费门槛（真实页面文本，不编）
        wide = txt[max(0, start - 160):start + 220]
        amts = [float(m.group(1).replace(",", "")) for m in _price.finditer(wide)]
        others = [a for a in amts if price is None or abs(a - price) > 0.01]
        threshold = max(others) if others else None
        condition = extract_condition(txt, start)   # 只放官方页真有的条件，没有就 None
        title = f"{provider}: {win}"
        key = (provider, re.sub(r"[^a-z0-9%]", "", win.lower()) + (discount or str(price)))
        if key in seen:
            return
        seen.add(key)
        valid = parse_date(txt[max(0, start - 120):start + 140])
        offers.append({
            "title": title,
            "price": price,           # 只放当期可核实的售价；没有就 None，绝不编
            "discount": discount,
            "threshold": threshold,   # 真实页面里出现的“另一个金额”，作为可能的门槛提示
            "currency": currency if price is not None else None,
            "condition": condition,   # 真实条件短句（门槛/人群/有效期/范围），没有则 None
            "offer_url": deals_url,   # 裸链到官方优惠页；日后可换联盟链接
            "valid_until": valid,
            "source_url": deals_url,
        })

    for m in _pct.finditer(txt):
        add(m, True)
    for m in _price.finditer(txt):
        add(m, False)
    return offers


def main():
    cfg = sitecfg.load_config()
    currency = cfg["currency"]
    providers_out = []
    for p in cfg["providers"]:
        rec = {"name": p["name"], "slug": p["slug"], "site": p["site"],
               "deals": p["deals"], "outbound": p["outbound"], "offers": [],
               "status": "ok"}
        try:
            if not robots_allows(p["deals"]):
                rec["status"] = "robots_disallowed"
            else:
                html = fetch(p["deals"])
                rec["offers"] = extract_offers(html, p["name"], p["deals"], currency)
                if not rec["offers"]:
                    rec["status"] = "no_offers_found"
        except urllib.error.HTTPError as e:
            rec["status"] = f"http_{e.code}"
        except Exception as e:
            rec["status"] = f"error:{type(e).__name__}"
        providers_out.append(rec)
        print(f"  {p['name']}: {rec['status']} offers={len(rec['offers'])}")

    out = {
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "brand": cfg["brand"],
        "display": cfg["display"],
        "currency": currency,
        "locale": cfg["locale"],
        "providers": providers_out,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
