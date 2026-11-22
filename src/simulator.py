from __future__ import annotations

import math
import re
import random
from collections import Counter, defaultdict
from copy import deepcopy
from statistics import mean, median
from typing import Any

from .personas import Persona, generate_personas

MODEL_VERSION = "2026-11-22-context-2"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-20, min(20, value))))


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return (max(0, (centre - margin) / denominator), min(1, (centre + margin) / denominator))


def _payment_fit(persona: Persona, methods: list[str]) -> tuple[float, str]:
    methods = methods or ["كاش"]
    scores: dict[str, float] = {}
    for method in methods:
        if method == "الدفع عند الاستلام":
            score = persona.cod_preference
        elif method in {"بريدي موب", "بطاقة", "تحويل بنكي"}:
            score = persona.digital_affinity
        else:
            score = 0.72
        scores[method] = score
    chosen = max(scores, key=scores.get)
    return clamp(scores[chosen]), chosen


def _activity_adjustments(activity: str, config: dict[str, Any], persona: Persona) -> tuple[float, list[str]]:
    delta = 0.0
    objections: list[str] = []
    if activity == "ecommerce":
        delivery_price = float(config.get("delivery_price", 0))
        reference_price = float(config.get("delivery_reference_price", config.get("price", 1)))
        if not config.get("free_delivery") and delivery_price > reference_price * 0.12:
            # Keep the reference price fixed across a what-if so raising the
            # product price cannot erase an existing delivery objection.
            delta -= 0.09 * persona.price_sensitivity
            objections.append("سعر التوصيل مرتفع")
        if float(config.get("response_minutes", 30)) > 60:
            delta -= 0.07
            objections.append("الرد بطيء")
        if config.get("return_policy") in {"none", "informal"} and persona.trust_need > .55:
            delta -= 0.07 * persona.trust_need
            objections.append("الاسترجاع غير مطمئن")
        if config.get("social_proof") == "strong":
            delta += 0.06 * persona.trust_need
    elif activity == "retail":
        if not config.get("fitting_rooms", False):
            delta -= 0.06 * persona.experience_need
            objections.append("ماكانش غرفة قياس")
        if not config.get("clear_prices", False):
            delta -= 0.10
            objections.append("الأسعار غير واضحة")
        if config.get("street_type") == "شارع تجاري":
            delta += 0.04
        if config.get("visual_quality") == "strong":
            delta += 0.04 * persona.experience_need
    elif activity == "cafe":
        if config.get("wifi"):
            delta += 0.05 * persona.experience_need
        if config.get("parking"):
            delta += 0.04 * persona.convenience_need
        if config.get("atmosphere") in {"شبابي وعصري", "هادئ للعمل والدراسة"}:
            delta += 0.05 * persona.experience_need
        if float(config.get("waiting_minutes", 8)) > 15:
            delta -= 0.06 * persona.convenience_need
            objections.append("الخدمة بطيئة")
    elif activity == "restaurant":
        hygiene = float(config.get("hygiene_score", 70)) / 100
        delta += (hygiene - 0.65) * 0.18
        waiting = float(config.get("waiting_minutes", 15))
        if waiting > 25:
            delta -= 0.09 * persona.convenience_need
            objections.append("وقت الانتظار طويل")
        if config.get("delivery"):
            delta += 0.04 * persona.convenience_need
    elif activity == "service":
        if config.get("online_booking"):
            delta += 0.05 * persona.convenience_need
        if float(config.get("response_minutes", 30)) > 120:
            delta -= 0.08
            objections.append("التواصل بطيء")
        if config.get("social_proof") == "strong":
            delta += 0.08 * persona.trust_need
    return delta, objections


