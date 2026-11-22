from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass

from .catalog import WILAYAS


@dataclass(frozen=True)
class Persona:
    id: int
    name: str
    gender: str
    age: int
    wilaya: str
    setting: str
    monthly_discretionary_budget: float
    price_sensitivity: float
    trust_need: float
    convenience_need: float
    experience_need: float
    digital_affinity: float
    cod_preference: float
    archetype: str
    language: str
    market_role: str
    primary_motivation: str
    preferred_channel: str
    buying_habit: str
    initial_objection: str
    monthly_income_estimate: float
    weight: float

    def to_dict(self) -> dict:
        return asdict(self)


ARCHETYPES = [
    ("صياد العروض", 0.23),
    ("عملي ومستعجل", 0.20),
    ("حذر ويبحث عن الثقة", 0.22),
    ("يحب التجربة والجودة", 0.19),
    ("رقمي ومرن", 0.16),
]

ACTIVITY_ARCHETYPES = {
    "ecommerce": [("رقمي ومرن", .27), ("حذر ويبحث عن الثقة", .25), ("صياد العروض", .22), ("عملي ومستعجل", .18), ("يحب التجربة والجودة", .08)],
    "retail": [("يحب التجربة والجودة", .27), ("صياد العروض", .24), ("عملي ومستعجل", .19), ("حذر ويبحث عن الثقة", .18), ("رقمي ومرن", .12)],
    "cafe": [("يحب التجربة والجودة", .34), ("عملي ومستعجل", .23), ("رقمي ومرن", .18), ("صياد العروض", .15), ("حذر ويبحث عن الثقة", .10)],
    "restaurant": [("يحب التجربة والجودة", .31), ("حذر ويبحث عن الثقة", .24), ("عملي ومستعجل", .21), ("صياد العروض", .17), ("رقمي ومرن", .07)],
    "service": [("حذر ويبحث عن الثقة", .31), ("عملي ومستعجل", .27), ("رقمي ومرن", .18), ("صياد العروض", .14), ("يحب التجربة والجودة", .10)],
}

ROLES = {
    "ecommerce": [("مشتري جديد", .36), ("متابع للعلامة", .22), ("زبون متكرر", .20), ("مقارن أسعار", .22)],
    "retail": [("زائر عابر", .28), ("زبون الحي", .31), ("مشتري مناسبة", .22), ("زبون وفي", .19)],
    "cafe": [("طالب/عامل متنقل", .29), ("زبون جلسة", .26), ("زبون سريع", .25), ("زبون معتاد", .20)],
    "restaurant": [("طلب عائلي", .28), ("زبون غداء", .25), ("مستكشف جديد", .27), ("زبون متكرر", .20)],
    "service": [("عميل لأول مرة", .38), ("عميل مستعجل", .24), ("عميل بإحالة", .22), ("عميل متكرر", .16)],
}

MOTIVATIONS = {
    "ecommerce": ["توفر المنتج", "سعر نهائي واضح", "توصيل موثوق", "منتج يطابق الصور"],
    "retail": ["التجربة قبل الشراء", "سعر واضح", "قرب المحل", "تنوع الاختيار"],
    "cafe": ["جلسة مريحة", "خدمة سريعة", "مكان للعمل", "قيمة مقابل السعر"],
    "restaurant": ["الطعم والجودة", "النظافة", "وقت انتظار قصير", "كمية مشبعة"],
    "service": ["نتيجة موثوقة", "موعد قريب", "سعر مفهوم", "متابعة بعد الخدمة"],
}

CHANNELS = {
    "ecommerce": [("Instagram", .34), ("TikTok", .20), ("Facebook", .25), ("إحالة", .21)],
    "retail": [("مرور الشارع", .38), ("Instagram", .25), ("إحالة", .25), ("Google Maps", .12)],
    "cafe": [("Google Maps", .22), ("Instagram", .28), ("إحالة", .31), ("مرور الشارع", .19)],
    "restaurant": [("إحالة", .34), ("Facebook", .22), ("Google Maps", .23), ("Instagram", .21)],
    "service": [("إحالة", .41), ("Facebook", .20), ("Google Search", .24), ("Instagram", .15)],
}

NAMES = {
    "أنثى": ["أمينة", "سارة", "ريم", "إيناس", "ليلى", "مريم", "ياسمين", "نسرين", "سلمى", "نهال", "آية", "رانيا", "مليكة", "سيرين", "حنان", "دنيا", "وفاء", "لينا", "سمية", "إيمان", "نور", "خديجة", "أسماء", "سهام", "فريال"],
    "ذكر": ["أمين", "يوسف", "إلياس", "مراد", "أنيس", "حمزة", "بلال", "كريم", "رياض", "سفيان", "وليد", "مهدي", "ياسين", "سمير", "عادل", "أيوب", "إسحاق", "هشام", "رشيد", "نبيل", "طارق", "زين", "عمر", "محمد", "علي"],
}

