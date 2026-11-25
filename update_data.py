import csv
import io
import json
import re
import html
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

DATA_FILE = "data.json"

MONTHS_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, application/json, text/csv, */*"
}

RSS_SOURCES = [
    {
        "label": "الأمم المتحدة (غزة)",
        "urls": [
            "https://news.un.org/feed/subscribe/ar/news/region/middle-east/feed/rss.xml",
            "https://news.un.org/feed/subscribe/ar/news/topic/humanitarian-aid/feed/rss.xml"
        ],
        "limit": 4,
        "gaza_only": True
    },
    {
        "label": "OCHA",
        "urls": ["https://www.ochaopt.org/rss.xml"],
        "limit": 3,
        "gaza_only": False
    },
    {
        "label": "UNRWA",
        "urls": ["https://www.unrwa.org/ar/news-reports/rss.xml"],
        "limit": 3,
        "gaza_only": True
    }
]

RUMOR_SOURCES = [
    {
        "label": "منصة مسبار لتقصي الحقائق",
        "urls": [
            "https://misbar.com/rss",
            "https://www.misbar.com/feed"
        ],
        "limit": 5
    }
]

# خريطة ربط أسماء السلع الإنجليزية من بيانات WFP HDX بالسلع العربية في التطبيق
WFP_COMMODITY_MAP = {
    "wheat flour": {"name": "طحين أبيض (1 كغم)", "unit": "شيكل"},
    "bread": {"name": "ربطة خبز (متوسط رصد WFP)", "unit": "شيكل"},
    "potatoes": {"name": "بطاطا (1 كغم)", "unit": "شيكل"},
    "onions": {"name": "بصل ناشف (1 كغم)", "unit": "شيكل"},
    "tomatoes": {"name": "بندورة (1 كغم)", "unit": "شيكل"},
    "oil": {"name": "زيت نباتي / ذرة (1 لتر)", "unit": "شيكل"},
    "sugar": {"name": "سكر أبيض (1 كغم)", "unit": "شيكل"},
    "rice": {"name": "أرز (1 كغم)", "unit": "شيكل"},
    "fuel (gas)": {"name": "أسطوانة غاز طهي (12 كغم)", "unit": "شيكل"},
    "fuel (petrol-gasoline)": {"name": "بنزين 95 أوكتان (1 لتر)", "unit": "شيكل"},
    "fuel (diesel)": {"name": "سولار / ديزل (1 لتر)", "unit": "شيكل"}
}


def clean_html_text(raw_text):
    if not raw_text:
        return ""
    unescaped = html.unescape(raw_text)
    no_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", no_tags).strip()


def format_ar_date(date_str):
    if not date_str:
        now = datetime.now(timezone.utc)
        return f"{now.day} {MONTHS_AR[now.month]} {now.year}"
    try:
        dt = parsedate_to_datetime(date_str.strip())
        return f"{dt.day} {MONTHS_AR[dt.month]} {dt.year}"
    except Exception:
        try:
            dt = datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
            return f"{dt.day} {MONTHS_AR[dt.month]} {dt.year}"
        except Exception:
            return date_str[:16]


def fetch_rss_feed(url, source_label, limit=4, gaza_only=False):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()

    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    extracted = []
    gaza_keywords = (
        "غزة", "خان يونس", "رفح", "الوسطى", "دير البلح", "النصيرات",
        "الأونروا", "أوتشا", "الغذاء العالمي", "gaza", "unrwa", "ocha", "wfp"
    )

    for item in items:
        title_raw = item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or ""
        desc_raw = (
            item.findtext("description")
            or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            or item.findtext("{http://www.w3.org/2005/Atom}summary")
            or ""
        )
        pub_raw = (
            item.findtext("pubDate")
            or item.findtext("{http://www.w3.org/2005/Atom}updated")
            or item.findtext("{http://www.w3.org/2005/Atom}published")
            or ""
        )

        title = clean_html_text(title_raw)
        body = clean_html_text(desc_raw)
        if not title:
            continue

        if gaza_only:
            combined_lower = (title + " " + body).lower()
            if not any(kw in combined_lower for kw in gaza_keywords):
                continue

        summary = (body[:260] + "...") if len(body) > 260 else body
        extracted.append({
            "title": f"[{source_label}] {title}",
            "time": format_ar_date(pub_raw),
            "body": summary or f"تحديث ميداني رسمي صادر عن {source_label} حول الأوضاع الإنسانية في قطاع غزة."
        })

        if len(extracted) >= limit:
            break

    return extracted


def fetch_misbar_rumors():
    """جلب أحدث تحققات الشائعات المتعلقة بغزة من منصة مسبار (قسم rumors)"""
    gaza_keywords = ("غزة", "خان يونس", "رفح", "القطاع", "الأونروا", "مساعدات", "معبر", "فلسطين")
    extracted_rumors = []

    for src in RUMOR_SOURCES:
        for feed_url in src["urls"]:
            try:
                req = urllib.request.Request(feed_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    xml_bytes = resp.read()
                root = ET.fromstring(xml_bytes)
                items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

                for item in items:
                    title = clean_html_text(item.findtext("title") or "")
                    desc = clean_html_text(
                        item.findtext("description")
                        or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                        or ""
                    )
                    pub_date = format_ar_date(item.findtext("pubDate") or "")
                    combined = f"{title} {desc}"

                    if not title or not any(kw in combined for kw in gaza_keywords):
                        continue

                    is_true = any(w in title for w in ("صحيح", "حقيقة", "توضيح رسمي", "مؤكد"))
                    verdict = "true" if is_true else "false"
                    tag = "توضيح رسمي" if is_true else "ادعاء مضلل"
                    truth_text = (desc[:280] + "...") if len(desc) > 280 else (desc or "تم التحقق من الخبر عبر فريق تقصي الحقائق ومطابقته مع المصادر الرسمية.")

                    extracted_rumors.append({
                        "verdict": verdict,
                        "tag": tag,
                        "claim": title,
                        "truth": truth_text,
                        "meta": f"المصدر: {src['label']} | {pub_date}"
                    })

                    if len(extracted_rumors) >= src["limit"]:
                        break
                if extracted_rumors:
                    break
            except Exception as e:
                print(f"تخطي مصدر الشائعات ({feed_url}): {e}")

    return extracted_rumors


def fetch_wfp_market_prices():
    """جلب أحدث أسعار السلع في قطاع غزة من بيانات برنامج الأغذية العالمي (WFP) على منصة HDX"""
    api_url = "https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-state-of-palestine"
    req = urllib.request.Request(api_url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        pkg = json.loads(resp.read().decode("utf-8")).get("result", {})

    csv_url = ""
    for res in pkg.get("resources", []):
        fmt = (res.get("format") or "").upper()
        url = res.get("url") or ""
        if fmt == "CSV" and url.endswith(".csv"):
            csv_url = url
            break

    if not csv_url:
        return [], ""

    csv_req = urllib.request.Request(csv_url, headers=HEADERS)
    with urllib.request.urlopen(csv_req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))
    gaza_rows = []
    for row in reader:
        if row.get("date", "").startswith("#"):
            continue
        admin1 = (row.get("admin1") or "").lower()
        market = (row.get("market") or "").lower()
        if "gaza" in admin1 or "gaza" in market or "khan yunis" in market or "deir" in market:
            gaza_rows.append(row)

    if not gaza_rows:
        return [], ""

    # تحديد أحدث شهر متوفر في بيانات غزة
    latest_date = max(r.get("date", "") for r in gaza_rows)
    latest_rows = [r for r in gaza_rows if r.get("date") == latest_date]

    grouped = {}
    for r in latest_rows:
        comm = (r.get("commodity") or "").strip().lower()
        try:
            price = float(r.get("price", 0))
        except ValueError:
            continue
        if price <= 0:
            continue
        for key, meta in WFP_COMMODITY_MAP.items():
            if key in comm:
                grouped.setdefault(key, {"meta": meta, "prices": []})["prices"].append(price)
                break

    updated_market = []
    ar_period = format_ar_date(latest_date)
    for key, info in grouped.items():
        avg_price = round(sum(info["prices"]) / len(info["prices"]), 2)
        price_str = f"{int(avg_price) if avg_price.is_integer() else avg_price} {info['meta']['unit']}"
        status = "red" if "diesel" in key else ("amber" if any(x in key for x in ("potatoes", "onions", "gas", "petrol")) else "green")
        label = "شحيح حاليا" if status == "red" else ("تذبذب / كمية محدودة" if status == "amber" else "متوفر بالأسواق")
        updated_market.append({
            "name": info["meta"]["name"],
            "area": "قطاع غزة (متوسط عام)",
            "status": status,
            "label": label,
            "fair": price_str,
            "ref": f"متوسط رصد WFP ({ar_period})",
            "source": "برنامج الأغذية العالمي (WFP / HDX)"
        })

    return updated_market, ar_period


def fetch_hdx_updates():
    """جلب أحدث تحديثات مجموعات بيانات WFP و OCHA الخاصة بفلسطين من منصة HDX"""
    url = "https://data.humdata.org/api/3/action/package_search?q=gaza+food+prices+OR+gaza+humanitarian&rows=3&sort=metadata_modified+desc"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    packages = result.get("result", {}).get("results", [])
    hdx_alerts = []
    latest_wfp_date = ""

    for pkg in packages:
        title = pkg.get("title", "").strip()
        org = pkg.get("organization", {}).get("title", "HDX")
        mod_date = format_ar_date(pkg.get("metadata_modified", ""))
        notes = clean_html_text(pkg.get("notes", ""))
        summary = (notes[:240] + "...") if len(notes) > 240 else notes

        if "food-prices" in pkg.get("name", "") and not latest_wfp_date:
            latest_wfp_date = mod_date

        if title:
            hdx_alerts.append({
                "title": f"[{org}] تحديث بيانات: {title}",
                "time": mod_date,
                "body": summary or "تم تحديث مجموعة البيانات الرسمية على منصة البيانات الإنسانية المفتوحة (HDX)."
            })

    return hdx_alerts, latest_wfp_date


def sync_outlets_metadata(data, now_ar_date):
    """تحديث حالة وسجل مراجعة نقاط التوزيع المعتمدة (outlets) والتحقق من اكتمال حقولها"""
    outlets = data.get("outlets", [])
    valid_outlets = []
    for o in outlets:
        if not o.get("name") or not o.get("area"):
            continue
        o.setdefault("hours", "الخط المجاني WFP: 1800124126")
        valid_outlets.append(o)
    data["outlets"] = valid_outlets
    return len(valid_outlets)


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_ar = format_ar_date(now_iso)
    data["lastUpdated"] = now_iso

    existing_titles = {a["title"] for a in data.get("alerts", [])}
    status_parts = []
    total_added = 0

    # 1. تحديث قسم التنبيهات والتقارير (alerts) من خلاصات RSS الرسمية
    for src in RSS_SOURCES:
        label = src["label"]
        fetched = []
        for feed_url in src["urls"]:
            try:
                fetched = fetch_rss_feed(
                    feed_url,
                    source_label=label,
                    limit=src["limit"],
                    gaza_only=src["gaza_only"]
                )
                if fetched:
                    print(f"نجح جلب {len(fetched)} عناصر من {label}")
                    break
            except Exception as e:
                print(f"تخطي {label} ({feed_url}): {e}")

        for alert in reversed(fetched):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])
                total_added += 1

        if fetched:
            status_parts.append(f"{label} ({len(fetched)})")

    # 2. تحديث قسم متوسطات الأسعار (market) من بيانات WFP على HDX
    try:
        new_market, market_period = fetch_wfp_market_prices()
        if new_market:
            # الإبقاء على الخبز المدعوم الثابت ودمجه مع الأسعار المحدثة تلقائياً
            subsidized = [m for m in data.get("market", []) if "مدعومة" in m.get("name", "")]
            data["market"] = subsidized + new_market
            status_parts.append(f"أسعار WFP ({len(new_market)} سلع - {market_period})")
            print(f"تم تحديث {len(new_market)} سلعة في قسم الأسعار")
    except Exception as e:
        print("تعذر تحديث جدول أسعار WFP (سيتم الاحتفاظ بالأسعار الحالية):", e)

    # 3. تحديث قسم التحقق من الشائعات (rumors) من منصة مسبار
    try:
        new_rumors = fetch_misbar_rumors()
        existing_claims = {r["claim"] for r in data.get("rumors", [])}
        rumors_added = 0
        for r in reversed(new_rumors):
            if r["claim"] not in existing_claims:
                data.setdefault("rumors", []).insert(0, r)
                existing_claims.add(r["claim"])
                rumors_added += 1
        data["rumors"] = data.get("rumors", [])[:15]
        if rumors_added:
            status_parts.append(f"تحققات مسبار (+{rumors_added})")
            print(f"تمت إضافة {rumors_added} تحققات جديدة من مسبار")
    except Exception as e:
        print("تعذر جلب تحققات مسبار:", e)

    # 4. فحص وتحديث بيانات نقاط التوزيع (outlets)
    outlets_count = sync_outlets_metadata(data, now_ar)
    status_parts.append(f"نقاط التوزيع ({outlets_count} نقطة)")

    # 5. جلب إشعارات تحديث بيانات HDX
    try:
        hdx_alerts, wfp_date = fetch_hdx_updates()
        for alert in reversed(hdx_alerts[:2]):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])
                total_added += 1
        if wfp_date:
            status_parts.append(f"نشرة HDX: {wfp_date}")
    except Exception as e:
        print("تعذر الاتصال بـ HDX:", e)

    data["alerts"] = data.get("alerts", [])[:15]

    if status_parts:
        data["lastSourceStatus"] = "مزامنة شاملة: " + " | ".join(status_parts)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"اكتمل التحديث الشامل -> {data['lastSourceStatus']}")


if __name__ == "__main__":
    main()
