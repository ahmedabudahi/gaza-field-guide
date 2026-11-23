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
    "Accept": "application/rss+xml, application/xml, text/xml, application/json, */*"
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


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["lastUpdated"] = now_iso

    existing_titles = {a["title"] for a in data.get("alerts", [])}
    status_parts = []
    total_added = 0

    # 1. جلب الأخبار والتقارير من خلاصات RSS الرسمية
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

    # 2. جلب تحديثات البيانات من HDX (WFP / OCHA)
    try:
        hdx_alerts, wfp_date = fetch_hdx_updates()
        for alert in reversed(hdx_alerts[:2]):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])
                total_added += 1
        if wfp_date:
            status_parts.append(f"نشرة أسعار WFP: {wfp_date}")
        elif hdx_alerts:
            status_parts.append(f"بيانات HDX ({len(hdx_alerts)})")
    except Exception as e:
        print("تعذر الاتصال بـ HDX:", e)

    data["alerts"] = data.get("alerts", [])[:15]

    if status_parts:
        data["lastSourceStatus"] = "تم الفحص التلقائي: " + " | ".join(status_parts)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"اكتمل التحديث (إضافات جديدة: {total_added}) -> {data['lastSourceStatus']}")


if __name__ == "__main__":
    main()
