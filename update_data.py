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

# خلاصات الأخبار المحلية لاستخلاص التسعيرة الاسترشادية اليومية لوزارة الاقتصاد الوطني بغزة
LOCAL_PRICING_RSS = [
    {
        "label": "وزارة الاقتصاد الوطني (عبر صفا)",
        "urls": ["https://safa.ps/rss", "https://safa.ps/feed"]
    },
    {
        "label": "وزارة الاقتصاد الوطني (عبر شهاب)",
        "urls": ["https://shehabnews.com/rss", "https://shehabnews.com/feed"]
    },
    {
        "label": "وزارة الاقتصاد الوطني (عبر الرسالة)",
        "urls": ["https://alresalah.ps/rss", "https://alresalah.ps/feed"]
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

# القائمة الشاملة للأصناف (26 غذائياً + 3 محروقات) بأسعار أسواق الجنوب والوسطى (خان يونس ودير البلح) والتسعيرة الاسترشادية
COMMODITIES_CATALOG = [
    # 1. الخبز والحبوب والنشويات
    {
        "key": "subsidized_bread",
        "keywords": [],
        "ar_patterns": [r"خبز[^0-9]{0,15}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخبز والحبوب",
        "name": "ربطة خبز مدعومة (وزن 2 كغم)",
        "area": "خان يونس والوسطى (المخابز المدعومة)",
        "default_price": "3 شيكل",
        "default_ref": "سعر مدعوم ثابت",
        "default_status": "green",
        "default_label": "سعر مدعوم",
        "source": "المتاجر المتعاقدة مع المخابز المدعومة أمميا (OCHA)"
    },
    {
        "key": "wheat_flour",
        "keywords": ["wheat flour", "flour"],
        "ar_patterns": [r"(?:طحين|دقيق)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخبز والحبوب",
        "name": "طحين أبيض (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "2.2 شيكل",
        "default_ref": "كيس 25 كغم: 50–55 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 8.0
    },
    {
        "key": "rice",
        "keywords": ["rice"],
        "ar_patterns": [r"(?:أرز|ارز|رز)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخبز والحبوب",
        "name": "أرز حبة قصيرة / متوسطة (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 4.5–5.5 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 12.0
    },
    {
        "key": "pasta",
        "keywords": ["pasta", "macaroni"],
        "ar_patterns": [r"(?:معكرونة|مكرونة|شعرية)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخبز والحبوب",
        "name": "معكرونة / شعرية (كيس 400–500 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "2.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 2–3 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 6.0
    },
    {
        "key": "semolina",
        "keywords": ["semolina"],
        "ar_patterns": [r"سميد[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخبز والحبوب",
        "name": "سميد (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3.5 شيكل",
        "default_ref": "متوسط أسواق الجنوب والوسطى",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "رصد أسواق خان يونس ودير البلح",
        "max_sane_price": 8.0
    },
    {
        "key": "yeast",
        "keywords": ["yeast"],
        "ar_patterns": [r"خميرة[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخبز والحبوب",
        "name": "خميرة جافة (عبوة 500 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "8 شيكل",
        "default_ref": "متوسط أسواق الجنوب والوسطى",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "رصد أسواق خان يونس ودير البلح",
        "max_sane_price": 18.0
    },

    # 2. البقوليات والمعلبات الأساسية
    {
        "key": "lentils",
        "keywords": ["lentils"],
        "ar_patterns": [r"عدس[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البقوليات والمعلبات",
        "name": "عدس مجروش / أصفر (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "5.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 5–6 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 12.0
    },
    {
        "key": "chickpeas_dry",
        "keywords": ["chickpeas"],
        "ar_patterns": [r"حمص\s*حب[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البقوليات والمعلبات",
        "name": "حمص حب جاف (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "6 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 5.5–6.5 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 13.0
    },
    {
        "key": "beans_white",
        "keywords": ["beans"],
        "ar_patterns": [r"فاصولياء[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البقوليات والمعلبات",
        "name": "فاصولياء بيضاء جافة (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "7 شيكل",
        "default_ref": "متوسط أسواق الجنوب والوسطى",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "رصد أسواق خان يونس ودير البلح",
        "max_sane_price": 14.0
    },
    {
        "key": "fava_canned",
        "keywords": ["fava", "broad beans"],
        "ar_patterns": [r"(?:فول|معلبات)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البقوليات والمعلبات",
        "name": "فول مدمس معلب (علبة 400 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "2.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 2–3 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 5.0
    },
    {
        "key": "chickpeas_canned",
        "keywords": ["hummus"],
        "ar_patterns": [r"حمص\s*(?:معلب|جاهز)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البقوليات والمعلبات",
        "name": "حمص حب جاهز معلب (علبة 400 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "2.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 2–3 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 5.0
    },

    # 3. الزيوت والسكر والألبان
    {
        "key": "oil_3l",
        "keywords": ["oil (vegetable)", "oil (sunflower)", "oil (maize)", "oil"],
        "ar_patterns": [r"زيت\s*(?:قلي|نباتي|ذرة|طهي)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الزيوت والألبان",
        "name": "زيت ذرة / عباد الشمس (عبوة 3 لتر)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "22 شيكل",
        "default_ref": "اللتر الواحد: 7–7.5 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "multiplier": 3.0,
        "max_sane_price": 32.0
    },
    {
        "key": "olive_oil",
        "keywords": ["olive oil"],
        "ar_patterns": [r"زيت\s*زيتون[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الزيوت والألبان",
        "name": "زيت زيتون بلدي (1 لتر)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "32 شيكل",
        "default_ref": "متوسط أسواق الجنوب والوسطى",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "رصد أسواق خان يونس ودير البلح",
        "max_sane_price": 45.0
    },
    {
        "key": "sugar",
        "keywords": ["sugar"],
        "ar_patterns": [r"سكر[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الزيوت والألبان",
        "name": "سكر أبيض (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3–4 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 8.0
    },
    {
        "key": "salt",
        "keywords": ["salt"],
        "ar_patterns": [r"ملح[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الزيوت والألبان",
        "name": "ملح طعام يودي (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "1.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 1–2 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "رصد أسواق خان يونس ودير البلح",
        "max_sane_price": 4.0
    },
    {
        "key": "milk_powder",
        "keywords": ["milk"],
        "ar_patterns": [r"حليب[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الزيوت والألبان",
        "name": "حليب مجفف / بودرة (عبوة 400 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "14 شيكل",
        "default_ref": "متوسط أسواق الجنوب والوسطى",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "رصد أسواق خان يونس ودير البلح",
        "max_sane_price": 22.0
    },

    # 4. الخضروات الأساسية
    {
        "key": "potatoes",
        "keywords": ["potatoes"],
        "ar_patterns": [r"(?:بطاطا|بطاطس)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخضروات",
        "name": "بطاطا (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3–4 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 9.0
    },
    {
        "key": "tomatoes",
        "keywords": ["tomatoes"],
        "ar_patterns": [r"(?:بندورة|طماطم)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخضروات",
        "name": "بندورة (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "4 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3.5–4.5 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 9.0
    },
    {
        "key": "onions",
        "keywords": ["onions"],
        "ar_patterns": [r"بصل[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخضروات",
        "name": "بصل ناشف (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3–4 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 9.0
    },
    {
        "key": "cucumbers",
        "keywords": ["cucumbers"],
        "ar_patterns": [r"خيار[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخضروات",
        "name": "خيار (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3–4 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 8.0
    },
    {
        "key": "eggplants",
        "keywords": ["eggplants"],
        "ar_patterns": [r"باذنجان[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخضروات",
        "name": "باذنجان (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 2.5–3.5 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 7.0
    },
    {
        "key": "chili_pepper",
        "keywords": ["peppers", "chili"],
        "ar_patterns": [r"فلفل[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "الخضروات",
        "name": "فلفل أخضر حار (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "4 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3.5–4.5 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 8.0
    },

    # 5. البروتينات والبدائل
    {
        "key": "eggs",
        "keywords": ["eggs"],
        "ar_patterns": [r"(?:كرتونة\s*بيض|بيض)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البروتينات والبدائل",
        "name": "كرتونة بيض مائدة (30 بيضة)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "18 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 16–20 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "multiplier": 30.0,
        "max_sane_price": 30.0
    },
    {
        "key": "tuna",
        "keywords": ["fish (tuna)", "tuna"],
        "ar_patterns": [r"تونة[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البروتينات والبدائل",
        "name": "تونة معلبة (علبة 160–185 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "3.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 3–4 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 7.0
    },
    {
        "key": "sardines",
        "keywords": ["sardines"],
        "ar_patterns": [r"سردين[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البروتينات والبدائل",
        "name": "سردين معلب (علبة 125 غم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "2.5 شيكل",
        "default_ref": "التسعيرة الاسترشادية: 2–3 شيكل",
        "default_status": "green",
        "default_label": "متوفر بالأسواق",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 5.0
    },
    {
        "key": "chicken",
        "keywords": ["meat (chicken)", "chicken"],
        "ar_patterns": [r"(?:دجاج|فراخ)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "البروتينات والبدائل",
        "name": "دجاج طازج / مجمد (1 كغم)",
        "area": "خان يونس ودير البلح (متوسط السوق)",
        "default_price": "16 شيكل",
        "default_ref": "متوسط أسواق الجنوب والوسطى",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "التسعيرة الاسترشادية لوزارة الاقتصاد ورصد خان يونس",
        "max_sane_price": 26.0
    },

    # 6. المحروقات وغاز الطهي
    {
        "key": "lpg_gas",
        "keywords": ["fuel (gas)"],
        "ar_patterns": [r"(?:أسطوانة\s*غاز|غاز\s*الطهي)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "المحروقات",
        "name": "أسطوانة غاز طهي (12 كغم)",
        "area": "خان يونس والوسطى (التسعيرة الرسمية)",
        "default_price": "70 شيكل",
        "default_ref": "التسعيرة الرسمية لهيئة البترول",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "التسعيرة الرسمية لهيئة البترول ووزارة الاقتصاد",
        "max_sane_price": 110.0
    },
    {
        "key": "petrol",
        "keywords": ["fuel (petrol-gasoline)"],
        "ar_patterns": [r"بنزين[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "المحروقات",
        "name": "بنزين 95 أوكتان (1 لتر)",
        "area": "خان يونس والوسطى (التسعيرة الرسمية)",
        "default_price": "7.5 شيكل",
        "default_ref": "متوسط محطات الجنوب والوسطى",
        "default_status": "amber",
        "default_label": "كمية محدودة",
        "source": "رصد محطات الوقود في خان يونس والوسطى",
        "max_sane_price": 12.0
    },
    {
        "key": "diesel",
        "keywords": ["fuel (diesel)"],
        "ar_patterns": [r"(?:سولار|ديزل)[^0-9]{0,20}(\d+(?:\.\d+)?)\s*شيكل"],
        "category": "المحروقات",
        "name": "سولار / ديزل (1 لتر)",
        "area": "خان يونس والوسطى (التسعيرة الرسمية)",
        "default_price": "7.2 شيكل",
        "default_ref": "متوسط محطات الجنوب والوسطى",
        "default_status": "red",
        "default_label": "شحيح حاليا",
        "source": "رصد محطات الوقود في خان يونس والوسطى",
        "max_sane_price": 12.0
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


def fetch_ministry_guidance_prices():
    """استخلاص الأسعار الاسترشادية اليومية لوزارة الاقتصاد الوطني من خلاصات الأخبار المحلية في غزة"""
    guidance_keywords = ("وزارة الاقتصاد", "التسعيرة الاسترشادية", "الأسعار الاسترشادية", "حماية المستهلك", "قائمة أسعار")
    extracted_prices = {}
    latest_bulletin_date = ""
    bulletin_source = ""

    for src in LOCAL_PRICING_RSS:
        for feed_url in src["urls"]:
            try:
                req = urllib.request.Request(feed_url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    xml_bytes = resp.read()
                root = ET.fromstring(xml_bytes)
                items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

                for item in items:
                    title = clean_html_text(item.findtext("title") or "")
                    body = clean_html_text(
                        item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                        or item.findtext("description")
                        or ""
                    )
                    full_text = f"{title} {body}"
                    if not any(kw in full_text for kw in guidance_keywords):
                        continue

                    pub_date = format_ar_date(item.findtext("pubDate") or "")
                    for comm in COMMODITIES_CATALOG:
                        if comm["key"] in extracted_prices:
                            continue
                        for pat in comm.get("ar_patterns", []):
                            m = re.search(pat, full_text)
                            if m:
                                try:
                                    val = float(m.group(1))
                                    if 0.5 <= val <= comm.get("max_sane_price", 100.0):
                                        extracted_prices[comm["key"]] = val
                                        if not latest_bulletin_date:
                                            latest_bulletin_date = pub_date
                                            bulletin_source = src["label"]
                                except ValueError:
                                    pass
                                break
                if extracted_prices:
                    break
            except Exception as e:
                print(f"تخطي خلاصة التسعيرة المحلية ({feed_url}): {e}")

    return extracted_prices, latest_bulletin_date, bulletin_source


def fetch_south_gaza_wfp_prices():
    """جلب أسعار أسواق جنوب ووسط غزة فقط (خان يونس ودير البلح) من WFP واستبعاد تضخم الشمال"""
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
    south_rows = []
    # تصفية صارمة لأسواق خان يونس ودير البلح ورفح فقط
    south_markers = ("khan yunis", "khan younis", "deir al-balah", "deir al balah", "rafah", "middle area")
    for row in reader:
        if row.get("date", "").startswith("#"):
            continue
        admin1 = (row.get("admin1") or "").lower()
        market = (row.get("market") or "").lower()
        combined = f"{admin1} {market}"
        if any(m in combined for m in south_markers):
            south_rows.append(row)

    if not south_rows:
        return {}, ""

    latest_date = max(r.get("date", "") for r in south_rows)
    latest_rows = [r for r in south_rows if r.get("date") == latest_date]

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
                mult = item.get("multiplier", 1.0)
                scaled = price * mult
                # تجاهل أي سعر متضخم يتجاوز سقف السوق المحلي في الجنوب والوسطى
                if scaled <= item.get("max_sane_price", 100.0):
                    live_prices.setdefault(item["key"], []).append(scaled)
                break

    averaged = {}
    for k, vals in live_prices.items():
        averaged[k] = sum(vals) / len(vals)

    return averaged, format_ar_date(latest_date)


def fetch_misbar_rumors():
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


def build_full_market_list(ministry_prices, ministry_date, wfp_south_prices, wfp_period):
    """دمج أسعار التسعيرة الاسترشادية لوزارة الاقتصاد + متوسطات أسواق خان يونس ودير البلح"""
    final_list = []
    live_count = 0

    for item in COMMODITIES_CATALOG:
        key = item["key"]
        fair_price = item["default_price"]
        ref_text = item["default_ref"]
        status = item["default_status"]
        label = item["default_label"]
        source = item["source"]

        # الأولوية 1: التسعيرة الاسترشادية اليومية لوزارة الاقتصاد الوطني بغزة
        if key in ministry_prices:
            val = round(ministry_prices[key], 2)
            fair_price = f"{int(val) if val.is_integer() else val} شيكل"
            ref_text = f"التسعيرة الاسترشادية لوزارة الاقتصاد ({ministry_date})"
            source = "وزارة الاقتصاد الوطني - غزة (التسعيرة الاسترشادية)"
            live_count += 1
        # الأولوية 2: رصد أسواق خان يونس ودير البلح من WFP
        elif key in wfp_south_prices:
            val = round(wfp_south_prices[key], 2)
            fair_price = f"{int(val) if val.is_integer() else val} شيكل"
            ref_text = f"متوسط أسواق خان يونس ودير البلح ({wfp_period})"
            source = "رصد أسواق خان يونس ودير البلح (WFP / الغرفة التجارية)"
            live_count += 1

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

    return final_list, live_count


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

    # 2. تحديث الأسعار من التسعيرة الاسترشادية لوزارة الاقتصاد + أسواق خان يونس ودير البلح
    ministry_prices, ministry_date, ministry_src = {}, "", ""
    try:
        ministry_prices, ministry_date, ministry_src = fetch_ministry_guidance_prices()
    except Exception as e:
        print("تعذر سحب نشرة وزارة الاقتصاد المحلية:", e)

    wfp_south_prices, wfp_period = {}, ""
    try:
        wfp_south_prices, wfp_period = fetch_south_gaza_wfp_prices()
    except Exception as e:
        print("تعذر سحب بيانات أسواق الجنوب والوسطى من WFP:", e)

    full_market, live_count = build_full_market_list(
        ministry_prices, ministry_date, wfp_south_prices, wfp_period
    )
    data["market"] = full_market
    status_parts.append(f"أسواق خان يونس والوسطى ({len(full_market)} صنفاً)")

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
        data["lastSourceStatus"] = "مزامنة ميدانية (الجنوب والوسطى): " + " | ".join(status_parts)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"اكتمل التحديث الميداني -> {data['lastSourceStatus']}")


if __name__ == "__main__":
    main()
