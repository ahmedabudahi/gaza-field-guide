import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

DATA_FILE = "data.json"

MONTHS_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"
}

def format_ar_date(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return f"{dt.day} {MONTHS_AR[dt.month]} {dt.year}"
    except Exception:
        return iso_str[:10]

def fetch_ocha_reliefweb_reports():
    """جلب أحدث التقارير الرسمية حول غزة من واجهة ReliefWeb API التابعة للأمم المتحدة"""
    url = "https://api.reliefweb.int/v1/reports?appname=gaza-field-guide"
    payload = {
        "limit": 5,
        "preset": "latest",
        "fields": {
            "include": ["title", "date.created", "source.shortname", "url", "body"]
        },
        "filter": {
            "operator": "AND",
            "conditions": [
                {
                    "field": "country.iso3",
                    "value": "PSE"
                },
                {
                    "field": "source.shortname",
                    "value": ["OCHA", "WFP", "UNRWA"]
                }
            ]
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GazaFieldGuideBot/1.0"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    new_alerts = []
    for item in result.get("data", []):
        fields = item.get("fields", {})
        title = fields.get("title", "").strip()
        created = fields.get("date", {}).get("created", "")
        sources = [s.get("shortname", "") for s in fields.get("source", []) if s.get("shortname")]
        source_label = " / ".join(sources) if sources else "OCHA"
        body_raw = fields.get("body", "").strip()
        summary = (body_raw[:240] + "...") if len(body_raw) > 240 else body_raw

        if title:
            new_alerts.append({
                "title": f"[{source_label}] {title}",
                "time": format_ar_date(created),
                "body": summary or "تحديث ميداني رسمي صادر عن وكالات الأمم المتحدة العاملة في قطاع غزة."
            })
    return new_alerts

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

    status_parts = []

    # 1. جلب تحديثات تقارير OCHA / WFP / UNRWA
    try:
        fetched_alerts = fetch_ocha_reliefweb_reports()
        existing_titles = {a["title"] for a in data.get("alerts", [])}
        added_count = 0
        for alert in reversed(fetched_alerts):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])
                added_count += 1
        # الاحتفاظ بأحدث 15 نشرة فقط حتى لا يكبر حجم الملف
        data["alerts"] = data["alerts"][:15]
        status_parts.append(f"OCHA/WFP/UNRWA (جديد: {added_count})")
    except Exception as e:
        print("تعذر الاتصال بـ ReliefWeb:", e)

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

    print("تم تحديث data.json بنجاح في:", now_iso)

if __name__ == "__main__":
    main()
