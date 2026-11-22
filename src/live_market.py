from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from .catalog import ACTIVITIES, activity_key
from .personas import Persona, generate_personas

"""
Fintwin Live Market visual adapter.

This module is deliberately downstream of the decision engine. It never decides
whether a persona buys; it translates existing simulation decisions into a
deterministic, normalized event timeline, structured factor-based explanations,
and consistent financial and behavioral metrics for the visual layer.
"""

DATASET_VERSION = "fintwin-live-market-dataset-2"
ADAPTER_VERSION = "2.0.0"
DEFAULT_VISIBLE = 22
MAX_VISIBLE = 24

ACTIVITY_LABELS = {
    "cafe": "كافيه",
    "restaurant": "مطعم / Fast Food",
    "retail": "متجر ملابس محلي",
    "ecommerce": "متجر إلكتروني",
    "service": "خدمات / Freelance",
}

# Centralized Arabic translation map for internal technical states (Section 7)
STATE_TRANSLATIONS = {
    "unexposed": "لم يصل بعد",
    "noticed": "لاحظ المشروع",
    "approaching": "يقترب من المشروع",
    "searching_parking": "يبحث عن موقف",
    "parking_left": "غادر لعدم وجود موقف",
    "inside": "داخل المشروع",
    "entered": "دخل المشروع",
    "browsing": "يتصفح القائمة والخيارات",
    "comparing": "يدرس العرض ويقارن الأسعار",
    "checking_price": "يقارن الأسعار",
    "queueing": "ينتظر في الطابور",
    "waiting": "ينتظر",
    "buying": "ينفّذ عملية الشراء",
    "purchasing": "ينفّذ عملية الشراء",
    "purchased": "أتم الشراء",
    "paying": "يدفع",
    "sitting": "يستخدم الخدمة",
    "using_service": "يستخدم الخدمة",
    "booking": "يحجز موعداً",
    "in_service": "في مرحلة تقديم الخدمة",
    "returned": "زبون عائد للمشروع",
    "repeat": "زبون دائم",
    "abandoned": "تراجع عن الشراء",
    "abandoning": "تراجع عن الشراء",
    "left": "يغادر",
    "leaving": "يغادر",
    "satisfied": "راضٍ عن التجربة",
    "cancelled": "ألغى الموعد",
}

def translate_state(state: str) -> str:
    """Safe lookup for internal state values into natural user-facing Arabic."""
    return STATE_TRANSLATIONS.get(str(state or "").strip(), str(state or ""))

EVENT_LABELS = {
    "noticed": "لاحظ المشروع من الشارع",
    "noticed_business": "لاحظ المشروع من الشارع",
    "passed_without_entering": "مرّ دون دخول",
    "approached": "اقترب من المدخل",
    "parking_unavailable": "لم يجد موقفاً متاحاً",
    "entered": "دخل المقهى",
    "entered_product_page": "فتح صفحة العرض",
    "viewed_service": "اطلع على تفاصيل الخدمة",
    "checked_products": "تفقّد المنتجات المعروضة",
    "checked_menu": "طالع قائمة الأسعار",
    "compared_price": "قارن الأسعار مع ميزانيته",
    "waited": "انتظر الخدمة",
    "waited_in_queue": "انضم إلى طابور الانتظار",
    "purchased": "أتم الطلب والدفع",
    "chose_payment": "أكد وسيلة الدفع",
    "received_order": "استلم الطلب من نقطة الاستلام",
    "sat_at_table": "جلس عند الطاولة",
    "stayed_for_wifi": "جلس في منطقة Wi-Fi للعمل",
    "left_due_to_price": "تراجع بسبب ملاءمة السعر",
    "left_due_to_parking": "غادر لتعذر العثور على موقف",
    "left_due_to_payment": "تراجع لعدم توفر وسيلة الدفع",
    "left_due_to_waiting": "غادر بسبب طول مدة الانتظار",
    "left_due_to_unavailable_size": "تراجع لعدم توفر المقاس/الطلب",
    "lost_trust": "تراجع لعدم كفاية إشارات الثقة",
    "abandoned": "غادر دون إتمام الشراء",
    "returned_later": "عاد كزبون معتاد",
    "repeat_customer": "أكد ولاءه كزبون متكرر",
    "added_to_cart": "أضاف إلى سلة التسوق",
    "checked_payment_options": "راجع خيارات الدفع المتاحة",
    "checked_trust": "راجع تقييمات وضمانات المشروع",
    "checked_delivery": "راجع شروط التوصيل",
    "abandoned_due_to_delivery": "تراجع بسبب تكلفة/مدة التوصيل",
    "delivery": "مرحلة التوصيل",
    "received": "استلم الطلب",
    "booked": "حجز الموعد",
    "reception": "وصل لمقر الاستقبال",
    "service_started": "بدأت مرحلة تقديم الخدمة",
    "follow_up": "متابعة ما بعد الخدمة",
    "cancelled": "ألغى الحجز",
}

INSIDE_STATES = {
    "inside", "browsing", "comparing", "queueing", "waiting", "buying",
    "purchased", "using_service", "booking", "in_service", "sitting",
}
LEAVING_STATES = {"left", "abandoned", "cancelled", "parking_left"}
BUYING_STATES = {"purchased", "repeat"}

LOSS_LABELS = {
    "parking": "خسائر بسبب موقف السيارة",
    "price": "خسائر بسبب السعر",
    "payment": "خسائر بسبب خيارات الدفع",
    "waiting": "خسائر بسبب الانتظار",
    "trust": "خسائر بسبب الثقة",
    "product": "خسائر بسبب توفّر المنتج/المقاس",
    "delivery": "خسائر بسبب التوصيل",
    "relevance": "خسائر بسبب ضعف الملاءمة",
}

METRIC_DEFINITIONS = {
    "purchase_intent_pct": {
        "title": "نية الشراء المقدّرة",
        "description": "النسبة التقديرية للشخصيات التي أبدت استعداداً للشراء بناءً على ملاءمة العرض ومحاكاة السلوك.",
        "formula": "متوسط احتمالية الشراء عبر لوحة الشخصيات الممثلة في المحاكاة",
        "source": "محرك محاكاة الشخصيات الاصطناعية (Synthetic Panel)",
        "kind": "تقديري (Estimated)",
    },
    "expected_orders": {
        "title": "الطلبات المتوقعة",
        "description": "تقدير الطلبات الشهرية قبل المرتجعات بعد تطبيق معامِل التحويل الميداني.",
        "formula": "الوصول الشهري × نية الشراء × معامل التحويل الميداني للنشاط",
        "source": "محسوب من مدخلات الوصول وفرضيات النشاط التجاري",
        "kind": "محسوب (Calculated)",
    },
    "expected_revenue_dzd": {
        "title": "الإيراد المتوقع",
        "description": "إجمالي الإيرادات المالية المقدرة شهرياً من مبيعات المنتجات والخدمات.",
        "formula": "الطلبات المتوقعة × (1 − نسبة المرتجعات) × متوسط قيمة الطلب شاملاً إيراد التوصيل",
        "source": "محسوب رياضياً من حجم الطلبات وقائمة الأسعار",
        "kind": "محسوب (Calculated)",
    },
    "average_order_value_dzd": {
        "title": "متوسط قيمة الطلب",
        "description": "القيمة المالية التقديرية للطلب الواحد متضمنة سعر المنتج وإيراد التوصيل إن وجد.",
        "formula": "سعر المنتج المرجح + إيراد التوصيل المباشر",
        "source": "قائمة المنتجات وأسعار المشروع المدخلة",
        "kind": "محسوب (Calculated)",
    },
    "contribution_margin_dzd": {
        "title": "هامش المساهمة للطلب",
        "description": "ما يتبقى من قيمة الطلب الواحد بعد خصم التكاليف المباشرة وعمولة الدفع لتغطية التكاليف الثابتة.",
        "formula": "متوسط قيمة الطلب - التكلفة المباشرة للوحدة - عمولة بوابات الدفع",
        "source": "بيانات التكاليف المباشرة للمنتج ورسوم المعاملات",
        "kind": "محسوب (Calculated)",
    },
    "break_even_orders": {
        "title": "نقطة التعادل",
        "description": "عدد الطلبات الشهرية اللازم إنجازها لتغطية كافة التكاليف الثابتة دون تحقيق ربح أو خسارة.",
        "formula": "التكاليف الثابتة الشهرية ÷ هامش المساهمة للطلب الواحد",
        "source": "نموذج الجدوى التشغيلية",
        "kind": "محسوب (Calculated)",
    },
    "trust_level_pct": {
        "title": "مستوى الثقة",
        "description": "مؤشر طمأنينة الجمهور المستهدف تجاه مصداقية المشروع وسمعته وسياسات الضمان.",
        "formula": "تقييم عناصر الإثبات وسياسات الاسترجاع والوضوح",
        "source": "لوحة أبعاد دراسة المشروع",
        "kind": "تقديري (Estimated)",
    },
    "liquidity_pressure_dzd": {
        "title": "ضغط السيولة",
        "description": "إجمالي التدفقات النقدية الخارجة المطلوبة شهرياً لتغطية الإيجار والرواتب والمخزون المباشر.",
        "formula": "التكاليف الثابتة + (الطلبات المتوقعة × التكلفة المباشرة للوحدة)",
        "source": "المصاريف التشغيلية ومشتريات المواد الأولية",
        "kind": "محسوب (Calculated)",
    },
}

def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

def _seed_unit(*parts: Any) -> float:
    raw = ":".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:14], 16) / float(0xFFFFFFFFFFFFFF)

def _age_group(age: int) -> str:
    if age <= 24:
        return "18–24"
    if age <= 34:
        return "25–34"
    if age <= 44:
        return "35–44"
    if age <= 54:
        return "45–54"
    return "55+"

def _income_band(income: float) -> str:
    if income < 25000:
        return "أقل من 25 ألف دج"
    if income < 50000:
        return "25–50 ألف دج"
    if income < 90000:
        return "50–90 ألف دج"
    if income < 150000:
        return "90–150 ألف دج"
    return "أكثر من 150 ألف دج"

def _purchasing_power(budget: float) -> str:
    if budget < 12000:
        return "محدودة"
    if budget < 24000:
        return "متوسطة"
    if budget < 50000:
        return "جيدة"
    return "مرتفعة"

def _preferred_payment(persona: Persona, methods: list[str]) -> str:
    methods = methods or ["كاش"]
    scores: dict[str, float] = {}
    for method in methods:
        if method == "الدفع عند الاستلام":
            scores[method] = persona.cod_preference
        elif method in {"بريدي موب", "بطاقة", "تحويل بنكي"}:
            scores[method] = persona.digital_affinity
        else:
            scores[method] = 0.72
    return max(scores, key=scores.get)

def _transportation(persona: Persona, config: dict[str, Any], index: int) -> str:
    if config.get("parking") or persona.monthly_income_estimate > 90000:
        return "سيارة"
    if persona.monthly_income_estimate > 45000:
        return "سيارة أو نقل عمومي"
    choices = ["نقل عمومي", "مشي", "دراجة", "سيارة مشتركة", "نقل عمومي"]
    return choices[index % len(choices)]

