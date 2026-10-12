# ::ILANG[TYPE:config-loader][PROJECT:travelpromohub]
# 这个文件只做一件事：把 .ilang/site.ilang 读成 Python dict。
# 边界：scraper.py 和 build.py 都从这里拿品牌/厂商清单/字段/渲染规则，
# 代码里不另写一份硬编码清单。改 site.ilang 重跑，站就得变。
import re
import os

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ilang", "site.ilang")


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def clean(v):
    """I-Lang 用 ``""`` 表示空值；去掉包裹的引号，避免把字面 ``""`` 当非空。"""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1].strip()
    return v


def load_config(path=DEFAULT_PATH):
    cfg = {
        "brand": "travelpromohub",
        "display": "TravelPromoHub",
        "niche": "travel",
        "locale": "en-US",
        "currency": "USD",
        "base_url": "",
        "domain": "",
        "cron": "0 */6 * * *",
        "providers": [],
        "fields": ["title", "price", "currency", "offer_url", "valid_until", "source_url", "fetched_at"],
    }
    if not os.path.exists(path):
        raise FileNotFoundError("site.ilang not found at " + path)
    text = open(path, encoding="utf-8").read()

    # ---- @STATE blocks ----
    for m in re.finditer(r"::STATE\{([^}]*)\}", text):
        body = m.group(1)
        lead = body.split(",", 1)[0].strip()  # e.g. @SITE / @BRAND
        for part in body.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            k, v = k.strip(), clean(v)
            if k == "base_url":
                cfg["base_url"] = v
            elif k == "domain":
                cfg["domain"] = v
            elif k == "name" and lead in ("@SITE", "@BRAND"):
                cfg["brand"] = v
            elif k == "display":
                cfg["display"] = v
            elif k == "locale":
                cfg["locale"] = v
            elif k == "currency":
                cfg["currency"] = v
            elif k == "name" and lead == "@NICHE":
                cfg["niche"] = v

    # ---- generic ::RULE <key>:<value> ----
    for m in re.finditer(r"::RULE\{([^}]*)\}", text):
        pair = m.group(1)
        if ":" in pair:
            k, v = pair.split(":", 1)
            k, v = k.strip(), clean(v)
            if k == "update_cron":
                cfg["cron"] = v
            elif k == "currency":
                cfg["currency"] = v
            elif k == "locale":
                cfg["locale"] = v
            elif k == "base_url":
                cfg["base_url"] = v
            elif k == "domain":
                cfg["domain"] = v

    # ---- ::MODULE{PROVIDERS} ... ::END ----
    pm = re.search(r"::MODULE\{PROVIDERS[^}]*\}(.*?)::END", text, re.S)
    if pm:
        for line in pm.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = [c.strip() for c in line.split("|")]
            if len(cols) < 3:
                continue
            name, site, deals = cols[0], cols[1], cols[2]
            affiliate = cols[3] if len(cols) > 3 else ""
            cfg["providers"].append({
                "name": clean(name),
                "slug": slugify(name),
                "site": clean(site),
                "deals": clean(deals),
                "affiliate": clean(affiliate),
                # 联盟链接留空则用裸链（官方优惠页）
                "outbound": affiliate if affiliate else deals,
            })

    # ---- ::MODULE{FIELDS} ----
    fm = re.search(r"::MODULE\{FIELDS[^}]*\}(.*?)::END", text, re.S)
    if fm:
        toks = [t.strip() for t in fm.group(1).replace("|", " ").split() if t.strip()]
        if toks:
            cfg["fields"] = toks

    # ---- ::MODULE{SCRAPER} ----
    sm = re.search(r"::MODULE\{SCRAPER[^}]*\}(.*?)::END", text, re.S)
    if sm:
        for line in sm.group(1).splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            cfg.setdefault("scraper", {})[k.strip()] = clean(v)

    # base_url 默认用 domain；都没有时先用占位，构建时再回写
    if not cfg["base_url"] and cfg["domain"]:
        cfg["base_url"] = "https://" + cfg["domain"]
    return cfg


if __name__ == "__main__":
    c = load_config()
    print("brand:", c["brand"], "| display:", c["display"])
    print("providers:", len(c["providers"]))
    for p in c["providers"]:
        print("  -", p["name"], p["slug"], p["deals"], "->", p["outbound"])
