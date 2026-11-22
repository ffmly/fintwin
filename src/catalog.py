from __future__ import annotations

from copy import deepcopy


WILAYAS = [
    "الجزائر", "وهران", "قسنطينة", "سطيف", "البليدة", "باتنة", "عنابة",
    "تيزي وزو", "بجاية", "تلمسان", "بسكرة", "الجلفة", "ورقلة", "غرداية",
    "مستغانم", "الشلف", "سيدي بلعباس", "تيارت", "بومرداس", "تيبازة",
]


ACTIVITIES = {
    "متجر إلكتروني": {
        "key": "ecommerce",
        "icon": "🛍️",
        "defaults": {
            "price": 6500.0,
            "unit_cost": 3000.0,
            "monthly_fixed_costs": 70000.0,
            "monthly_reach": 2500,
            "delivery_price": 600.0,
            "delivery_cost": 550.0,
            "return_rate": 0.10,
            "trust_score": 65,
            "experience_score": 62,
            "convenience_score": 68,
            "response_minutes": 20,
            "payment_methods": ["الدفع عند الاستلام", "بريدي موب"],
            "free_delivery": False,
        },
    },
    "متجر ملابس محلي": {
        "key": "retail",
        "icon": "👕",
        "defaults": {
            "price": 4500.0,
            "unit_cost": 2200.0,
            "monthly_fixed_costs": 140000.0,
            "monthly_reach": 900,
            "trust_score": 70,
            "experience_score": 72,
            "convenience_score": 60,
            "fitting_rooms": True,
            "clear_prices": True,
            "parking": False,
            "street_type": "شارع تجاري",
            "payment_methods": ["كاش", "بطاقة"],
        },
    },
    "كافيه": {
        "key": "cafe",
        "icon": "☕",
        "defaults": {
            "price": 350.0,
            "unit_cost": 120.0,
            "monthly_fixed_costs": 240000.0,
            "monthly_reach": 1800,
            "trust_score": 74,
            "experience_score": 76,
            "convenience_score": 62,
            "wifi": True,
            "parking": False,
            "atmosphere": "شبابي وعصري",
            "street_type": "وسط المدينة",
            "payment_methods": ["كاش", "بريدي موب"],
        },
    },
    "مطعم / Fast Food": {
        "key": "restaurant",
        "icon": "🍔",
        "defaults": {
            "price": 900.0,
            "unit_cost": 380.0,
            "monthly_fixed_costs": 320000.0,
            "monthly_reach": 2200,
            "trust_score": 76,
            "experience_score": 70,
            "convenience_score": 68,
            "delivery": True,
            "waiting_minutes": 15,
            "hygiene_score": 82,
            "payment_methods": ["كاش", "بريدي موب"],
        },
    },
    "خدمات / Freelance": {
        "key": "service",
        "icon": "🧰",
        "defaults": {
            "price": 8000.0,
            "unit_cost": 1500.0,
            "monthly_fixed_costs": 50000.0,
            "monthly_reach": 220,
            "trust_score": 68,
            "experience_score": 75,
            "convenience_score": 72,
            "online_booking": True,
            "response_minutes": 30,
            "payment_methods": ["كاش", "بريدي موب", "تحويل بنكي"],
        },
    },
    "مشروع آخر": {
        "key": "other",
        "icon": "◇",
        "defaults": {
            "price": 3000.0,
            "unit_cost": 1200.0,
            "monthly_fixed_costs": 80000.0,
            "monthly_reach": 700,
            "trust_score": 65,
            "experience_score": 65,
            "convenience_score": 65,
            "payment_methods": ["كاش", "بريدي موب"],
        },
    },
}


PAYMENT_METHODS = [
    "كاش",
    "الدفع عند الاستلام",
    "بريدي موب",
    "بطاقة",
    "تحويل بنكي",
]


PROVIDER_MODELS = {
    "Hugging Face Inference": ["Qwen/Qwen3.5-9B", "Qwen/Qwen3.5-4B", "Qwen/Qwen3-4B-Thinking-2507"],
    "DeepSeek الرسمي": ["deepseek-flash", "deepseek-v4-pro"],
}


def activity_defaults(label: str) -> dict:
    return deepcopy(ACTIVITIES[label]["defaults"])


def activity_key(label: str) -> str:
    return ACTIVITIES[label]["key"]