HABITS = {
    "ecommerce": ["يقارن السعر والتوصيل قبل تأكيد الطلب", "يشوف التعليقات والصور الحقيقية", "يحفظ المنتج ويرجع له بعد يومين", "يطلب غالباً بعد استلام الراتب", "يفضّل صفحة ترد بسرعة"],
    "retail": ["يدخل للمحل بعد ما يشوف الواجهة", "يقيس أكثر من خيار قبل الشراء", "يسأل على السعر قبل التجربة", "يرجع للمحل اللي يعرف مقاساته", "يشتري غالباً مع شخص آخر"],
    "cafe": ["يبدل المكان حسب الازدحام", "يجلس للعمل أكثر من ساعة", "يطلب بسرعة وهو في الطريق", "يختار المكان مع المجموعة", "يرجع لنفس المكان إذا حفظوا طلبه"],
    "restaurant": ["يقارن الكمية بالسعر", "يسأل معارفه قبل التجربة", "يطلب في وقت الغداء", "يهتم بسرعة الخدمة", "يعيد الطلب إذا الجودة ثابتة"],
    "service": ["يطلب عرض سعر قبل الموعد", "يعتمد على الإحالة", "يتواصل مع أكثر من مقدم خدمة", "يؤجل القرار إذا النتيجة غامضة", "يدفع أكثر مقابل ضمان واضح"],
}

OBJECTIONS = {
    "ecommerce": ["يمكن المنتج ما يجيش كيما الصورة", "التوصيل يرفع السعر النهائي", "ما نعرفش إذا الاسترجاع ساهل", "الدفع المسبق ما يريحنيش", "يمكن نلقى أرخص في صفحة أخرى"],
    "retail": ["ما نحبش نسقسي على السعر", "يمكن ما نلقاش المقاس", "المحل بعيد أو صعب نوقف قدامه", "الجودة ما تبانش من الواجهة", "نحتاج وقت نقارن"],
    "cafe": ["السعر عالي على قهوة عادية", "يمكن المكان مزعج أو عامر", "الـWi-Fi يقدر يكون ضعيف", "الباركينغ صعيب", "الخدمة يمكن تطول"],
    "restaurant": ["النظافة أهم من الصور", "يمكن الكمية ما تشبعش", "وقت الانتظار يفسد التجربة", "التوصيل يقدر يوصل بارد", "السعر ما يبررش الجودة"],
    "service": ["ما نعرفش النتيجة قبل ما ندفع", "التسعير يقدر يتبدل بعد البداية", "ماكانش ضمان واضح", "صعيب نلقى موعد قريب", "نحتاج نشوف أعمال أو آراء حقيقية"],
}

OTHER_PROFILES = {
    "fitness": {
        "roles": [("عضو محتمل", .40), ("مشترك جديد", .27), ("مقارن اشتراكات", .23), ("مشترك سابق", .10)],
        "motivations": ["برنامج يناسب هدفي", "مواعيد تدريب ملائمة", "مدربة مؤهلة", "مكان مريح وآمن"],
        "habits": ["يزور النادي قبل الاشتراك", "يقارن الباقات الشهرية", "يسأل عن حصص تجريبية", "يفضل الاشتراك مع صديقة"],
        "objections": ["المواعيد لا تناسب يومي", "أحتاج حصة تجريبية أولاً", "الاشتراك الشهري فوق ميزانيتي", "لا أعرف مستوى المدربة"],
    },
    "education": {
        "roles": [("متعلم جديد", .43), ("ولي أمر", .19), ("مقارن برامج", .23), ("متعلم عائد", .15)],
        "motivations": ["نتيجة تعليمية واضحة", "أستاذ موثوق", "جدول مناسب", "محتوى يطابق المستوى"],
        "habits": ["يطلب البرنامج قبل التسجيل", "يقارن نتائج المتعلمين", "يحضر درساً تجريبياً", "يسأل عن الشهادة والتقييم"],
        "objections": ["لا أعرف مستوى الأستاذ", "النتيجة غير واضحة", "المواعيد غير مناسبة", "السعر مرتفع على مدة البرنامج"],
    },
    "general": {
        "roles": [("عميل لأول مرة", .38), ("مقارن خيارات", .27), ("عميل بإحالة", .20), ("عميل عائد", .15)],
        "motivations": ["فائدة واضحة من العرض", "سعر مفهوم", "تجربة موثوقة", "سهولة الوصول"],
        "habits": ["يسأل عن تفاصيل العرض", "يقارن البدائل قبل القرار", "يبحث عن تجارب سابقة", "يجرب خدمة صغيرة أولاً"],
        "objections": ["القيمة غير واضحة", "التسعير يحتاج تفصيلاً", "لا توجد تجربة سابقة موثوقة", "لا أعرف إن كان العرض يناسبني"],
    },
}


def _weighted_choice(rng: random.Random, pairs: list[tuple[str, float]]) -> str:
    return rng.choices([item for item, _ in pairs], weights=[weight for _, weight in pairs], k=1)[0]


