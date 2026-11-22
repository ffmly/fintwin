from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


PERCENT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
TASHKEEL_PATTERN = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]")


def _normalize_arabic(text: str) -> str:
    """Strip Arabic diacritics so «قوّي» and «قوي» match the same phrase."""
    return TASHKEEL_PATTERN.sub("", text)


def parse_rule_based(message: str, current: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    text = _normalize_arabic(message.strip().lower())
    updated = deepcopy(current)
    updated.setdefault("delivery_reference_price", current.get("delivery_reference_price", current.get("price", 1)))
    changes: list[str] = []
    match = PERCENT_PATTERN.search(text)
    percent = float(match.group(1).replace(",", ".")) / 100 if match else None

    increase_words = ("زيد", "نزيد", "زود", "نزود", "ارفع", "نرفع", "رفع", "زيادة", "augment", "increase", "+")
    decrease_words = ("نقص", "ننقص", "انقص", "خفض", "نخفض", "تخفيض", "خفف", "rédu", "decrease", "-")
    price_words = ("سعر", "السعر", "الأسعار", "ثمن", "اشتراك", "prix", "price", "subscription")
    delivery_words = ("توصيل", "livraison", "delivery")
    mentions_delivery = any(word in text for word in delivery_words)
    delivery_target = any(
        phrase in text for phrase in ("سعر التوصيل", "تكلفة التوصيل", "delivery price", "delivery cost", "frais de livraison")
    ) or (mentions_delivery and not any(word in text for word in price_words))
    if percent is not None and any(word in text for word in price_words) and not delivery_target:
        old_price = float(updated.get("price", 0))
        if any(word in text for word in increase_words):
            updated["price"] = round(old_price * (1 + percent), 2)
            changes.append(f"رفع السعر من {old_price:,.0f} إلى {updated['price']:,.0f} دج")
        elif any(word in text for word in decrease_words):
            updated["price"] = round(old_price * (1 - percent), 2)
            changes.append(f"خفض السعر من {old_price:,.0f} إلى {updated['price']:,.0f} دج")

    if percent is not None and delivery_target:
        if any(word in text for word in ("تكلفة", "cost", "frais")):
            old_cost = float(updated.get("delivery_cost", 0))
            if any(word in text for word in increase_words):
                updated["delivery_cost"] = round(old_cost * (1 + percent), 2)
                changes.append(f"رفع تكلفة التوصيل من {old_cost:,.0f} إلى {updated['delivery_cost']:,.0f} دج")
            elif any(word in text for word in decrease_words):
                updated["delivery_cost"] = round(old_cost * (1 - percent), 2)
                changes.append(f"خفض تكلفة التوصيل من {old_cost:,.0f} إلى {updated['delivery_cost']:,.0f} دج")
        else:
            old_delivery = float(updated.get("delivery_price", 0))
            if any(word in text for word in increase_words):
                updated["delivery_price"] = round(old_delivery * (1 + percent), 2)
                changes.append(f"رفع سعر التوصيل من {old_delivery:,.0f} إلى {updated['delivery_price']:,.0f} دج")
            elif any(word in text for word in decrease_words):
                updated["delivery_price"] = round(old_delivery * (1 - percent), 2)
                changes.append(f"خفض سعر التوصيل من {old_delivery:,.0f} إلى {updated['delivery_price']:,.0f} دج")

    if any(phrase in text for phrase in ("توصيل مجاني", "livraison gratuite", "free delivery")):
        updated["free_delivery"] = True
        updated["delivery_price"] = 0.0
        changes.append("تفعيل التوصيل المجاني")
    if any(phrase in text for phrase in ("زيد بريدي موب", "أضف بريدي موب", "ajoute baridimob", "add baridimob")):
        methods = list(updated.get("payment_methods", []))
        if "بريدي موب" not in methods:
            methods.append("بريدي موب")
        updated["payment_methods"] = methods
        changes.append("إضافة بريدي موب")
    add_words = ("زيد", "نزيد", "زود", "نزود", "نضيف", "أضف", "اضف", "فعّل", "فعل", "وفر", "وفّر", "add", "ajoute", "active")
    if any(word in text for word in ("بطاقة", "carte", "card")) and any(word in text for word in add_words):
        methods = list(updated.get("payment_methods", []))
        if "بطاقة" not in methods:
            methods.append("بطاقة")
        updated["payment_methods"] = methods
        changes.append("إضافة الدفع بالبطاقة")
    if any(word in text for word in ("ويفي", "wifi", "wi-fi")) and any(word in text for word in add_words):
        updated["wifi"] = True
        changes.append("إضافة Wi-Fi")
    if any(word in text for word in ("باركينغ", "parking", "موقف", "مواقف", "park")) and any(word in text for word in add_words):
        updated["parking"] = True
        changes.append("إضافة موقف سيارات")
    if any(phrase in text for phrase in ("غرفة قياس", "غرف القياس", "fitting room")) and any(word in text for word in ("زيد", "نضيف", "أضف", "add", "ajoute")):
        updated["fitting_rooms"] = True
        changes.append("إضافة غرف القياس")
    if any(phrase in text for phrase in ("وضح الأسعار", "الأسعار واضحة", "أسعار واضحة", "clear prices")):
        updated["clear_prices"] = True
        changes.append("إظهار الأسعار بوضوح")
    if any(phrase in text for phrase in ("حجز اونلاين", "حجز أونلاين", "حجز مسبق", "online booking")):
        updated["online_booking"] = True
        changes.append("تفعيل الحجز المسبق")
    if any(phrase in text for phrase in ("فعّل التوصيل", "فعل التوصيل", "add delivery", "active la livraison")):
        updated["delivery"] = True
        changes.append("تفعيل خدمة التوصيل")
    if any(phrase in text for phrase in ("قوي الثقة", "زيد الثقة", "إثباتات ثقة", "social proof")):
        old = float(updated.get("trust_score", 60))
        updated["trust_score"] = min(100, old + (percent * 100 if percent is not None else 15))
        updated["social_proof"] = "strong"
        changes.append(f"تقوية إشارات الثقة إلى {updated['trust_score']:.0f}/100")
    minutes = re.search(r"(\d+)\s*(?:دقيقة|دق|minutes?|min)", text)
    if minutes and any(word in text for word in ("رد", "response", "réponse")):
        updated["response_minutes"] = float(minutes.group(1))
        changes.append(f"ضبط زمن الرد على {minutes.group(1)} دقيقة")
    if minutes and any(word in text for word in ("انتظار", "waiting", "attente")):
        updated["waiting_minutes"] = float(minutes.group(1))
        changes.append(f"ضبط وقت الانتظار على {minutes.group(1)} دقيقة")
    return updated, changes


def apply_structured_patch(current: dict[str, Any], patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    allowed = {
        "price", "unit_cost", "monthly_fixed_costs", "monthly_reach", "delivery_price",
        "delivery_cost", "return_rate", "trust_score", "experience_score", "convenience_score",
        "response_minutes", "payment_methods", "free_delivery", "fitting_rooms", "clear_prices",
        "parking", "wifi", "waiting_minutes", "hygiene_score", "online_booking", "delivery",
    }
    updated = deepcopy(current)
    changes: list[str] = []
    for key, value in patch.items():
        if key not in allowed:
            continue
        previous = updated.get(key)
        if previous != value:
            updated[key] = value
            changes.append(f"{key}: {previous} → {value}")
    return updated, changes