def _target_fit(persona: Persona, target: str) -> tuple[float, str]:
    text = target.lower().strip()
    if not text:
        return 0.68, "جمهور غير محدد بدقة"
    checks: list[bool] = []
    if any(word in text for word in ("نساء", "نسائي", "بنات", "femme", "women")):
        checks.append(persona.gender == "أنثى")
    if any(word in text for word in ("رجال", "رجالي", "homme", "men")):
        checks.append(persona.gender == "ذكر")
    if any(word in text for word in ("طلبة", "طالب", "étudiant", "student")):
        checks.append(persona.age <= 29)
    if any(word in text for word in ("شباب", "jeune", "young")):
        checks.append(persona.age <= 38)
    if any(word in text for word in ("موظف", "موظفين", "عامل", "profession", "employee")):
        checks.append(22 <= persona.age <= 56)
    if any(word in text for word in ("عائلات", "عائلة", "parents", "famille")):
        checks.append(persona.age >= 27)
    age_range = re.search(r"(\d{2})\s*[-–]\s*(\d{2})", text)
    if age_range:
        checks.append(int(age_range.group(1)) <= persona.age <= int(age_range.group(2)))
    if not checks:
        return 0.76, "ضمن الجمهور الواسع"
    matched = sum(checks) / len(checks)
    return (0.91, "ضمن الجمهور الأساسي") if matched >= .75 else ((0.64, "قريب من الجمهور") if matched >= .5 else (0.36, "جمهور ثانوي"))


def _project_evidence(config: dict[str, Any]) -> float:
    score = 0.0
    score += .23 if len(str(config.get("description", "")).strip()) >= 70 else .08
    score += .15 if str(config.get("target_customer", "")).strip() else 0
    score += .17 if config.get("products") else .05
    score += .13 if float(config.get("price", 0) or 0) > 0 else 0
    score += .12 if config.get("payment_methods") else 0
    score += .10 if str(config.get("offer_notes", "")).strip() else 0
    score += .10 if str(config.get("experience_notes", "")).strip() else 0
    return clamp(score)


def _select_offer(config: dict[str, Any], persona: Persona) -> dict[str, Any]:
    products = [p for p in (config.get("products") or []) if float(p.get("price_dzd", 0) or 0) > 0]
    scenario_price = max(1.0, float(config.get("price", 1) or 1))
    if not products:
        return {"name": "العرض الرئيسي", "category": config.get("activity_label", "عرض"), "price": scenario_price}
    reference_price = float(config.get("catalog_reference_price") or scenario_price)
    price_multiplier = scenario_price / max(1.0, reference_price)
    preferred_spend = persona.monthly_discretionary_budget * (.12 + (1 - persona.price_sensitivity) * .26)
    ranked = []
    for offset, product in enumerate(products):
        adjusted = float(product.get("price_dzd", 0)) * price_multiplier
        # Select the product against its original offer price so a scenario
        # compares the same item for each persona before and after repricing.
        distance = abs(float(product.get("price_dzd", 0)) - preferred_spend) / max(1000, preferred_spend)
        variety = ((persona.id * 17 + offset * 31) % 19) / 100
        ranked.append((distance + variety, product, adjusted))
    _, selected, adjusted_price = min(ranked, key=lambda row: row[0])
    return {"name": selected.get("name") or "عرض بدون اسم", "category": selected.get("category") or "—", "price": adjusted_price}


FACTOR_LABELS = {
    "affordability": "السعر النهائي",
    "trust": "الثقة والإثباتات",
    "experience": "التجربة المتوقعة",
    "convenience": "السهولة والوقت",
    "payment": "طريقة الدفع",
    "relevance": "ملاءمة العرض",
    "evidence": "وضوح المعلومات",
}


def _buyer_voice(persona: Persona, buys: bool, scores: dict[str, float], offer_name: str) -> tuple[str, str, str]:
    weakest = min(scores, key=scores.get)
    strongest = max(scores, key=scores.get)
    weak_label, strong_label = FACTOR_LABELS[weakest], FACTOR_LABELS[strongest]
    if buys:
        reason = f"عرض «{offer_name}» قريب لاحتياجي، وأكثر حاجة شجعتني هي {strong_label}. يبقى عندي تحفظ صغير حول {weak_label}."
        flip = ""
        reaction = "نية قوية" if scores[strongest] >= .82 else "مهتم مع تحقق أخير"
    else:
        reason = f"ما نأكدش الشراء الآن؛ «{offer_name}» ما جاوبنيش كفاية في نقطة {weak_label}، حتى لو {strong_label} باينة مليحة."
        flip_map = {
            "affordability": "سعر نهائي أخف أو قيمة إضافية واضحة",
            "trust": "إثباتات حقيقية وسياسة استرجاع أو ضمان واضحة",
            "experience": "تجربة أو صور وتفاصيل أدق قبل الدفع",
            "convenience": "خدمة أسرع ووصول أو توصيل أسهل",
            "payment": "إضافة وسيلة الدفع اللي نستعملها",
            "relevance": "عرض أقرب لاحتياجي أو لفئتي",
            "evidence": "شرح كامل للسعر والخدمة وما الذي سأحصل عليه",
        }
        flip = flip_map[weakest]
        reaction = "متردد" if scores[weakest] >= .48 else "يرفض حالياً"
    return weakest, reason, flip or "لا يحتاج تغييراً جوهرياً"