def _seed(project_seed: str) -> int:
    digest = hashlib.sha256(project_seed.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def generate_personas(
    project_seed: str,
    count: int = 100,
    target_wilayas: list[str] | None = None,
    context: dict | None = None,
) -> list[Persona]:
    rng = random.Random(_seed(project_seed))
    context = context or {}
    activity = str(context.get("activity_key", "ecommerce"))
    archetypes = ACTIVITY_ARCHETYPES.get(activity, ARCHETYPES)
    custom_text = " ".join(str(context.get(key) or "") for key in ("custom_activity", "description")).lower()
    other_profile = OTHER_PROFILES[
        "fitness" if any(word in custom_text for word in ("نادي رياضي", "رياضة", "لياقة", "fitness", "gym"))
        else "education" if any(word in custom_text for word in ("تعليم", "تكوين", "دروس", "مدرسة", "course", "academy"))
        else "general"
    ] if activity == "other" else None
    roles = other_profile["roles"] if other_profile else ROLES.get(activity, ROLES["service"])
    motivations = other_profile["motivations"] if other_profile else MOTIVATIONS.get(activity, MOTIVATIONS["service"])
    channels = CHANNELS.get(activity, CHANNELS["service"])
    wilayas = target_wilayas or WILAYAS[:8]
    income_bands = [
        (9000, 0.14), (15000, 0.22), (24000, 0.27), (38000, 0.22), (60000, 0.11), (90000, 0.04)
    ]
    languages = [("دارجة", 0.58), ("دارجة + فرنسية", 0.25), ("عربية", 0.12), ("فرنسية", 0.05)]
    settings = [("حضري", 0.61), ("شبه حضري", 0.27), ("ريفي", 0.12)]
    audience = " ".join(str(context.get(key) or "") for key in ("target_customer", "description")).lower()
    women_only = any(word in audience for word in ("نسائي", "نسائية", "نساء", "بنات", "women", "femme"))
    men_only = any(word in audience for word in ("رجالي", "رجالية", "رجال", "hommes"))
    exclusive_audience = activity == "other" and other_profile is OTHER_PROFILES["fitness"]
    female_share = (1.0 if exclusive_audience else .86) if women_only and not men_only else ((0.0 if exclusive_audience else .14) if men_only and not women_only else .52)
    personas: list[Persona] = []
    for index in range(count):
        gender = "أنثى" if rng.random() < female_share else "ذكر"
        archetype = _weighted_choice(rng, archetypes)
        base_budget = float(_weighted_choice(rng, [(str(value), weight) for value, weight in income_bands]))
        price_sensitivity = rng.betavariate(2.5, 1.9)
        trust_need = rng.betavariate(2.7, 1.8)
        convenience_need = rng.betavariate(2.2, 2.0)
        experience_need = rng.betavariate(2.0, 2.2)
        digital_affinity = rng.betavariate(2.0, 2.1)
        cod_preference = max(0.05, min(0.95, 0.82 - 0.65 * digital_affinity + rng.uniform(-0.12, 0.12)))
        if archetype == "صياد العروض":
            price_sensitivity = min(0.98, price_sensitivity + 0.20)
        elif archetype == "حذر ويبحث عن الثقة":
            trust_need = min(0.98, trust_need + 0.18)
        elif archetype == "يحب التجربة والجودة":
            experience_need = min(0.98, experience_need + 0.18)
        elif archetype == "رقمي ومرن":
            digital_affinity = min(0.98, digital_affinity + 0.22)
            cod_preference = max(0.05, cod_preference - 0.18)
        personas.append(
            Persona(
                id=index + 1,
                name=f"{NAMES[gender][index % len(NAMES[gender])]} {1 + index // len(NAMES[gender])}" if index >= len(NAMES[gender]) else NAMES[gender][index],
                gender=gender,
                age=int(rng.triangular(18, 64, 30)),
                wilaya=rng.choice(wilayas),
                setting=_weighted_choice(rng, settings),
                monthly_discretionary_budget=round(base_budget * rng.uniform(0.78, 1.25), -2),
                price_sensitivity=round(price_sensitivity, 3),
                trust_need=round(trust_need, 3),
                convenience_need=round(convenience_need, 3),
                experience_need=round(experience_need, 3),
                digital_affinity=round(digital_affinity, 3),
                cod_preference=round(cod_preference, 3),
                archetype=archetype,
                language=_weighted_choice(rng, languages),
                market_role=_weighted_choice(rng, roles),
                primary_motivation=rng.choice(motivations),
                preferred_channel=_weighted_choice(rng, channels),
                buying_habit=rng.choice(other_profile["habits"] if other_profile else HABITS.get(activity, HABITS["service"])),
                initial_objection=rng.choice(other_profile["objections"] if other_profile else OBJECTIONS.get(activity, OBJECTIONS["service"])),
                monthly_income_estimate=round(base_budget * rng.uniform(2.4, 4.8), -3),
                weight=1.0 / count,
            )
        )
    return personas

