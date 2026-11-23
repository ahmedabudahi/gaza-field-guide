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

RSS_SOURCES = [
    {
        "label": "OCHA",
        "urls": ["https://www.ochaopt.org/rss.xml"],
        "limit": 4,
        "gaza_only": False
    },
    {
        "label": "UNRWA",
        "urls": [
            "https://www.unrwa.org/ar/news-reports/rss.xml",
            "https://www.unrwa.org/news-reports/rss.xml"
        ],
        "limit": 4,
        "gaza_only": True
    }
]


def clean_html_text(raw_text):
    """إزالة وسوم HTML والمسافات الزائدة من نصوص RSS"""
    if not raw_text:
        return ""
    unescaped = html.unescape(raw_text)
    no_tags = re.sub(r"<[^>]+>", " ", unescaped)
    return re.sub(r"\s+", " ", no_tags).strip()


def format_ar_date(date_str):
    """تحويل تواريخ RSS أو ISO إلى صيغة عربية مقروءة"""
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
    """قراءة خلاصة RSS واستخراج أحدث التقارير والبيانات الرسمية"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GazaFieldGuideBot/1.0)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        xml_bytes = resp.read()

    root = ET.fromstring(xml_bytes)
    items = root.findall(".//item")
    if not items:
        # دعم صيغة Atom في حال استخدامها
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    extracted = []
    gaza_keywords = ("غزة", "خان يونس", "رفح", "الوسطى", "دير البلح", "النصيرات", "gaza", "khan younis", "rafah")

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


def check_hdx_wfp_dataset():
    """فحص تاريخ آخر تحديث لبيانات أسعار الغذاء في فلسطين على منصة HDX"""
    url = "https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-state-of-palestine"
    req = urllib.request.Request(url, headers={"User-Agent": "GazaFieldGuideBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    last_mod = result.get("result", {}).get("metadata_modified", "")
    return format_ar_date(last_mod) if last_mod else ""


def main():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["lastUpdated"] = now_iso

    existing_titles = {a["title"] for a in data.get("alerts", [])}
    status_parts = []

    # 1. جلب أحدث التقارير من خلاصات RSS الرسمية لـ OCHA والأونروا
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
                    break
            except Exception as e:
                print(f"تعذر قراءة خلاصة {label} من {feed_url}:", e)

        added = 0
        for alert in reversed(fetched):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])
                added += 1

        if fetched:
            status_parts.append(f"{label} RSS (جديد: {added})")

    # الاحتفاظ بأحدث 15 تقريراً في القائمة
    data["alerts"] = data.get("alerts", [])[:15]

    # 2. التحقق من تحديث بيانات أسعار WFP على منصة HDX
    try:
        hdx_date = check_hdx_wfp_dataset()
        if hdx_date:
            status_parts.append(f"نشرة أسعار WFP: {hdx_date}")
    except Exception as e:
        print("تعذر الاتصال بـ HDX:", e)

    if status_parts:
        data["lastSourceStatus"] = "تم الفحص التلقائي: " + " | ".join(status_parts)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("تم تحديث data.json بنجاح:", data["lastSourceStatus"])


if __name__ == "__main__":
    main()
