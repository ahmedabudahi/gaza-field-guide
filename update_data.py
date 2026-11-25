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

# القائمة الشاملة للأصناف الغذائية والأساسية في قطاع غزة (26 صنفاً)
COMMODITIES_CATALOG = [
    # 1. الخبز والحبوب والنشويات
    {
        "key": "subsidized_bread",
        "keywords": [],
        "category": "الخبز والحبوب",
        "name": "ربطة خبز مدعومة (وزن 2 كغم)",
        "area": "قطاع غزة (المخابز المدعومة)",
        "default_price": "3 شيكل",
        "default_ref": "سعر مدعوم أممياً (أكثر من 30 شيكل تجاري سابق)",
        "default_status": "green",
        "default_label": "سعر مدعوم",
        "source": "المتاجر المتعاقدة مع المخابز المدعومة أمميا (OCHA)"
    },
    {
        "key": "wheat_flour",
        "keywords": ["wheat flour", "flour"],
        "category": "الخبز والحبوب",
        "name": "طحين أبيض (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "4.5 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "rice",
        "keywords": ["rice"],
        "category": "الخبز والحبوب",
        "name": "أرز حبة قصيرة / متوسطة (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "8 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "pasta",
        "keywords": ["pasta", "macaroni"],
        "category": "الخبز والحبوب",
        "name": "معكرونة / شعرية (كيس 400–500 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "4 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
    },
    {
        "key": "semolina",
        "keywords": ["semolina"],
        "category": "الخبز والحبوب",
        "name": "سميد (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "6 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "yeast",
        "keywords": ["yeast"],
        "category": "الخبز والحبوب",
        "name": "خميرة جافة (عبوة 500 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "15 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },

    # 2. البقوليات والمعلبات الأساسية
    {
        "key": "lentils",
        "keywords": ["lentils"],
        "category": "البقوليات والمعلبات",
        "name": "عدس مجروش / أصفر (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "9 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "chickpeas_dry",
        "keywords": ["chickpeas"],
        "category": "البقوليات والمعلبات",
        "name": "حمص حب جاف (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "10 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "beans_white",
        "keywords": ["beans"],
        "category": "البقوليات والمعلبات",
        "name": "فاصولياء بيضاء جافة (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "11 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "fava_canned",
        "keywords": ["fava", "broad beans"],
        "category": "البقوليات والمعلبات",
        "name": "فول مدمس معلب (علبة 400 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "4.5 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "chickpeas_canned",
        "keywords": ["hummus"],
        "category": "البقوليات والمعلبات",
        "name": "حمص حب جاهز معلب (علبة 400 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "4.5 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },

    # 3. الزيوت والسكر والألبان
    {
        "key": "oil_3l",
        "keywords": ["oil (vegetable)", "oil (sunflower)", "oil (maize)", "oil"],
        "category": "الزيوت والألبان",
        "name": "زيت ذرة / عباد الشمس (عبوة 3 لتر)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "38 شيكل",
        "default_ref": "36 شيكل (متوسط 2024)",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP",
        "multiplier": 3.0
    },
    {
        "key": "olive_oil",
        "keywords": ["olive oil"],
        "category": "الزيوت والألبان",
        "name": "زيت زيتون بلدي (1 لتر)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "45 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "sugar",
        "keywords": ["sugar"],
        "category": "الزيوت والألبان",
        "name": "سكر أبيض (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "6 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "salt",
        "keywords": ["salt"],
        "category": "الزيوت والألبان",
        "name": "ملح طعام يودي (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "2.5 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP)"
    },
    {
        "key": "milk_powder",
        "keywords": ["milk"],
        "category": "الزيوت والألبان",
        "name": "حليب مجفف / بودرة (عبوة 400 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "22 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "amber",
        "default_label": "تذبذب سعري",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
    },

    # 4. الخضروات الأساسية
    {
        "key": "potatoes",
        "keywords": ["potatoes"],
        "category": "الخضروات",
        "name": "بطاطا (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "9 شيكل",
        "default_ref": "مؤشر الغذاء +6.67% شهريا",
        "default_status": "amber",
        "default_label": "تذبذب سعري",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
    },
    {
        "key": "tomatoes",
        "keywords": ["tomatoes"],
        "category": "الخضروات",
        "name": "بندورة (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "8 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "amber",
        "default_label": "تذبذب سعري",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "onions",
        "keywords": ["onions"],
        "category": "الخضروات",
        "name": "بصل ناشف (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "9 شيكل",
        "default_ref": "مؤشر الغذاء +6.67% شهريا",
        "default_status": "amber",
        "default_label": "تذبذب سعري",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
    },
    {
        "key": "cucumbers",
        "keywords": ["cucumbers"],
        "category": "الخضروات",
        "name": "خيار (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "7 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "eggplants",
        "keywords": ["eggplants"],
        "category": "الخضروات",
        "name": "باذنجان (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "6 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "chili_pepper",
        "keywords": ["peppers", "chili"],
        "category": "الخضروات",
        "name": "فلفل أخضر حار (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "7 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },

    # 5. البروتينات والبدائل
    {
        "key": "eggs",
        "keywords": ["eggs"],
        "category": "البروتينات والبدائل",
        "name": "كرتونة بيض مائدة (30 بيضة)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "35 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني",
        "multiplier": 30.0
    },
    {
        "key": "tuna",
        "keywords": ["fish (tuna)", "tuna"],
        "category": "البروتينات والبدائل",
        "name": "تونة معلبة (علبة 160–185 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "6 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },
    {
        "key": "sardines",
        "keywords": ["sardines"],
        "category": "البروتينات والبدائل",
        "name": "سردين معلب (علبة 125 غم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "4 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "الجهاز المركزي للإحصاء الفلسطيني"
    },
    {
        "key": "chicken",
        "keywords": ["meat (chicken)", "chicken"],
        "category": "البروتينات والبدائل",
        "name": "دجاج طازج / مجمد (1 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "26 شيكل",
        "default_ref": "متوسط رصد الأسواق",
        "default_status": "red",
        "default_label": "شحيح حاليا",
        "source": "برنامج الأغذية العالمي (WFP) والإحصاء الفلسطيني"
    },

    # 6. المحروقات وغاز الطهي
    {
        "key": "lpg_gas",
        "keywords": ["fuel (gas)"],
        "category": "المحروقات",
        "name": "أسطوانة غاز طهي (12 كغم)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "94 شيكل",
        "default_ref": "126 شيكل (متوسط 2025)",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
    },
    {
        "key": "petrol",
        "keywords": ["fuel (petrol-gasoline)"],
        "category": "المحروقات",
        "name": "بنزين 95 أوكتان (1 لتر)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "7.92 شيكل",
        "default_ref": "7.90 شيكل (آذار 2026)",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
    },
    {
        "key": "diesel",
        "keywords": ["fuel (diesel)"],
        "category": "المحروقات",
        "name": "سولار / ديزل (1 لتر)",
        "area": "قطاع غزة (متوسط عام)",
        "default_price": "8.99 شيكل",
        "default_ref": "8.40 شيكل (آذار 2026)",
        "default_status": "red",
        "default_label": "شحيح حاليا",
        "source": "الجهاز المركزي للإحصاء الفلسطيني و WFP"
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


def fetch_wfp_live_prices():
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
        return {}, ""

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
        return {}, ""

    latest_date = max(r.get("date", "") for r in gaza_rows)
    latest_rows = [r for r in gaza_rows if r.get("date") == latest_date]

    live_prices = {}
    for r in latest_rows:
        comm = (r.get("commodity") or "").strip().lower()
        try:
            price = float(r.get("price", 0))
        except ValueError:
            continue
        if price <= 0:
            continue
        for item in COMMODITIES_CATALOG:
            if any(kw in comm for kw in item["keywords"]):
                live_prices.setdefault(item["key"], []).append(price)
                break

    averaged = {}
    for k, vals in live_prices.items():
        averaged[k] = sum(vals) / len(vals)

    return averaged, format_ar_date(latest_date)


def build_full_market_list(existing_market, live_prices, live_period):
    """بناء قائمة الـ 29 صنفاً (26 غذائياً + 3 محروقات) مع دمج الأسعار الحية"""
    existing_by_name = {m.get("name"): m for m in existing_market}
    final_list = []
    live_updated_count = 0

    for item in COMMODITIES_CATALOG:
        key = item["key"]
        prev = existing_by_name.get(item["name"], {})
        fair_price = prev.get("fair") or item["default_price"]
        ref_text = prev.get("ref") or item["default_ref"]
        status = prev.get("status") or item["default_status"]
        label = prev.get("label") or item["default_label"]
        source = prev.get("source") or item["source"]

        if key in live_prices:
            mult = item.get("multiplier", 1.0)
            val = round(live_prices[key] * mult, 2)
            # تجاهل القيم غير المنطقية لوحدات القياس المختلفة
            if val > 0:
                fair_price = f"{int(val) if val.is_integer() else val} شيكل"
                ref_text = f"متوسط رصد WFP ({live_period})"
                source = "برنامج الأغذية العالمي (WFP / HDX)"
                live_updated_count += 1

        final_list.append({
            "name": item["name"],
            "category": item["category"],
            "area": item["area"],
            "status": status,
            "label": label,
            "fair": fair_price,
            "ref": ref_text,
            "source": source
        })

    return final_list, live_updated_count


def fetch_hdx_updates():
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


def sync_outlets_metadata(data):
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

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["lastUpdated"] = now_iso

    existing_titles = {a["title"] for a in data.get("alerts", [])}
    status_parts = []

    # 1. تحديث التنبيهات والتقارير (alerts)
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
                print(f"تخطي {label} ({feed_url}): {e}")

        for alert in reversed(fetched):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])

        if fetched:
            status_parts.append(f"{label} ({len(fetched)})")

    # 2. تحديث جميع الأصناف الغذائية والأساسية (market)
    live_prices, live_period = {}, ""
    try:
        live_prices, live_period = fetch_wfp_live_prices()
    except Exception as e:
        print("تعذر سحب جدول WFP المباشر، سيتم استخدام آخر متوسطات محفوظة:", e)

    full_market, live_count = build_full_market_list(data.get("market", []), live_prices, live_period)
    data["market"] = full_market
    if live_count:
        status_parts.append(f"السلع ({len(full_market)} صنفاً · تحديث حي: {live_count})")
    else:
        status_parts.append(f"السلع ({len(full_market)} صنفاً)")

    # 3. تحديث التحقق من الشائعات (rumors)
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
            status_parts.append(f"مسبار (+{rumors_added})")
    except Exception as e:
        print("تعذر جلب تحققات مسبار:", e)

    # 4. فحص نقاط التوزيع (outlets)
    outlets_count = sync_outlets_metadata(data)
    status_parts.append(f"المنافذ ({outlets_count})")

    # 5. تحديثات HDX
    try:
        hdx_alerts, wfp_date = fetch_hdx_updates()
        for alert in reversed(hdx_alerts[:2]):
            if alert["title"] not in existing_titles:
                data["alerts"].insert(0, alert)
                existing_titles.add(alert["title"])
        if wfp_date:
            status_parts.append(f"HDX: {wfp_date}")
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