def _event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type)

def _category_from_decision(decision: dict[str, Any], persona: Persona, config: dict[str, Any], activity: str) -> str:
    if decision.get("buys"):
        return "accepted"
    objections = " ".join(decision.get("objections") or [])
    reason = str(decision.get("reason_code") or "")
    if not config.get("parking", False) and activity in {"cafe", "restaurant", "retail"} and persona.convenience_need > 0.61:
        if _seed_unit(decision.get("persona_id"), "parking") > 0.42:
            return "parking"
    if reason == "affordability" or "السعر" in objections or "سعر التوصيل" in objections:
        return "price"
    if reason == "payment" or "الدفع" in objections:
        return "payment"
    if activity == "retail" and (
        not config.get("fitting_rooms", False) or not config.get("clear_prices", False)
    ):
        return "product"
    if reason == "trust" or "الثقة" in objections:
        return "trust"
    if activity == "ecommerce" and "التوصيل" in objections:
        return "delivery"
    if reason == "convenience" or "الانتظار" in objections or "الخدمة" in objections:
        return "waiting"
    if reason == "evidence":
        return "relevance"
    return "relevance"

def _loss_reason_codes(category: str, decision: dict[str, Any], persona: Persona, config: dict[str, Any]) -> list[str]:
    codes: dict[str, list[str]] = {
        "parking": ["parking_unavailable", "high_convenience_need"],
        "price": ["price_above_budget", "affordability_fit_low"],
        "payment": ["payment_method_missing", "digital_affinity_mismatch"],
        "waiting": ["waiting_time_high", "low_waiting_tolerance"],
        "trust": ["trust_need_high", "trust_signal_low"],
        "product": ["product_or_size_unavailable", "store_experience_gap"],
        "delivery": ["delivery_cost_high", "delivery_uncertainty"],
        "relevance": ["offer_relevance_low", "information_gap"],
    }
    result = list(codes.get(category, ["offer_not_convincing"]))
    if decision.get("reason_code"):
        result.append(f"weak_factor_{decision['reason_code']}")
    if persona.price_sensitivity > 0.7:
        result.append("high_price_sensitivity")
    if persona.trust_need > 0.7:
        result.append("high_trust_need")
    if config.get("waiting_minutes", 0):
        result.append(f"waiting_{int(float(config.get('waiting_minutes', 0)))}m")
    return result[:5]

def _loss_impact(decision: dict[str, Any], config: dict[str, Any], contribution: float) -> dict[str, float]:
    offer = decision.get("selected_offer") or {}
    delivery = 0.0
    if str(config.get("activity_key")) == "ecommerce" and not config.get("free_delivery"):
        delivery = max(0.0, float(config.get("delivery_price", 0) or 0))
    revenue = max(0.0, float(offer.get("price", config.get("price", 0)) or 0) + delivery)
    margin = max(0.0, float(contribution or 0))
    return {
        "lostRevenueDzd": round(revenue),
        "lostMarginDzd": round(margin),
        "revenueDzd": 0,
        "marginDzd": 0,
    }

def _purchase_impact(decision: dict[str, Any], config: dict[str, Any], contribution: float) -> dict[str, float]:
    offer = decision.get("selected_offer") or {}
    delivery = 0.0
    if str(config.get("activity_key")) == "ecommerce" and not config.get("free_delivery"):
        delivery = max(0.0, float(config.get("delivery_price", 0) or 0))
    revenue = max(0.0, float(offer.get("price", config.get("price", 0)) or 0) + delivery)
    margin = max(0.0, float(contribution or 0))
    return {
        "lostRevenueDzd": 0,
        "lostMarginDzd": 0,
        "revenueDzd": round(revenue),
        "marginDzd": round(margin),
    }