def simulate(config: dict[str, Any], project_seed: str, count: int = 128) -> dict[str, Any]:
    cfg = deepcopy(config)
    activity = str(cfg.get("activity_key", "ecommerce"))
    # The panel composition is project-specific but stable across scenarios.
    # This makes the actors relevant to the activity while preserving a fair
    # before/after comparison when one decision changes.
    personas = generate_personas(project_seed, count, cfg.get("wilayas"), cfg)
    # Common random numbers: the same persona gets the same draw in every
    # scenario. This makes before/after differences attributable to the change,
    # instead of noise from regenerating the panel.
    rng = random.Random(f"{project_seed}:decisions")
    decisions: list[dict[str, Any]] = []
    objections_counter: Counter[str] = Counter()
    payment_counter: Counter[str] = Counter()
    segment_stats: dict[str, list[float]] = defaultdict(list)
    role_stats: dict[str, list[float]] = defaultdict(list)
    dimension_stats: dict[str, list[float]] = defaultdict(list)
    flip_counter: Counter[str] = Counter()
    price = max(1.0, float(cfg.get("price", 1)))
    customer_delivery_price = (
        0.0
        if activity != "ecommerce" or cfg.get("free_delivery")
        else max(0.0, float(cfg.get("delivery_price", 0)))
    )
    unit_cost = max(0.0, float(cfg.get("unit_cost", 0)))
    trust_score = clamp(float(cfg.get("trust_score", 60)) / 100)
    experience_score = clamp(float(cfg.get("experience_score", 60)) / 100)
    convenience_score = clamp(float(cfg.get("convenience_score", 60)) / 100)
    methods = list(cfg.get("payment_methods") or ["كاش"])
    evidence_fit = _project_evidence(cfg)
    target_text = str(cfg.get("target_customer", ""))

    for persona in personas:
        selected_offer = _select_offer(cfg, persona)
        selected_outlay = float(selected_offer["price"]) + customer_delivery_price
        ratio = selected_outlay / max(1000, persona.monthly_discretionary_budget)
        affordability = clamp(1.05 - ratio * (1.3 + persona.price_sensitivity))
        trust_fit = clamp(1 - max(0, persona.trust_need - trust_score) * 1.15)
        experience_fit = clamp(1 - abs(persona.experience_need - experience_score) * 0.62)
        convenience_fit = clamp(1 - max(0, persona.convenience_need - convenience_score) * 0.88)
        payment_fit, payment = _payment_fit(persona, methods)
        relevance_fit, target_segment = _target_fit(persona, target_text)
        activity_delta, objections = _activity_adjustments(activity, cfg, persona)
        utility = (
            affordability * 0.27
            + trust_fit * 0.18
            + experience_fit * 0.12
            + convenience_fit * 0.12
            + payment_fit * 0.12
            + relevance_fit * 0.13
            + evidence_fit * 0.06
            + activity_delta
        )
        probability = clamp(sigmoid((utility - 0.64) * 5.4), 0.03, 0.96)
        buys = rng.random() < probability
        factor_scores = {
            "affordability": affordability,
            "trust": trust_fit,
            "experience": experience_fit,
            "convenience": convenience_fit,
            "payment": payment_fit,
            "relevance": relevance_fit,
            "evidence": evidence_fit,
        }
        reason_code, decision_reason, would_change = _buyer_voice(persona, buys, factor_scores, selected_offer["name"])
        if not buys:
            if affordability < 0.48:
                objections.append("السعر فوق الميزانية")
            if trust_fit < 0.62:
                objections.append("الثقة غير كافية")
            if payment_fit < 0.52:
                objections.append("طريقة الدفع غير مناسبة")
            if convenience_fit < 0.58:
                objections.append("الخدمة غير مريحة")
            if not objections:
                objections.append("العرض ما أقنعنيش كفاية")
            objections_counter.update(set(objections))
            flip_counter[would_change] += 1
        else:
            payment_counter[payment] += 1
        segment_stats[persona.archetype].append(probability)
        role_stats[persona.market_role].append(probability)
        for factor, factor_score in factor_scores.items():
            dimension_stats[factor].append(factor_score)
        price_reference = max(100.0, selected_outlay)
        price_answers = {
            "too_cheap": round(price_reference * (.48 + persona.trust_need * .12), -1),
            "bargain": round(price_reference * (.72 + (1 - persona.price_sensitivity) * .12), -1),
            "expensive": round(price_reference * (1.08 + (1 - persona.price_sensitivity) * .20), -1),
            "too_expensive": round(price_reference * (1.35 + (1 - persona.price_sensitivity) * .35), -1),
        }
        if buys:
            monthly_frequency = {"cafe": 5, "restaurant": 3, "retail": 1, "ecommerce": 1, "service": 1}.get(activity, 1)
            purchases_first_month = max(1, round(monthly_frequency * probability))
        else:
            purchases_first_month = 0
        decisions.append(
            {
                "persona_id": persona.id,
                "name": persona.name,
                "gender": persona.gender,
                "age": persona.age,
                "wilaya": persona.wilaya,
                "archetype": persona.archetype,
                "language": persona.language,
                "monthly_income_estimate": persona.monthly_income_estimate,
                "market_role": persona.market_role,
                "primary_motivation": persona.primary_motivation,
                "preferred_channel": persona.preferred_channel,
                "buying_habit": persona.buying_habit,
                "initial_objection": persona.initial_objection,
                "target_segment": target_segment,
                "selected_offer": selected_offer,
                "evaluated_factors": {key: round(value * 100, 1) for key, value in factor_scores.items()},
                "probability": round(probability, 4),
                "buys": buys,
                "reaction_label": "نية قوية" if buys and probability >= .70 else ("مهتم" if buys else ("متردد" if probability >= .38 else "يرفض حالياً")),
                "reason_code": reason_code,
                "decision_reason": decision_reason,
                "would_change_my_mind": would_change,
                "purchases_first_month": purchases_first_month,
                "price_answers": price_answers,
                "payment": payment if buys else None,
                "objections": objections if not buys else [],
            }
        )

    buyers = sum(1 for decision in decisions if decision["buys"])
    conversion_probability = mean(decision["probability"] for decision in decisions)
    low, high = wilson_interval(buyers, count)
    monthly_reach = max(0, int(cfg.get("monthly_reach", 0)))
    # Intent is measured among the synthetic panel; only a portion of monthly
    # reach reaches a real purchase moment. Activity-specific funnel factors keep
    # the financial projection separate from the intent score.
    funnel_factor = {
        "ecommerce": 0.06,
        "retail": 0.16,
        "cafe": 0.28,
        "restaurant": 0.24,
        "service": 0.12,
    }.get(activity, 0.10)
    expected_orders = round(monthly_reach * conversion_probability * funnel_factor)
    return_rate = clamp(float(cfg.get("return_rate", 0))) if activity == "ecommerce" else 0.0
    fulfilled_orders = expected_orders * (1 - return_rate)
    delivery_cost = float(cfg.get("delivery_cost", 0)) if activity == "ecommerce" else 0.0
    delivery_revenue = 0.0 if cfg.get("free_delivery") else float(cfg.get("delivery_price", 0))
    payment_fee_rate = float(cfg.get("payment_fee_rate", 0.008))
    digital_share = sum(value for key, value in payment_counter.items() if key in {"بريدي موب", "بطاقة", "تحويل بنكي"}) / max(1, buyers)
    avg_payment_fee = price * payment_fee_rate * digital_share
    contribution = price + delivery_revenue - unit_cost - delivery_cost - avg_payment_fee
    fixed_costs = max(0.0, float(cfg.get("monthly_fixed_costs", 0)))
    monthly_revenue = fulfilled_orders * (price + delivery_revenue)
    monthly_profit = fulfilled_orders * contribution - fixed_costs
    break_even = math.ceil(fixed_costs / contribution) if contribution > 0 else None
    payment_mix = {
        key: round(value / max(1, buyers) * 100, 1)
        for key, value in payment_counter.most_common()
    }
    segments = [
        {"segment": key, "purchase_intent": round(mean(values) * 100, 1), "count": len(values)}
        for key, values in sorted(segment_stats.items(), key=lambda item: mean(item[1]), reverse=True)
    ]
    market_roles = [
        {"role": key, "purchase_intent": round(mean(values) * 100, 1), "count": len(values)}
        for key, values in sorted(role_stats.items(), key=lambda item: mean(item[1]), reverse=True)
    ]
    study_dimensions = [
        {"key": key, "label": FACTOR_LABELS[key], "score": round(mean(values) * 100, 1)}
        for key, values in sorted(dimension_stats.items(), key=lambda item: mean(item[1]))
    ]
    price_ranges = {
        key: round(median(d["price_answers"][key] for d in decisions), -1)
        for key in ("too_cheap", "bargain", "expensive", "too_expensive")
    }
    recommendations = []
    if contribution <= 0:
        recommendations.append("هامش المساهمة سلبي: راجع السعر، تكلفة السلعة أو التوصيل قبل الإطلاق.")
    elif break_even and break_even > monthly_reach:
        recommendations.append("نقطة التعادل أعلى من الوصول الشهري المتوقع؛ خفّض التكاليف الثابتة أو ارفع الهامش.")
    if trust_score < 0.65:
        recommendations.append("قوّي إشارات الثقة: سياسة استرجاع واضحة، معلومات تواصل واثباتات حقيقية.")
    if conversion_probability < 0.35:
        recommendations.append("اختبر العرض مع عينة حقيقية صغيرة قبل أي مصاريف كبيرة.")
    top_objection = objections_counter.most_common(1)
    if top_objection:
        recommendations.append(f"أكبر اعتراض هو «{top_objection[0][0]}»؛ ابنِ تجربة A/B لمعالجته.")
    return {
        "model_version": MODEL_VERSION,
        "sample_size": count,
        "buyers": buyers,
        "purchase_intent_pct": round(conversion_probability * 100, 1),
        "observed_buy_rate_pct": round(buyers / count * 100, 1),
        "confidence_interval_pct": [round(low * 100, 1), round(high * 100, 1)],
        "expected_monthly_orders": expected_orders,
        "expected_conversion_pct": round(conversion_probability * funnel_factor * 100, 2),
        "fulfilled_orders": round(fulfilled_orders),
        "monthly_revenue_dzd": round(monthly_revenue),
        "monthly_profit_dzd": round(monthly_profit),
        "contribution_per_order_dzd": round(contribution, 2),
        "break_even_orders": break_even,
        "payment_mix": payment_mix,
        "top_objections": [{"label": label, "count": value} for label, value in objections_counter.most_common(6)],
        "segments": segments,
        "market_roles": market_roles,
        "study_dimensions": study_dimensions,
        "what_flips_no": [{"label": label, "count": value} for label, value in flip_counter.most_common(6)],
        "price_range_dzd": price_ranges,
        "panel_blueprint": {
            "activity": activity,
            "target": target_text or "غير محدد — تمت معاملة الملاءمة كفرضية",
            "evidence_score": round(evidence_fit * 100, 1),
            "same_panel_across_scenarios": True,
        },
        "recommendations": recommendations[:5],
        "personas": decisions,
        "persona_sample": decisions[:12],
        "disclaimer": "هذه محاكاة فرضيات وليست توقعاً مضموناً. أكد القرارات المهمة باختبار مع زبائن حقيقيين.",
    }


def compare_results(baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "purchase_intent_pct",
        "expected_monthly_orders",
        "monthly_revenue_dzd",
        "monthly_profit_dzd",
        "contribution_per_order_dzd",
    ]
    return {
        key: {
            "baseline": baseline.get(key),
            "scenario": scenario.get(key),
            "delta": round(float(scenario.get(key) or 0) - float(baseline.get(key) or 0), 2),
        }
        for key in keys
    }