def _location_positions(activity: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Define 3D coordinates and sequence for each business environment type.
    Includes customized realistic spatial layouts for:
    - cafe: Storefront, parking, counter, menu, queue, pickup, tables, wifi, exit
    - restaurant: Fast-food order pass, heat lamps, menu, queue, pickup, dining booths, terrace, parking, street
    - retail: Mannequin display, clothing racks, fitting rooms, queue, cashier wrap, parking, street
    - ecommerce: Digital discovery, online storefront, comparison, cart, payment, packaging bench, courier dispatch bay, reception
    - service: Reception desk, client waiting lounge, diagnostic workbench, conference table, invoicing, follow-up
    """
    if activity in {"cafe", "restaurant"}:
        locations = {
            "street": {"x": -6.0, "z": 1.2, "label": "الشارع", "kind": "street"},
            "parking": {"x": -4.2, "z": -1.2, "label": "مواقف السيارات", "kind": "parking"},
            "entrance": {"x": 0.0, "z": 0.8, "label": "المدخل", "kind": "entrance"},
            "menu": {"x": 1.8, "z": -1.8, "label": "قائمة الأسعار", "kind": "menu"},
            "queue": {"x": 2.8, "z": -1.8, "label": "الطابور", "kind": "queue"},
            "counter": {"x": 3.8, "z": -2.2, "label": "صندوق الدفع", "kind": "counter"},
            "pickup": {"x": 5.4, "z": -2.2, "label": "نقطة استلام الطلب", "kind": "pickup"},
            "tables": {"x": 5.2, "z": 1.0, "label": "الطاولات", "kind": "seating"},
            "wifi": {"x": 8.6, "z": -0.8, "label": "منطقة Wi-Fi", "kind": "wifi"},
            "exit": {"x": 0.0, "z": 1.8, "label": "المخرج", "kind": "exit"},
        }
        return locations, ["street", "parking", "entrance", "menu", "queue", "counter", "pickup", "tables", "wifi", "exit"]

    if activity == "retail":
        locations = {
            "street": {"x": -6.0, "z": 1.2, "label": "الشارع", "kind": "street"},
            "parking": {"x": -4.2, "z": -1.2, "label": "مواقف السيارات", "kind": "parking"},
            "entrance": {"x": 0.0, "z": 0.8, "label": "المدخل", "kind": "entrance"},
            "shelves": {"x": 3.6, "z": 0.6, "label": "رفوف وتشكيلة المنتجات", "kind": "shelf"},
            "fitting": {"x": 8.6, "z": -0.8, "label": "غرف القياس والمرايا", "kind": "fitting"},
            "queue": {"x": 2.8, "z": -1.8, "label": "الطابور", "kind": "queue"},
            "cashier": {"x": 3.8, "z": -2.2, "label": "صندوق الدفع والتغليف", "kind": "cashier"},
            "exit": {"x": 0.0, "z": 1.8, "label": "المخرج", "kind": "exit"},
        }
        return locations, ["street", "parking", "entrance", "shelves", "fitting", "queue", "cashier", "exit"]

    if activity == "ecommerce":
        locations = {
            "discovery": {"x": -6.0, "z": 1.2, "label": "الإعلان والحملة الرقمية", "kind": "discovery"},
            "product_page": {"x": -3.8, "z": 0.4, "label": "المتجر وتفاصيل المنتج", "kind": "catalog"},
            "comparison": {"x": -1.6, "z": -0.6, "label": "المقارنة والمقاسات", "kind": "comparison"},
            "cart": {"x": 0.8, "z": -1.2, "label": "سلة الطلب", "kind": "cart"},
            "payment": {"x": 2.8, "z": -1.8, "label": "تأكيد الدفع / COD", "kind": "payment"},
            "confirmation": {"x": 4.8, "z": -1.8, "label": "منضدة التغليف والتجهيز", "kind": "checkout"},
            "delivery": {"x": 7.2, "z": 0.0, "label": "شحن وتوصيل الطرود", "kind": "delivery"},
            "reception": {"x": 8.8, "z": 1.6, "label": "استلام الزبون للطلب", "kind": "confirmation"},
        }
        return locations, ["discovery", "product_page", "comparison", "cart", "payment", "confirmation", "delivery", "reception"]

    if activity == "service":
        locations = {
            "discovery": {"x": -6.0, "z": 1.2, "label": "اكتشاف الخدمة", "kind": "discovery"},
            "booking": {"x": -3.8, "z": 0.2, "label": "طلب الحجز الأولي", "kind": "booking"},
            "reception": {"x": 0.0, "z": 0.8, "label": "مكتب الاستقبال", "kind": "reception"},
            "waiting": {"x": 2.4, "z": 1.4, "label": "صالة استراحة الزبائن", "kind": "waiting"},
            "service": {"x": 5.4, "z": -1.4, "label": "ورشة / منضدة تقديم الخدمة", "kind": "service"},
            "payment": {"x": 3.8, "z": -2.2, "label": "الفاتورة والدفع", "kind": "payment"},
            "follow_up": {"x": 6.8, "z": 1.0, "label": "متابعة وتقييم الجودة", "kind": "follow_up"},
            "repeat": {"x": 8.6, "z": -0.6, "label": "إعادة الطلب والولاء", "kind": "repeat"},
        }
        return locations, ["discovery", "booking", "reception", "waiting", "service", "payment", "follow_up", "repeat"]

    # A custom activity still needs every event destination used by its journey.
    keys = ["discovery", "booking", "reception", "waiting", "service", "payment", "follow_up", "repeat", "exit"]
    labels = ["اكتشاف العرض", "طلب حجز", "الاستقبال", "الانتظار", "تجربة العرض", "الدفع", "المتابعة", "العودة", "المغادرة"]
    locations = {}
    for idx, (key, label) in enumerate(zip(keys, labels)):
        locations[key] = {"x": round(-8.0 + idx * 2.0, 2), "z": 0.0, "label": label, "kind": key}
    return locations, keys

def _action_text(event_type: str, persona: Persona, config: dict[str, Any], activity: str, location: str) -> str:
    """Rich, descriptive real-action explanation for each event in Arabic (Section 13)."""
    budget_period = "اليومية" if activity in {"cafe", "restaurant"} else "الشهرية"
    texts = {
        "noticed_business": "لاحظ المشروع من الشارع وقرر التوجه نحو المدخل لاستكشاف المكان.",
        "noticed": "شاهد العرض واسترعى انتباهه أثناء تصفحه.",
        "approached": "اقترب من المدخل بعد التأكد من سهولة الوصول إلى الموقع.",
        "parking_unavailable": "وصل بالسيارة وبحث عن موقف متاح في محيط المكان دون جدوى.",
        "left_due_to_parking": "غادر دون دخول بعد تعذر العثور على موقف قريب لسيارته.",
        "passed_without_entering": "مرّ بجانب المشروع دون أن يجد ما يدفعه للتوقف أو الدخول.",
        "entered": "دخل المقهى وتفقد الأجواء العامة والمقاعد المتاحة.",
        "entered_product_page": "فتح صفحة العرض للاطلاع على تفاصيل الأسعار والمواصفات.",
        "viewed_service": "اطلع على نطاق الخدمة وشروط التنفيذ.",
        "checked_products": "تفقّد تشكيلة المنتجات المعروضة وجودة الخامات على الرفوف.",
        "checked_menu": "طالع قائمة الأسعار وبدأ بدراسة الخيارات المتاحة ومقارنتها.",
        "compared_price": "راجع تكلفة الطلب وقارنها مع ميزانيته المتاحة للاستهلاك اليومي.",
        "waited_in_queue": "انضم إلى طابور الانتظار أمام صندوق الدفع بانتظار دوره.",
        "waited": "انتظر في منطقة الاستقبال لبدء تقديم الخدمة.",
        "chose_payment": "حدد وسيلة الدفع وأكد اختياره لدى أمين الصندوق.",
        "purchased": "أتم عملية الدفع بنجاح وأكد تسجيل طلبه في النظام.",
        "received_order": "استلم طلبه جاهزاً من نقطة استلام الطلبات.",
        "sat_at_table": "جلس عند إحدى الطاولات المتاحة للاستمتاع بطلبه في أجواء مناسبة.",
        "stayed_for_wifi": "استقر في منطقة Wi-Fi وفتح حاسوبه لمتابعة العمل أثناء تناول طلبه.",
        "left_due_to_price": f"تراجع عن العرض بعدما وجد السعر مرتفعاً مقارنة بميزانيته {budget_period} التقديرية.",
        "left_due_to_waiting": "غادر قبل الطلب بعدما طال الانتظار وتجاوز الحد المقبول لديه.",
        "left_due_to_payment": "تراجع عن الدفع لعدم توفر وسيلة الدفع الإلكترونية التي يفضلها.",
        "lost_trust": "تراجع قبل الطلب لغياب إشارات الثقة أو سياسات الاسترجاع والضمان الكافية.",
        "left_due_to_unavailable_size": "تراجع لعدم توفر المقاس أو النوع المطلوب في المخزون الحالي.",
        "abandoned": "غادر المشروع دون إتمام الشراء لعدم اقتناعه بالعرض الإجمالي.",
        "returned_later": "عاد لزيارة المشروع كزبون معتاد بثقة تامة بفضل تجربته الإيجابية السابقة.",
        "repeat_customer": "أكد ولاءه وسجل زيارته المتكررة كزبون دائم ومستمر.",
        "added_to_cart": "أضاف المنتج إلى سلة الشراء للشروع في تأكيد الطلب.",
        "checked_delivery": "راجع شروط ورسوم التوصيل والمدة الزمنية المتوقعة للوصول.",
        "abandoned_due_to_delivery": "ألغى الطلب لارتفاع تكلفة التوصيل أو بطء المدة المتوقعة.",
        "booked": "حجز الموعد إلكترونياً واختار التوقيت المناسب له.",
        "service_started": "بدأ الفريق المختص بتقديم الخدمة المطلوبة ميدانياً.",
        "cancelled": "ألغى الطلب أو الموعد لعدم ملاءمة الظروف المتاحة.",
    }
    location_label = _location_positions(activity)[0].get(location, {}).get("label", "المرحلة التالية")
    line = texts.get(event_type, f"انتقل إلى {EVENT_LABELS.get(event_type, location_label)} ضمن رحلة القرار.")
    if activity == "other" and any(word in str(config.get("custom_activity", "")).lower() for word in ("نادي رياضي", "رياضة", "لياقة", "gym", "fitness")):
        if event_type == "purchased":
            line = "أكد الاشتراك بعد مراجعة البرنامج والسعر وطريقة الدفع."
        elif event_type == "viewed_service":
            line = "راجع برنامج التدريب ومواعيد الحصص ومستوى الإشراف."
        elif event_type == "booked":
            line = "حجز حصة تجريبية أو موعداً للاستفسار عن الاشتراك."
    if persona.gender == "أنثى":
        for before, after in (("لاحظ ", "لاحظت "), ("شاهد ", "شاهدت "), ("اطلع ", "اطلعت "), ("راجع ", "راجعت "), ("تراجع ", "تراجعت "), ("انتقل ", "انتقلت "), ("انتظر ", "انتظرت "), ("ألغى ", "ألغت "), ("وجد ", "وجدت "), ("ميزانيته", "ميزانيتها"), ("لديه", "لديها"), ("انتباهه", "انتباهها"), ("تصفحه", "تصفحها")):
            line = line.replace(before, after)
    return line

# ==============================================================================
# STRUCTURED FACTOR-BASED DECISION REASON ENGINE (Sections 8, 9, 10, 11, 12)
# ==============================================================================

def _build_structured_decision(
    decision: dict[str, Any],
    persona: Persona,
    config: dict[str, Any],
    result: dict[str, Any],
    activity: str,
    category: str,
    index: int,
) -> dict[str, Any]:
    buys = bool(decision.get("buys"))
    probability = clamp(float(decision.get("probability", 0.5)))
    offer = decision.get("selected_offer") or {}
    offer_price = float(offer.get("price", config.get("price", 400)) or 400)
    monthly_budget = float(persona.monthly_discretionary_budget or 15000)
    budget_period = "اليومية" if activity in {"cafe", "restaurant"} else "الشهرية"
    spending_budget = max(150.0, monthly_budget / 30.0) if budget_period == "اليومية" else max(1000.0, monthly_budget)
    budget_pct = max(1, round((offer_price / spending_budget) * 100))
    waiting_min = float(config.get("waiting_minutes", 8 if activity == "cafe" else 15 if activity == "restaurant" else 0) or 0)
    acceptable_wait = max(4, round(18 - persona.convenience_need * 14))
    has_parking = bool(config.get("parking", False))
    has_wifi = bool(config.get("wifi", False))
    trust_score = float(config.get("trust_score", 60))
    methods = list(config.get("payment_methods") or ["كاش"])
    preferred_pay = _preferred_payment(persona, methods)

    raw_factors: list[dict[str, Any]] = []

    # 1. Affordability factor (السعر والميزانية)
    if not buys and (category == "price" or budget_pct > 32 or persona.price_sensitivity > 0.65):
        impact = -round(18 + persona.price_sensitivity * 12)
        raw_factors.append({
            "key": "affordability",
            "label": "السعر المرتفع",
            "impact": impact,
            "sign": "-",
            "positive": False,
            "desc": f"سعر العرض ({offer_price:.0f} دج) يمثل {budget_pct}% من ميزانيته {budget_period} التقديرية، وهو عبء مرتفع مقارنة بالبدائل المتاحة.",
        })
    elif buys and budget_pct <= 28:
        impact = round(16 + (1 - persona.price_sensitivity) * 12)
        raw_factors.append({
            "key": "affordability",
            "label": "السعر الملائم",
            "impact": impact,
            "sign": "+",
            "positive": True,
            "desc": f"السعر النهائي ({offer_price:.0f} دج) يقع ضمن ميزانيته {budget_period} التقديرية (يمثل {budget_pct}%).",
        })
    else:
        score_val = round(8 + (1 - persona.price_sensitivity) * 6) if buys else -round(8 + persona.price_sensitivity * 6)
        raw_factors.append({
            "key": "affordability",
            "label": "ملاءمة السعر" if buys else "تحفظ على السعر",
            "impact": score_val,
            "sign": "+" if buys else "-",
            "positive": buys,
            "desc": f"السعر النهائي ({offer_price:.0f} دج) يمثل {budget_pct}% من ميزانيته {budget_period} التقديرية.",
        })

    # 2. Wi-Fi factor (توفر الويفي) - specific to cafe/digital personas
    if activity == "cafe":
        if has_wifi:
            if persona.experience_need > 0.45 or persona.digital_affinity > 0.5 or "عمل" in persona.primary_motivation or "طلبة" in persona.archetype:
                impact = round(14 + persona.experience_need * 10)
                raw_factors.append({
                    "key": "wifi",
                    "label": "توفر الويفي",
                    "impact": impact,
                    "sign": "+",
                    "positive": True,
                    "desc": "توفر شبكة Wi-Fi سريعة ومستقرة يجعل المكان مناسباً للعمل والدراسة لساعات إضافية.",
                })
            else:
                raw_factors.append({
                    "key": "wifi",
                    "label": "توفر الويفي",
                    "impact": 6,
                    "sign": "+",
                    "positive": True,
                    "desc": "توفر اتصال Wi-Fi يمثل ميزة إضافية مريحة أثناء التواجد.",
                })
        elif not has_wifi and (persona.experience_need > 0.55 or persona.digital_affinity > 0.6):
            impact = -round(12 + persona.digital_affinity * 10)
            raw_factors.append({
                "key": "wifi",
                "label": "غياب الويفي",
                "impact": impact,
                "sign": "-",
                "positive": False,
                "desc": "غياب شبكة Wi-Fi يحدّ من رغبته في قضاء وقت عمل أو جلسة دراسية طويلة.",
            })

    # 3. Seating and Tables (المقاعد والطاولات)
    if activity in {"cafe", "restaurant"}:
        if buys:
            impact = round(9 + persona.experience_need * 8)
            raw_factors.append({
                "key": "seating",
                "label": "طاولة متاحة",
                "impact": impact,
                "sign": "+",
                "positive": True,
                "desc": "وجد طاولة شاغرة ومقاعد مريحة توفر استقلالية وأجواء ملائمة.",
            })
        elif category == "product":
            raw_factors.append({
                "key": "seating",
                "label": "محدودية المقاعد",
                "impact": -12,
                "sign": "-",
                "positive": False,
                "desc": "المقاعد المتاحة كانت محدودة أو في موقع غير مريح لجلسته.",
            })

    # 4. Waiting time (مدة الانتظار)
    if waiting_min > acceptable_wait or category == "waiting":
        impact = -round(15 + persona.convenience_need * 14)
        raw_factors.append({
            "key": "waiting",
            "label": "مدة الانتظار",
            "impact": impact,
            "sign": "-",
            "positive": False,
            "desc": f"مدة الانتظار المتوقعة ({waiting_min:.0f} دقائق) تجاوزت الحد المقبول لديه ({acceptable_wait} دقائق) قبل موعده التالي.",
        })
    elif buys:
        impact = round(6 + (1 - persona.convenience_need) * 6)
        raw_factors.append({
            "key": "waiting",
            "label": "سرعة الخدمة",
            "impact": impact,
            "sign": "+",
            "positive": True,
            "desc": f"مدة الانتظار المقدرة ({waiting_min:.0f} دقائق) لم تتجاوز قدرته على الانتظار.",
        })

    # 5. Parking (مواقف السيارات)
    uses_car = persona.monthly_income_estimate > 45000 or config.get("parking") or category == "parking"
    if uses_car:
        if not has_parking and (category == "parking" or persona.convenience_need > 0.6):
            impact = -round(18 + persona.convenience_need * 12)
            raw_factors.append({
                "key": "parking",
                "label": "غياب موقف السيارة",
                "impact": impact,
                "sign": "-",
                "positive": False,
                "desc": "وصل بالسيارة ولم يجد موقفاً متاحاً في الشارع المزدحم، وأقرب موقف بديل بعيد بالنسبة إليه.",
            })
        elif has_parking:
            impact = round(10 + persona.convenience_need * 8)
            raw_factors.append({
                "key": "parking",
                "label": "موقف متاح",
                "impact": impact,
                "sign": "+",
                "positive": True,
                "desc": "سهولة العثور على موقف قريب للسيارة سهّل الوصول والنزول السريع.",
            })

    # 6. Trust (مؤشرات الثقة والسمعة)
    if trust_score < 65 and (persona.trust_need > 0.65 or category == "trust"):
        impact = -round(14 + persona.trust_need * 12)
        raw_factors.append({
            "key": "trust",
            "label": "نقص إثباتات الثقة",
            "impact": impact,
            "sign": "-",
            "positive": False,
            "desc": "المشروع جديد ولا توجد مؤشرات ثقة أو تقييمات عملاء سابقة كافية بالنسبة لشخصية حذرة.",
        })
    elif trust_score >= 70:
        impact = round(8 + persona.trust_need * 8)
        raw_factors.append({
            "key": "trust",
            "label": "مستوى الثقة",
            "impact": impact,
            "sign": "+",
            "positive": True,
            "desc": "السمعة الإيجابية للمشروع تعطي طمأنينة كافية تجاه جودة ما يُقدّم.",
        })

    # 7. Atmosphere / Peak Noise (تحفظ إضافي للمشترين)
    if buys and activity in {"cafe", "restaurant"}:
        raw_factors.append({
            "key": "noise",
            "label": "الضجيج في الذروة",
            "impact": -5,
            "sign": "-",
            "positive": False,
            "desc": "الضجيج في فترة الذروة قد يقلّل احتمال عودته مساءً.",
        })

    # 8. PAYMENT METHOD COMPLIANCE RULE (Strict check from Section 8):
    # Payment must ONLY be mentioned if preferred method is unavailable or specifically rejected!
    # If preferred payment is cash and cash is accepted -> NO payment factor, NO payment in text!
    if preferred_pay not in methods or category == "payment":
        impact = -round(16 + persona.digital_affinity * 10)
        raw_factors.append({
            "key": "payment",
            "label": f"عدم توفر الدفع بـ{preferred_pay}",
            "impact": impact,
            "sign": "-",
            "positive": False,
            "desc": f"وسيلة الدفع التي يعتمد عليها ({preferred_pay}) غير متوفرة ضمن خيارات الدفع المقبولة بالمشروع.",
        })

    # Separate positive and negative drivers
    positives = sorted([f for f in raw_factors if f["positive"]], key=lambda x: x["impact"], reverse=True)
    negatives = sorted([f for f in raw_factors if not f["positive"]], key=lambda x: x["impact"])

    top_driver = positives[0]["label"] if positives else "ملاءمة العرض"
    second_driver = positives[1]["label"] if len(positives) > 1 else (positives[0]["label"] if positives else "جودة التجربة")
    top_friction = negatives[0]["label"] if negatives else "لا توجد تحفظات جوهرية"
    second_friction = negatives[1]["label"] if len(negatives) > 1 else "تحفظ طفيف"

    # Outcome text (Section 9)
    if buys:
        outcome = "قرر الشراء."
    elif category == "parking":
        outcome = "لم يدخل المشروع."
    elif category == "waiting":
        outcome = "غادر قبل تقديم الطلب."
    elif category == "trust":
        outcome = "تراجع عن الشراء."
    else:
        outcome = "غادر دون شراء."

    # Main Reason (السبب الرئيسي)
    if buys:
        main_reason = f"رجّح {top_driver} قرار الشراء؛ السعر المعروض {offer_price:.0f} دج، وتقدير الملاءمة لهذه الشخصية {round(probability * 100)}%."
    elif category == "parking":
        main_reason = "وصل بالسيارة ولم يجد موقفاً متاحاً خلال الوقت الذي يستطيع انتظاره."
    elif category == "price":
        main_reason = f"سعر العرض يمثل نسبة مرتفعة ({budget_pct}%) من ميزانيته {budget_period} التقديرية مقارنة بالبدائل القريبة."
    elif category == "waiting":
        main_reason = f"مدة الانتظار المتوقعة ({waiting_min:.0f} دقيقة) تجاوزت قدرته على الانتظار قبل موعده التالي."
    elif category == "trust":
        main_reason = "لم يجد معلومات كافية حول جودة المنتج أو سياسة الاستبدال."
    elif category == "payment":
        main_reason = f"وسيلة الدفع التي يعتمد عليها ({preferred_pay}) غير متوفرة ضمن خيارات الدفع بالمشروع."
    else:
        main_reason = "العرض لم يقدم قيمة مضافة كافية لتبرير الدفع مقارنة بالأولويات الأخرى لديه."

    # Supporting Factors (العوامل المساعدة)
    if buys:
        supporting_factors = f"العامل الإيجابي التالي هو {second_driver}." if second_driver != top_driver else "لم يظهر عائق إضافي حاسم في هذا السيناريو."
    elif category == "parking":
        supporting_factors = "الشارع مزدحم، وأقرب موقف بديل بعيد بالنسبة إليه."
    elif category == "price":
        supporting_factors = "لم يجد عرضاً اقتصادياً أو حجماً أصغر يناسب ميزانيته في هذه الزيارة."
    elif category == "waiting":
        supporting_factors = "الطابور يتحرك ببطء ولا توجد إشارة واضحة إلى وقت الخدمة المتوقع."
    elif category == "trust":
        supporting_factors = "المشروع جديد ولا توجد مؤشرات ثقة كافية بالنسبة لشخصية حذرة."
    elif category == "payment":
        supporting_factors = "تفضيله للدفع الإلكتروني لم يجد قناة معتمدة وسلسة لإتمامه."
    else:
        supporting_factors = "لم تتوفر عناصر جذب إضافية تشجع على التجربة الأولى."

    # Reservation (نقطة التحفظ)
    if buys:
        reservation = f"أبرز نقطة تستحق المتابعة: {top_friction}." if negatives else "لا توجد نقطة تحفظ بارزة في المدخلات الحالية."
    elif category == "parking":
        reservation = "العرض مناسب له من حيث السعر، لكن الوصول إلى المكان كان العائق الأساسي."
    elif category == "price":
        reservation = "أعجبه المكان، لذلك لم يكن الرفض مرتبطاً بجودة التجربة."
    elif category == "waiting":
        reservation = "السعر والمنتج كانا مناسبين، لذلك لم يكن الرفض مالياً."
    elif category == "trust":
        reservation = "السعر مقبول، لكنه غير كافٍ لتعويض غياب الثقة."
    elif category == "payment":
        reservation = "المنتج والخدمة كانا مناسبين، واقتصر العائق على وسيلة الدفع."
    else:
        reservation = "أعجبته الفكرة عموماً، لكنه فضل التريث في الوقت الراهن."

    # What would change the decision (ما الذي قد يغيّر القرار؟)
    if buys:
        what_would_change = f"اختبر تأثير تغيّر {top_friction} على قراره في سيناريو جديد." if negatives else "اختبر السعر والخدمة في سيناريو جديد للتحقق من ثبات القرار."
    elif category == "parking":
        what_would_change = "توفير اتفاق مع موقف قريب أو توضيح أماكن الركن البديلة."
    elif category == "price":
        what_would_change = "إضافة عرض بسعر أقل أو تخفيض خاص بالفترة الصباحية."
    elif category == "waiting":
        what_would_change = "تقليل وقت الخدمة أو إظهار المدة المتوقعة قبل الانضمام إلى الطابور."
    elif category == "trust":
        what_would_change = "عرض معلومات واضحة عن الجودة والاستبدال وتجارب العملاء الموثقة."
    elif category == "payment":
        what_would_change = f"إضافة وسيلة الدفع بـ{preferred_pay} لتسهيل الدفع الإلكتروني."
    else:
        what_would_change = "تقديم باقة تجريبية أو تسليط الضوء على مزايا المنتج التنافسية."

    # Platform Analysis (تحليل Fintwin - Formal, objective) (Section 11)
    if buys:
        platform_analysis = f"اختارت الشخصية الشراء في هذا السيناريو. أبرز عامل مساند هو {top_driver}، يليه {second_driver}؛ وتقدير نية الشراء {round(probability * 100)}%."
    elif category == "parking":
        platform_analysis = "غادرت الشخصية قبل الدخول لأن وصولها بالسيارة اصطدم بعدم توفر موقف متاح خلال الوقت المقبول لديها، رغم ملاءمة السعر المالي."
    elif category == "waiting":
        platform_analysis = f"غادرت الشخصية لأن مدة الانتظار المتوقعة ({waiting_min:.0f} دقيقة) تجاوزت الحد المقبول لديها بست دقائق قبل موعدها اللاحق."
    elif category == "price":
        platform_analysis = f"سعر {offer_price:.0f} دج يمثل {budget_pct}% من ميزانيته {budget_period} التقديرية، مما ساهم في تراجعه رغم ملاءمة جوانب أخرى من العرض."
    elif category == "trust":
        platform_analysis = "تراجعت الشخصية عن الشراء لحاجتها إلى إشارات ثقة وتجارب سابقة تفوق المتاح حالياً لدى المشروع."
    elif category == "payment":
        platform_analysis = f"تراجعت الشخصية لعدم توفر وسيلة الدفع بـ{preferred_pay} مع تفضيلها المعاملات غير النقدية."
    else:
        platform_analysis = "لم تكتمل عملية الشراء لعدم تجاوز المنفعة المتوقعة عتبة التردد المسجلة في المحاكاة."

    # Persona Quote (تعليق الشخصية - Natural first-person Arabic) (Section 11)
    if buys:
        persona_quote = f"العرض مناسب لي؛ أكثر ما شجعني هو {top_driver}."
    elif category == "parking":
        persona_quote = "جيت بالطوموبيل ودرت شحال من دورة ما لقيتش وين نكاري، اضطرّيت نكمل طريقي."
    elif category == "waiting":
        persona_quote = "المكان مناسب، لكن لا أستطيع انتظار ربع ساعة قبل العمل."
    elif category == "price":
        persona_quote = f"سعر {offer_price:.0f} دج جاني غالي على قهوة، يديلي كثر من ثلث ميزانية يومي وما يساعدنيش نهار كامل."
    elif category == "trust":
        persona_quote = "المحل جديد وما نعرفش الجودة نتاعهم مليح، فضّلت نتريث حتى نشوف تجارب ناس آخرين."
    elif category == "payment":
        persona_quote = f"كنت حاب نخلص بـ{preferred_pay} وما لقيتهاش؛ ما نحبش نستعمل الكاش بزاف."
    else:
        persona_quote = "ما لقيتش حاجة تشجعني نجرب اليوم، بالاك نرجع كي نشوف عروض أوضح."

    confidence_score = round(clamp(0.55 + abs(probability - 0.5) * 0.82), 2)
    confidence_text = "ثقة مرتفعة مبنية على توافق قوي في العوامل الأساسية" if confidence_score >= 0.78 else "ثقة متوسطة نظراً لوجود عوامل متقاربة بين الشراء والتردد"

    structured_decision = {
        "outcome": outcome,
        "main_driver": top_driver,
        "second_driver": second_driver,
        "main_friction": top_friction,
        "second_friction": second_friction,
        "main_reason": main_reason,
        "supporting_factors": supporting_factors,
        "reservation": reservation,
        "what_would_change": what_would_change,
        "decision_score": round(probability, 4),
        "confidence": confidence_score,
        "confidence_explanation": confidence_text,
    }

    # Format decision factors for frontend visualization (Section 12)
    display_factors = [
        {
            "factor": f["key"],
            "label": f["label"],
            "impact": abs(f["impact"]),
            "sign": f["sign"],
            "sentiment": "positive" if f["positive"] else "negative",
            "description": f["desc"],
        }
        for f in raw_factors[:5]
    ]

    return {
        "structured_decision": structured_decision,
        "decision_factors": display_factors,
        "platform_analysis": platform_analysis,
        "persona_quote": persona_quote,
        "legacy_reason": main_reason,
    }

def _environment(activity: str, config: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    locations, route = _location_positions(activity)
    fitness = activity == "other" and any(word in str(config.get("custom_activity", "")).lower() for word in ("نادي رياضي", "رياضة", "لياقة", "fitness", "gym"))
    if fitness:
        fitness_labels = {"discovery": "اكتشاف النادي", "booking": "حصة تجريبية", "reception": "الاستقبال", "waiting": "قاعة الانتظار", "service": "منطقة التدريب", "payment": "الاشتراك والدفع", "follow_up": "متابعة التقدم", "repeat": "تجديد الاشتراك", "exit": "المغادرة"}
        for key, label in fitness_labels.items():
            locations[key]["label"] = label
    physical = activity in {"cafe", "restaurant", "retail"} or fitness
    products = [item for item in (config.get("products") or []) if item.get("name")]
    if not products:
        products = [{"name": "العرض الرئيسي", "price_dzd": config.get("price", 0)}]
    reference_price = float(config.get("catalog_reference_price") or config.get("price") or 1)
    price_multiplier = float(config.get("price") or reference_price) / max(1, reference_price)
    waiting = float(config.get("waiting_minutes", 8 if activity == "cafe" else 15 if activity == "restaurant" else 0) or 0)
    business: dict[str, Any] = {
        "parking": bool(config.get("parking", False)),
        "parking_spaces": 8 if config.get("parking") else 0,
        "wifi": bool(config.get("wifi", False)),
        "seating_capacity": int(config.get("seating_capacity") or (34 if activity == "cafe" else 46 if activity == "restaurant" else 24)),
        "tables": int(config.get("tables") or (12 if activity == "cafe" else 16 if activity == "restaurant" else 0)),
        "waiting_minutes": waiting,
        "peak_hours": (
            "18:00–21:00" if activity == "cafe"
            else "12:00–14:00" if activity == "restaurant"
            else "17:00–20:00" if activity == "retail"
            else "20:00–22:00" if activity == "ecommerce"
            else "09:00–12:00"
        ),
        "menu": [{"name": item.get("name"), "price": round(float(item.get("price_dzd") or config.get("price") or 0) * price_multiplier)} for item in products[:5]],
        "fitting_rooms": bool(config.get("fitting_rooms", False)),
        "clear_prices": bool(config.get("clear_prices", False)),
        "street_type": config.get("street_type") or ("شارع تجاري" if physical else "قناة رقمية"),
        "delivery_price": float(config.get("delivery_price", 0) or 0),
        "response_minutes": float(config.get("response_minutes", 30) or 30),
        "online_booking": bool(config.get("online_booking", False)),
        "payment_methods": list(config.get("payment_methods") or ["كاش"]),
        "occupancy_reference": int(result.get("expected_monthly_orders", 0) or 0),
        "product_availability": [
            {"name": item.get("name"), "stock": item.get("stock")}
            for item in products[:6]
        ],
    }
    return {
        "kind": "physical" if physical else "journey",
        "activity": activity,
        "visual_activity": "fitness" if fitness else activity,
        "label": config.get("custom_activity") or ACTIVITY_LABELS.get(activity, "نشاط"),
        "locations": locations,
        "route": route,
        "business": business,
        "stage_order": route,
        "camera": {"distance": 16.0 if physical else 14.5, "height": 9.5 if physical else 8.5},
    }



def _timeline_for_decision(
    decision: dict[str, Any],
    persona: Persona,
    config: dict[str, Any],
    result: dict[str, Any],
    activity: str,
    index: int,
) -> tuple[list[dict[str, Any]], str, str]:
    """Translate one existing decision into a normalized visual timeline."""
    base = _seed_unit(decision.get("persona_id"), config.get("scenario_name", "Baseline"), "timeline")
    start = round(2.0 + (base ** 1.35) * 165.0, 1)
    buys = bool(decision.get("buys"))
    probability = clamp(float(decision.get("probability", 0)))
    category = _category_from_decision(decision, persona, config, activity)
    contribution = float(result.get("contribution_per_order_dzd", 0) or 0)
    confidence = round(clamp(0.55 + abs(probability - 0.5) * 0.82), 2)
    events: list[dict[str, Any]] = []
    previous_state = "unexposed"

    def add(
        event_type: str,
        offset: float,
        new_state: str,
        location: str,
        *,
        impact: dict[str, float] | None = None,
        reason_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        nonlocal previous_state
        timestamp = round(max(0.0, start + offset), 1)
        event = {
            "id": f"event_{decision.get('persona_id')}_{len(events) + 1}",
            "personaId": decision.get("persona_id"),
            "personaName": decision.get("name"),
            "timestamp": timestamp,
            "type": event_type,
            "label": _event_label(event_type),
            "actionText": _action_text(event_type, persona, config, activity, location),
            "previousState": previous_state,
            "newState": new_state,
            "newStateAr": translate_state(new_state),
            "location": location,
            "reasonCodes": reason_codes or [],
            "decisionScore": round(probability, 4),
            "confidence": confidence,
            "financialImpact": impact or {
                "lostRevenueDzd": 0, "lostMarginDzd": 0, "revenueDzd": 0, "marginDzd": 0,
            },
            "category": category if not buys else "accepted",
        }
        events.append(event)
        previous_state = new_state
        return event

    if activity in {"cafe", "restaurant", "retail"}:
        add("noticed_business", 0, "noticed", "street")
        if not buys and category == "parking":
            add("approached", 16, "approaching", "street")
            add("parking_unavailable", 29, "searching_parking", "parking",
                reason_codes=_loss_reason_codes("parking", decision, persona, config))
            add("left_due_to_parking", 43, "parking_left", "street",
                impact=_loss_impact(decision, config, contribution),
                reason_codes=_loss_reason_codes("parking", decision, persona, config))
        elif not buys and probability < 0.24:
            add("passed_without_entering", 20 + base * 12, "left", "street",
                impact=_loss_impact(decision, config, contribution),
                reason_codes=_loss_reason_codes("relevance", decision, persona, config))
        else:
            add("approached", 14, "approaching", "entrance")
            add("entered", 26, "inside", "entrance")
            if activity == "retail":
                add("checked_products", 41, "browsing", "shelves")
                add("compared_price", 54, "comparing", "shelves")
            else:
                add("checked_menu", 41, "browsing", "menu")
                add("compared_price", 54, "comparing", "menu")

            if buys:
                if config.get("waiting_minutes", 0) and float(config.get("waiting_minutes", 0)) > 4:
                    add("waited_in_queue", 63, "queueing", "queue")
                payment = decision.get("payment") or _preferred_payment(persona, list(config.get("payment_methods") or []))
                add("chose_payment", 72, "buying", "counter" if activity != "retail" else "cashier")
                add("purchased", 83, "purchased", "counter" if activity != "retail" else "cashier",
                    impact=_purchase_impact(decision, config, contribution),
                    reason_codes=["order_completed"])

                if activity in {"cafe", "restaurant"}:
                    add("received_order", 92, "using_service", "pickup")
                    if activity == "cafe" and config.get("wifi") and (persona.experience_need > 0.45 or persona.digital_affinity > 0.5):
                        add("stayed_for_wifi", 104, "sitting", "wifi")
                    else:
                        add("sat_at_table", 104, "sitting", "tables")

                if _is_repeat(decision, persona, activity):
                    add("returned_later", 124, "returned", "entrance")
                    add("repeat_customer", 136, "repeat", "counter" if activity != "retail" else "cashier",
                        impact=_purchase_impact(decision, config, contribution),
                        reason_codes=["repeat_pattern", "positive_first_experience"])
            else:
                if category == "waiting":
                    add("waited_in_queue", 63, "queueing", "queue")
                    add("left_due_to_waiting", 78, "left", "exit",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("waiting", decision, persona, config))
                elif category == "payment":
                    add("checked_payment_options", 64, "comparing", "counter" if activity != "retail" else "cashier")
                    add("left_due_to_payment", 78, "left", "exit",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("payment", decision, persona, config))
                elif category == "trust":
                    add("checked_trust", 62, "comparing", "entrance")
                    add("lost_trust", 79, "left", "exit",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("trust", decision, persona, config))
                elif category == "product" and activity == "retail":
                    if config.get("fitting_rooms"):
                        add("checked_products", 66, "browsing", "fitting")
                    add("left_due_to_unavailable_size", 80, "left", "exit",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("product", decision, persona, config))
                elif category in {"price", "delivery"}:
                    add("left_due_to_price", 78, "left", "exit",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes(category, decision, persona, config))
                else:
                    add("abandoned", 78, "abandoned", "exit",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes(category, decision, persona, config))
    elif activity == "ecommerce":
        add("noticed", 0, "noticed", "discovery")
        if not buys and probability < 0.2:
            add("passed_without_entering", 26, "left", "discovery",
                impact=_loss_impact(decision, config, contribution),
                reason_codes=_loss_reason_codes("relevance", decision, persona, config))
        else:
            add("entered_product_page", 18, "inside", "product_page")
            add("compared_price", 31, "comparing", "comparison")
            if buys:
                add("added_to_cart", 43, "browsing", "cart")
                add("chose_payment", 55, "buying", "payment")
                add("purchased", 67, "purchased", "confirmation",
                    impact=_purchase_impact(decision, config, contribution),
                    reason_codes=["order_confirmed", "payment_fit"])
                add("delivery", 84, "using_service", "delivery")
                add("received", 100, "using_service", "reception")
                if _is_repeat(decision, persona, activity):
                    add("returned_later", 120, "returned", "product_page")
                    add("repeat_customer", 134, "repeat", "confirmation",
                        impact=_purchase_impact(decision, config, contribution),
                        reason_codes=["repeat_pattern", "positive_first_experience"])
            else:
                if category == "payment":
                    add("checked_payment_options", 43, "comparing", "payment")
                    add("left_due_to_payment", 58, "left", "payment",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("payment", decision, persona, config))
                elif category == "trust":
                    add("checked_trust", 43, "comparing", "product_page")
                    add("lost_trust", 60, "left", "comparison",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("trust", decision, persona, config))
                elif category == "delivery":
                    add("checked_delivery", 43, "comparing", "cart")
                    add("abandoned_due_to_delivery", 58, "left", "cart",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("delivery", decision, persona, config))
                elif category == "price":
                    add("left_due_to_price", 52, "left", "comparison",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("price", decision, persona, config))
                else:
                    add("abandoned", 55, "abandoned", "comparison",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes(category, decision, persona, config))
    else:  # service + generic journey
        add("noticed", 0, "noticed", "discovery")
        if not buys and probability < 0.2:
            add("passed_without_entering", 25, "left", "discovery",
                impact=_loss_impact(decision, config, contribution),
                reason_codes=_loss_reason_codes("relevance", decision, persona, config))
        else:
            add("viewed_service", 18, "inside", "discovery")
            if config.get("online_booking"):
                add("booked", 36, "booking", "booking")
            if buys:
                add("reception", 50, "inside", "reception")
                add("waited", 62, "waiting", "waiting")
                add("service_started", 76, "in_service", "service")
                add("chose_payment", 94, "buying", "payment")
                add("purchased", 103, "purchased", "payment",
                    impact=_purchase_impact(decision, config, contribution),
                    reason_codes=["service_delivered", "payment_fit"])
                add("follow_up", 118, "using_service", "follow_up")
                if _is_repeat(decision, persona, activity):
                    add("returned_later", 134, "returned", "repeat")
                    add("repeat_customer", 148, "repeat", "repeat",
                        impact=_purchase_impact(decision, config, contribution),
                        reason_codes=["repeat_pattern", "positive_follow_up"])
            else:
                if category == "waiting":
                    add("waited", 50, "waiting", "waiting")
                    add("left_due_to_waiting", 68, "left", "waiting",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("waiting", decision, persona, config))
                elif category == "payment":
                    add("checked_payment_options", 50, "comparing", "payment")
                    add("left_due_to_payment", 66, "left", "payment",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("payment", decision, persona, config))
                elif category == "trust":
                    add("checked_trust", 45, "comparing", "booking")
                    add("lost_trust", 62, "cancelled", "booking",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("trust", decision, persona, config))
                elif category == "price":
                    add("left_due_to_price", 54, "cancelled", "booking",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes("price", decision, persona, config))
                else:
                    add("cancelled", 58, "cancelled", "booking",
                        impact=_loss_impact(decision, config, contribution),
                        reason_codes=_loss_reason_codes(category, decision, persona, config))
    final_state = events[-1]["newState"] if events else "unexposed"
    final_decision = "accepted" if buys else "abandoned"
    return events, final_state, final_decision

def _is_repeat(decision: dict[str, Any], persona: Persona, activity: str) -> bool:
    role = str(persona.market_role)
    return any(word in role for word in ("متكرر", "معتاد", "وفي", "متابع"))

def _persona_view(
    decision: dict[str, Any],
    persona: Persona,
    config: dict[str, Any],
    result: dict[str, Any],
    activity: str,
    index: int,
    final_state: str,
    final_decision: str,
) -> dict[str, Any]:
    payment = decision.get("payment") or _preferred_payment(persona, list(config.get("payment_methods") or []))
    offer = decision.get("selected_offer") or {}
    revenue = float(offer.get("price", config.get("price", 0)) or 0)
    if activity == "ecommerce" and not config.get("free_delivery"):
        revenue += float(config.get("delivery_price", 0) or 0)
    margin = max(0.0, float(result.get("contribution_per_order_dzd", 0) or 0))
    category = "accepted" if decision.get("buys") else _category_from_decision(decision, persona, config, activity)

    # Build factor-based decision explanation
    decision_pack = _build_structured_decision(decision, persona, config, result, activity, category, index)

    return {
        "id": decision.get("persona_id"),
        "name": decision.get("name"),
        "gender": decision.get("gender"),
        "age": decision.get("age"),
        "age_group": _age_group(int(decision.get("age", 30))),
        "wilaya": decision.get("wilaya"),
        "segment": decision.get("archetype"),
        "market_role": decision.get("market_role"),
        "language": decision.get("language"),
        "monthly_income_estimate": decision.get("monthly_income_estimate"),
        "income_band": _income_band(float(decision.get("monthly_income_estimate", 0) or 0)),
        "monthly_discretionary_budget": persona.monthly_discretionary_budget,
        "purchasing_power": _purchasing_power(persona.monthly_discretionary_budget),
        "price_sensitivity": round(persona.price_sensitivity * 100, 1),
        "trust_sensitivity": round(persona.trust_need * 100, 1),
        "convenience_need": round(persona.convenience_need * 100, 1),
        "experience_need": round(persona.experience_need * 100, 1),
        "digital_affinity": round(persona.digital_affinity * 100, 1),
        "cod_preference": round(persona.cod_preference * 100, 1),
        "preferred_payment": payment,
        "transportation": _transportation(persona, config, index),
        "preferred_channel": decision.get("preferred_channel"),
        "buying_habit": decision.get("buying_habit"),
        "primary_motivation": decision.get("primary_motivation"),
        "initial_objection": decision.get("initial_objection"),
        "target_segment": decision.get("target_segment"),
        "selected_offer": offer,
        "evaluated_factors": decision.get("evaluated_factors") or {},
        "probability": decision.get("probability"),
        "buys": bool(decision.get("buys")),
        "final_decision": final_decision,
        "decision_confidence": decision_pack["structured_decision"]["confidence"],
        "reaction_label": decision.get("reaction_label"),
        "reason_code": decision.get("reason_code"),
        "decision_reason": decision_pack["structured_decision"]["main_reason"],
        "would_change_my_mind": decision_pack["structured_decision"]["what_would_change"],
        "purchases_first_month": decision.get("purchases_first_month"),
        "price_answers": decision.get("price_answers") or {},
        "payment": payment if decision.get("buys") else None,
        "objections": decision.get("objections") or [],
        "current_state": final_state,
        "current_state_ar": translate_state(final_state),
        "customer_type": "عائد" if _is_repeat(decision, persona, activity) else "جديد",
        "outcome": "accepted" if decision.get("buys") else "abandoned",
        "loss_category": category,
        "structured_decision": decision_pack["structured_decision"],
        "decision_factors": decision_pack["decision_factors"],
        "platform_analysis": decision_pack["platform_analysis"],
        "persona_quote": decision_pack["persona_quote"],
        "expected_financial_impact": {
            "revenue_dzd": round(revenue) if decision.get("buys") else 0,
            "margin_dzd": round(margin) if decision.get("buys") else 0,
            "lost_revenue_dzd": 0 if decision.get("buys") else round(revenue),
            "lost_margin_dzd": 0 if decision.get("buys") else round(margin),
        },
    }

def _select_representatives(personas: list[dict[str, Any]], limit: int = DEFAULT_VISIBLE) -> list[int]:
    """Pick a deterministic, behaviorally diverse set for the scene."""
    if not personas:
        return []
    chosen: list[int] = []
    seen: set[int] = set()

    def take(item: dict[str, Any] | None) -> None:
        if item and item["id"] not in seen and len(chosen) < limit:
            seen.add(item["id"])
            chosen.append(item["id"])

    by_id = {item["id"]: item for item in personas}
    cells: dict[tuple[str, bool], list[dict[str, Any]]] = defaultdict(list)
    for item in personas:
        cells[(str(item.get("segment")), bool(item.get("buys")))].append(item)
    for key in sorted(cells, key=lambda row: (row[0], row[1])):
        take(cells[key][0])

    for field in ("preferred_payment", "loss_category", "customer_type", "wilaya", "age_group", "income_band"):
        seen_values: set[str] = set()
        for item in personas:
            value = str(item.get(field))
            if value in seen_values:
                continue
            seen_values.add(value)
            take(item)

    ordered = sorted(personas, key=lambda item: (float(item.get("probability", 0)), item["id"]))
    take(ordered[0])
    take(ordered[-1])

    if len(chosen) < limit:
        remaining = [item for item in ordered if item["id"] not in seen]
        step = max(1, len(remaining) // max(1, limit - len(chosen)))
        for item in remaining[::step]:
            take(item)
            if len(chosen) >= limit:
                break
    if len(chosen) < limit:
        for item in ordered:
            take(item)
            if len(chosen) >= limit:
                break
    return chosen

def _aggregate_metrics(
    personas: list[dict[str, Any]],
    events: list[dict[str, Any]],
    config: dict[str, Any],
    result: dict[str, Any],
    activity: str,
) -> dict[str, Any]:
    total = len(personas)
    buyer_count = sum(1 for item in personas if item["buys"])
    repeat_count = sum(1 for item in personas if item["buys"] and item["customer_type"] == "عائد")
    visitors = len({
        event["personaId"] for event in events
        if event["type"] in {"entered", "entered_product_page", "viewed_service"}
    })
    abandoned = len({
        event["personaId"] for event in events
        if event["newState"] in {"left", "abandoned", "cancelled", "parking_left"}
    })
    losses = {key: 0 for key in LOSS_LABELS}
    loss_counts = {key: 0 for key in LOSS_LABELS}
    for item in personas:
        if item["buys"]:
            continue
        category = item.get("loss_category") or "relevance"
        if category not in losses:
            category = "relevance"
        loss_counts[category] += 1
        losses[category] += int(item["expected_financial_impact"]["lost_revenue_dzd"])

    waiting_default = 8.0 if activity == "cafe" else 15.0 if activity == "restaurant" else 0.0
    waiting = float(config.get("waiting_minutes", waiting_default) or 0)
    if not waiting and activity == "service":
        waiting = float(config.get("response_minutes", 30) or 30)

    trust = None
    for dimension in result.get("study_dimensions", []):
        if dimension.get("key") == "trust":
            trust = dimension.get("score")
            break
    if trust is None:
        trust = float(config.get("trust_score", 60) or 60)

    # Financial Consistency Verification (Section 14 & 15):
    # expectedRevenue = expectedOrders * averageOrderValue
    expected_orders = int(result.get("expected_monthly_orders", 0) or 0)
    return_rate = float(config.get("return_rate", 0) or 0) if activity == "ecommerce" else 0.0
    delivery_revenue = 0.0 if activity != "ecommerce" or config.get("free_delivery") else float(config.get("delivery_price", 0) or 0)
    base_price = float(config.get("price", 0) or 0)
    average_order_value = round(base_price + delivery_revenue)

    # Exactly consistent formula
    if expected_orders > 0:
        expected_revenue = round(expected_orders * (1 - return_rate) * average_order_value)
    else:
        expected_revenue = round(float(result.get("monthly_revenue_dzd", 0) or 0))

    direct_unit_cost = float(config.get("unit_cost", 0) or 0)
    direct_delivery_cost = float(config.get("delivery_cost", 0) or 0) if activity == "ecommerce" else 0.0
    direct_cost = round(direct_unit_cost + direct_delivery_cost)

    payment_mix = result.get("payment_mix") or {}
    cod_share = float(payment_mix.get("الدفع عند الاستلام", 0) or 0) / 100

    contribution_margin = round(float(result.get("contribution_per_order_dzd", 0) or (average_order_value - direct_cost)))

    return {
        "behavioral": {
            "exposed_personas": total,
            "visitors": visitors,
            "entry_rate_pct": round(visitors / max(1, total) * 100, 1),
            "purchase_conversion_pct": round(buyer_count / max(1, total) * 100, 1),
            "abandonment_rate_pct": round(abandoned / max(1, visitors or total) * 100, 1),
            "average_waiting_minutes": round(waiting, 1),
            "trust_level_pct": round(float(trust), 1),
            "repeat_purchase_intention_pct": round(repeat_count / max(1, buyer_count) * 100, 1),
            "loss_counts": loss_counts,
            "losses_dzd": losses,
        },
        "financial": {
            "expected_orders": expected_orders,
            "expected_revenue_dzd": expected_revenue,
            "average_order_value_dzd": average_order_value,
            "direct_cost_dzd": direct_cost,
            "contribution_margin_dzd": contribution_margin,
            "break_even_volume": result.get("break_even_orders"),
            "liquidity_pressure_dzd": round(
                float(config.get("monthly_fixed_costs", 0) or 0) + expected_orders * direct_cost
            ),
            "cash_on_delivery_exposure_dzd": round(expected_revenue * cod_share),
            "rejection_refund_risk_dzd": round(expected_revenue * return_rate),
        },
        "definitions": METRIC_DEFINITIONS,
        "live": {
            "simulation_duration_seconds": 180,
            "clock_start": "09:00",
            "occupancy_capacity": int(config.get("seating_capacity") or (34 if activity == "cafe" else 46 if activity == "restaurant" else 24)),
        },
        "loss_labels": LOSS_LABELS,
        "state_translations": STATE_TRANSLATIONS,
    }

def _filter_vocabulary(personas: list[dict[str, Any]]) -> dict[str, list[str]]:
    def values(field: str) -> list[str]:
        return sorted({str(item.get(field)) for item in personas if item.get(field) not in (None, "")})
    return {
        "segment": values("segment"),
        "wilaya": values("wilaya"),
        "age_group": values("age_group"),
        "income_band": values("income_band"),
        "decision": ["accepted", "abandoned"],
        "payment_method": values("preferred_payment"),
        "customer_type": ["جديد", "عائد"],
        "outcome": ["accepted", "abandoned"],
        "loss_category": [key for key in LOSS_LABELS],
    }

def build_live_market(
    project: dict[str, Any],
    run: dict[str, Any],
    *,
    seed: str | None = None,
    runs: list[dict[str, Any]] | None = None,
    demo: bool = False,
) -> dict[str, Any]:
    config = deepcopy(run.get("config_json") or {})
    result = deepcopy(run.get("result_json") or {})
    activity = str(config.get("activity_key") or activity_key(project.get("activity_type", "متجر إلكتروني")))
    project_seed = seed or project.get("id") or "fintwin-project"
    decisions = result.get("personas") or result.get("persona_sample") or []
    traits = generate_personas(project_seed, len(decisions) or 100, config.get("wilayas"), config)
    trait_by_id = {persona.id: persona for persona in traits}
    personas: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        pid = decision.get("persona_id", index + 1)
        persona = trait_by_id.get(pid)
        if persona is None:
            persona = generate_personas(project_seed, int(pid), config.get("wilayas"), config)[-1]
        events, final_state, final_decision = _timeline_for_decision(decision, persona, config, result, activity, index)
        view = _persona_view(decision, persona, config, result, activity, index, final_state, final_decision)
        view["timeline_event_ids"] = [event["id"] for event in events]
        personas.append(view)
        all_events.extend(events)

    all_events.sort(key=lambda event: (float(event["timestamp"]), int(event["personaId"]), event["id"]))
    representatives = _select_representatives(personas)
    rep_set = set(representatives)
    for item in personas:
        item["representative"] = item["id"] in rep_set
    for event in all_events:
        event["representative"] = event["personaId"] in rep_set

    metrics = _aggregate_metrics(personas, all_events, config, result, activity)
    environment = _environment(activity, config, result)
    return {
        "dataset_version": DATASET_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "seed": project_seed,
        "generated_for": {
            "project_id": project.get("id"),
            "run_id": run.get("id"),
            "scenario_name": run.get("scenario_name"),
            "activity": activity,
            "demo": demo,
        },
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "activity_type": project.get("activity_type"),
            "description": config.get("description") or project.get("activity_type"),
        },
        "run": {
            "id": run.get("id"),
            "scenario_name": run.get("scenario_name") or "Baseline",
            "parent_run_id": run.get("parent_run_id"),
            "created_at": run.get("created_at"),
            "provider": run.get("provider"),
            "model": run.get("model"),
            "config": config,
            "result_summary": {
                "purchase_intent_pct": result.get("purchase_intent_pct"),
                "expected_monthly_orders": metrics["financial"]["expected_orders"],
                "monthly_revenue_dzd": metrics["financial"]["expected_revenue_dzd"],
                "monthly_profit_dzd": result.get("monthly_profit_dzd"),
                "contribution_per_order_dzd": metrics["financial"]["contribution_margin_dzd"],
                "break_even_orders": result.get("break_even_orders"),
            },
        },
        "runs": [
            {
                "id": item.get("id"),
                "scenario_name": item.get("scenario_name"),
                "parent_run_id": item.get("parent_run_id"),
                "created_at": item.get("created_at"),
            }
            for item in (runs or [])
        ],
        "environment": environment,
        "personas": personas,
        "events": all_events,
        "representatives": representatives,
        "max_visible_personas": MAX_VISIBLE,
        "filters": _filter_vocabulary(personas),
        "metrics": metrics,
        "state_translations": STATE_TRANSLATIONS,
        "disclaimer": "نتائج السوق الحي محاكاة تقديرية مبنية على قرارات اللوحة الحالية، وليست ضماناً تجارياً. أكد القرارات المهمة باختبار ميداني صغير.",
    }

def compare_live_markets(baseline: dict[str, Any], scenario: dict[str, Any], changes: list[str] | None = None) -> dict[str, Any]:
    def metric_diff(section: str) -> dict[str, dict[str, float]]:
        left = baseline.get("metrics", {}).get(section, {})
        right = scenario.get("metrics", {}).get(section, {})
        res: dict[str, dict[str, float]] = {}
        for key in sorted(set(left) | set(right)):
            if isinstance(left.get(key), (int, float)) and isinstance(right.get(key), (int, float)):
                res[key] = {
                    "baseline": left[key],
                    "scenario": right[key],
                    "delta": round(float(right[key]) - float(left[key]), 2),
                }
        return res

    baseline_people = {item["id"]: item for item in baseline.get("personas", [])}
    scenario_people = {item["id"]: item for item in scenario.get("personas", [])}
    changed = []
    for pid in sorted(set(baseline_people) & set(scenario_people)):
        before = baseline_people[pid]
        after = scenario_people[pid]
        delta = float(after.get("probability", 0) or 0) - float(before.get("probability", 0) or 0)
        decision_changed = bool(before.get("buys")) != bool(after.get("buys"))
        if decision_changed or abs(delta) >= 0.08:
            changed.append({
                "personaId": pid,
                "name": after.get("name"),
                "segment": after.get("segment"),
                "wilaya": after.get("wilaya"),
                "baselineDecision": before.get("final_decision"),
                "scenarioDecision": after.get("final_decision"),
                "baselineProbability": before.get("probability"),
                "scenarioProbability": after.get("probability"),
                "delta": round(delta, 4),
                "decisionChanged": decision_changed,
                "why": after.get("decision_reason"),
                "mainObjection": (after.get("objections") or [None])[0],
            })
    changed.sort(key=lambda item: (not item["decisionChanged"], -abs(item["delta"])))
    return {
        "changes": changes or [],
        "metrics": {
            "behavioral": metric_diff("behavioral"),
            "financial": metric_diff("financial"),
        },
        "persona_changes": changed[:30],
        "changed_persona_count": len(changed),
        "flow_change": {
            "baseline_events": len(baseline.get("events", [])),
            "scenario_events": len(scenario.get("events", [])),
        },
        "disclaimer": "الفروقات محاكاة تقديرية، وليست نتيجة مضمونة.",
    }

def answer_persona(persona: dict[str, Any], question: str, config: dict[str, Any]) -> dict[str, Any]:
    """Answer from the persona's existing profile and structured decision without inventing new data.
    Strictly observes the payment rule: never mentions payment if cash was available and used."""
    q = (question or "").strip()
    lowered = q.lower()
    buys = bool(persona.get("buys"))
    struct = persona.get("structured_decision") or {}
    main_reason = struct.get("main_reason") or persona.get("decision_reason") or "قراراتي مبنية على العرض والظروف المتاحة."
    would_change = struct.get("what_would_change") or persona.get("would_change_my_mind") or "عروض أسعار أوضح"
    platform_analysis = persona.get("platform_analysis") or ""
    persona_quote = persona.get("persona_quote") or ""
    offer = persona.get("selected_offer") or {}
    price_val = float(offer.get("price", config.get("price", 0)) or 0)
    price = persona.get("price_answers") or {}
    factors = persona.get("evaluated_factors") or {}
    payment = persona.get("payment") or persona.get("preferred_payment") or "كاش"
    objection = (persona.get("objections") or [persona.get("initial_objection") or "العرض ما أقنعنيش كفاية"])[0]

    ground = {
        "persona_id": persona.get("id"),
        "decision": persona.get("final_decision"),
        "probability": persona.get("probability"),
        "selected_offer": offer.get("name"),
        "selected_price_dzd": price_val,
        "main_objection": objection,
        "main_reason": main_reason,
        "would_change": would_change,
    }

    if "لماذا لم تشتر" in q or "علاش ما شريتش" in q or "why didn't" in lowered or "علاش ما" in q:
        if buys:
            answer = f"أنا قبلت الشراء في هاد المحاكاة باحتمال {round(float(persona.get('probability', 0)) * 100)}%. {persona_quote}"
        else:
            answer = f"{persona_quote} السبب الأساسي: {main_reason} والاعتراض اللي خلاني نحبس: «{objection}»."
    elif "السعر" in q or "سعر" in q or "price" in lowered:
        answer = (
            f"بالنسبة لـ«{offer.get('name', 'الطلب')}» بسعر {price_val:,.0f} دج، "
            f"السعر المقبول عندي حوالي {float(price.get('bargain', 0) or 0):,.0f} دج، "
            f"وحساسيتي للسعر {persona.get('price_sensitivity')}%. "
            f"{'السعر جا مناسب لميزانيتي اليومية.' if buys else 'السعر جاني مرتفع على ميزانيتي وما يشجعش.'}"
        )
    elif "الثقة" in q or "ثق" in q or "trust" in lowered:
        if buys:
            answer = f"الثقة عندي مقبولة وجربت الشراء، لكن ديما نحب نشوف إثباتات أو تقييمات واضحة للاستمرارية."
        else:
            answer = f"حساسيتي للثقة {persona.get('trust_sensitivity')}%. {persona_quote} الحاجة اللي تطمني: {would_change}."
    elif "تعود" in q or "ترجع" in q or "return" in lowered:
        if buys:
            answer = f"نعم نرجع إذا بقات نفس جودة الخدمة والأجواء مريحة. {struct.get('reservation', '')}"
        else:
            answer = f"ما نرجعش بالعرض الحالي؛ نرجع فقط إذا تحقّق: {would_change}."
    elif "ماذا يجب" in q or "شنو" in q or "نغيّر" in q or "change" in lowered or "يبدّل" in q:
        answer = f"الحاجة اللي تقدر تبدّل قراري هي: {would_change}. والاعتراض اللي لازم يتعالج: «{objection}»."
    elif "الدفع" in q or "payment" in lowered or "بريدي" in q or "بطاقة" in lowered:
        methods_str = "، ".join(config.get("payment_methods") or ["كاش"])
        if persona.get("loss_category") == "payment":
            answer = f"تفضيل الدفع عندي هو {payment}، وحالياً القنوات المتوفرة: {methods_str}. هاد الشي كان سبب تراجعي."
        else:
            answer = f"وسيلة الدفع المتوفرة والمقبولة ناسبتني ({payment})، وما كانش عندي أي مشكل في طريقة الدفع."
    else:
        answer = f"{persona_quote} ({struct.get('main_driver', 'ملاءمة العرض')} كان دافعاً مهماً، وتحفظي الأساسي: {struct.get('main_friction', 'لا يوجد')})."

    return {
        "answer": answer,
        "grounding": ground,
        "source": "existing_persona_profile_and_simulation_result",
        "provider": "deterministic_grounded_responder",
    }

def demo_catalog() -> dict[str, dict[str, Any]]:
    """Curated demo cases used by the existing showcase cards."""
    return {
        "demo-street": {
            "name": "Northline Streetwear",
            "activity_label": "متجر إلكتروني",
            "activity_key": "ecommerce",
            "seed": "demo:northline-streetwear",
            "config": {
                "price": 5200, "unit_cost": 2450, "monthly_fixed_costs": 70000, "monthly_reach": 2600,
                "delivery_price": 650, "delivery_cost": 520, "return_rate": 0.14,
                "trust_score": 58, "experience_score": 66, "convenience_score": 61,
                "response_minutes": 45, "payment_methods": ["الدفع عند الاستلام", "بريدي موب"],
                "free_delivery": False, "social_proof": "some", "return_policy": "informal",
                "wilayas": ["الجزائر", "وهران", "سطيف"],
                "target_customer": "طلبة وشباب 18–30 سنة",
                "description": "علامة ملابس streetwear جزائرية تُباع أونلاين، بصور حقيقية ومقاسات مفصلة، مع COD وBaridiMob وتوصيل لثلاث ولايات.",
                "offer_notes": "مقاسات مفصلة، تبديل خلال 48 ساعة، وتغليف هدايا.",
                "products": [
                    {"name": "Hoodie Oversize", "category": "ملابس", "price_dzd": 5900, "cost_dzd": 2800, "stock": 22},
                    {"name": "T-shirt Heavy", "category": "ملابس", "price_dzd": 3200, "cost_dzd": 1450, "stock": 40},
                    {"name": "Cap Signature", "category": "إكسسوار", "price_dzd": 1900, "cost_dzd": 700, "stock": 15},
                ],
            },
        },
        "demo-cafe": {
            "name": "Noya Work Café",
            "activity_label": "كافيه",
            "activity_key": "cafe",
            "seed": "demo:noya-work-cafe",
            "config": {
                "price": 430, "unit_cost": 145, "monthly_fixed_costs": 240000, "monthly_reach": 1800,
                "trust_score": 72, "experience_score": 78, "convenience_score": 58,
                "wifi": True, "parking": False, "atmosphere": "هادئ للعمل والدراسة",
                "street_type": "وسط المدينة", "waiting_minutes": 17, "seating_capacity": 28,
                "payment_methods": ["كاش", "بريدي موب"], "wilayas": ["سطيف", "الجزائر"],
                "target_customer": "طلبة وموظفون 20–35 سنة",
                "description": "مساحة قهوة وعمل قرب الجامعة، Wi-Fi سريع وطاولات للدراسة، مع خدمة سريعة في وقت الذروة.",
                "products": [
                    {"name": "قهوة سادة", "category": "مشروبات", "price_dzd": 250, "cost_dzd": 70, "stock": 100},
                    {"name": "لاتيه", "category": "مشروبات", "price_dzd": 430, "cost_dzd": 145, "stock": 100},
                    {"name": "بريوش", "category": "مخبوزات", "price_dzd": 300, "cost_dzd": 110, "stock": 32},
                ],
            },
        },
        "demo-local": {
            "name": "Atelier Yasmine",
            "activity_label": "متجر ملابس محلي",
            "activity_key": "retail",
            "seed": "demo:atelier-yasmine",
            "config": {
                "price": 6800, "unit_cost": 3300, "monthly_fixed_costs": 140000, "monthly_reach": 900,
                "trust_score": 69, "experience_score": 73, "convenience_score": 55,
                "fitting_rooms": True, "clear_prices": False, "parking": False, "street_type": "شارع تجاري",
                "payment_methods": ["كاش", "بطاقة"], "wilayas": ["تلمسان", "وهران"],
                "target_customer": "نساء 22–45 سنة",
                "description": "بوتيك ملابس نسائية في شارع تجاري، فيه غرف قياس وتشكيلة موسمية، لكن بعض الأسعار تُطلب من البائعة.",
                "products": [
                    {"name": "فستان صيفي", "category": "ملابس", "price_dzd": 6800, "cost_dzd": 3300, "stock": 8},
                    {"name": "قميص كتان", "category": "ملابس", "price_dzd": 4200, "cost_dzd": 1900, "stock": 14},
                    {"name": "حجاب حرير", "category": "إكسسوار", "price_dzd": 2400, "cost_dzd": 950, "stock": 3},
                ],
            },
        },
        "demo-service": {
            "name": "Fixli Home Services",
            "activity_label": "خدمات / Freelance",
            "activity_key": "service",
            "seed": "demo:fixli-home-services",
            "config": {
                "price": 8500, "unit_cost": 2200, "monthly_fixed_costs": 50000, "monthly_reach": 420,
                "trust_score": 63, "experience_score": 76, "convenience_score": 59,
                "online_booking": True, "response_minutes": 95,
                "payment_methods": ["كاش", "بريدي موب", "تحويل بنكي"], "wilayas": ["البليدة", "الجزائر"],
                "target_customer": "عائلات وأصحاب منازل 27–55 سنة",
                "description": "حجز حرفيين موثوقين للصيانة المنزلية مع سعر واضح قبل الزيارة ومتابعة بعد الخدمة.",
                "products": [
                    {"name": "صيانة كهربائية", "category": "خدمة", "price_dzd": 8500, "cost_dzd": 2200, "stock": 12},
                    {"name": "تركيب سخان", "category": "خدمة", "price_dzd": 12000, "cost_dzd": 3800, "stock": 6},
                    {"name": "تشخيص عاجل", "category": "خدمة", "price_dzd": 4500, "cost_dzd": 900, "stock": 20},
                ],
            },
        },
        "demo-food": {
            "name": "Dar Box Kitchen",
            "activity_label": "مطعم / Fast Food",
            "activity_key": "restaurant",
            "seed": "demo:dar-box-kitchen",
            "config": {
                "price": 1100, "unit_cost": 470, "monthly_fixed_costs": 320000, "monthly_reach": 2200,
                "trust_score": 76, "experience_score": 70, "convenience_score": 64,
                "delivery": True, "waiting_minutes": 27, "hygiene_score": 84,
                "parking": False, "payment_methods": ["كاش", "بريدي موب"], "wilayas": ["قسنطينة", "عنابة"],
                "target_customer": "عائلات وموظفون 25–50 سنة",
                "description": "وجبات جزائرية في boxes مع خدمة غداء وتوصيل، يشتكي بعض الزبائن من الانتظار في وقت الذروة.",
                "products": [
                    {"name": "Box دجاج", "category": "وجبات", "price_dzd": 1100, "cost_dzd": 470, "stock": 60},
                    {"name": "Box عائلي", "category": "وجبات", "price_dzd": 2400, "cost_dzd": 1050, "stock": 24},
                    {"name": "شوربة", "category": "مقبلات", "price_dzd": 350, "cost_dzd": 120, "stock": 30},
                ],
            },
        },
        "demo-box": {
            "name": "Dzair Book Box",
            "activity_label": "متجر إلكتروني",
            "activity_key": "ecommerce",
            "seed": "demo:dzair-book-box",
            "config": {
                "price": 3900, "unit_cost": 1750, "monthly_fixed_costs": 90000,
                "monthly_reach": 1300, "delivery_price": 500, "delivery_cost": 460,
                "return_rate": 0.08, "trust_score": 66, "experience_score": 68,
                "convenience_score": 64, "response_minutes": 35,
                "payment_methods": ["الدفع عند الاستلام", "بريدي موب"],
                "wilayas": ["الجزائر", "قسنطينة", "وهران"],
                "target_customer": "قراء وطلبة وأولياء يحبون الكتب",
                "description": "اشتراك شهري في صندوق كتب ومنتجات ثقافية، مع اختيار الموضوع والتوصيل للولايات.",
                "products": [
                    {"name": "صندوق الروايات", "category": "اشتراك", "price_dzd": 3900, "cost_dzd": 1750, "stock": 40},
                    {"name": "صندوق الأطفال", "category": "اشتراك", "price_dzd": 4200, "cost_dzd": 1900, "stock": 32},
                ],
            },
        },
    }

def demo_project_and_run(demo_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from .simulator import simulate

    case = demo_catalog()[demo_id]
    config = deepcopy(case["config"])
    config["activity_key"] = case["activity_key"]
    config["activity_label"] = case["activity_label"]
    config["scenario_name"] = "Baseline"
    config["catalog_reference_price"] = config.get("price")
    result = simulate(config, case["seed"])
    project = {
        "id": demo_id,
        "name": case["name"],
        "activity_type": case["activity_label"],
        "base_config": config,
    }
    run = {
        "id": f"{project['id']}-baseline",
        "project_id": project["id"],
        "scenario_name": "Baseline",
        "parent_run_id": None,
        "config_json": config,
        "result_json": result,
        "provider": "curated",
        "model": "deterministic-demo",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    return project, run, case

def run_demo_scenario(demo_id: str, message: str) -> tuple[dict[str, Any], dict[str, Any], list[str], dict[str, Any]]:
    from .scenario import parse_rule_based
    from .simulator import compare_results, simulate

    project, baseline_run, case = demo_project_and_run(demo_id)
    config, changes = parse_rule_based(message, baseline_run["config_json"])
    if not changes:
        raise ValueError("ما فهمتش التغيير. مثال: زيد السعر 20% أو أضف الدفع بالبطاقة أو وفر موقف سيارات.")
    config["scenario_name"] = message.strip()[:80]
    result = simulate(config, case["seed"])
    comparison = compare_results(baseline_run["result_json"], result)
    run = {
        "id": f"{project['id']}-scenario-{hashlib.sha1(message.encode('utf-8')).hexdigest()[:10]}",
        "project_id": project["id"],
        "scenario_name": config["scenario_name"],
        "parent_run_id": baseline_run["id"],
        "config_json": config,
        "result_json": result,
        "provider": "curated",
        "model": "deterministic-scenario",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    return project, run, changes, comparison
