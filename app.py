from __future__ import annotations

import os
import json
import re
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.catalog import ACTIVITIES, PAYMENT_METHODS, PROVIDER_MODELS, WILAYAS
from src.config import ROOT, load_settings
from src.db import Database
from src.live_market import (
    answer_persona,
    build_live_market,
    compare_live_markets,
    demo_catalog,
    demo_project_and_run,
    run_demo_scenario,
)
from src.llm import LLMGateway
from src.service import FinTwinService


load_dotenv(ROOT / ".env")
settings = load_settings()
database = Database(settings.database_path)
gateway = LLMGateway(settings, database)
service = FinTwinService(database, gateway)

app = FastAPI(title="Fintwin", version="2.0.0")
app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class SessionInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=180)


class ProjectInput(BaseModel):
    user_id: str
    name: str = Field(default="مشروع جديد", max_length=120)
    activity_label: str
    config: dict[str, Any] = Field(default_factory=dict)


class BriefInput(BaseModel):
    text: str = Field(min_length=20, max_length=12000)


class ScenarioInput(BaseModel):
    run_id: str
    message: str = Field(min_length=2, max_length=800)


class LiveScenarioInput(ScenarioInput):
    """A what-if request from the Live Market. The baseline run is never mutated."""


class PersonaChatInput(BaseModel):
    run_id: str
    persona_id: int
    question: str = Field(min_length=2, max_length=800)


class DemoChatInput(BaseModel):
    persona_id: int
    question: str = Field(min_length=2, max_length=800)
    scenario_message: str | None = Field(default=None, max_length=800)


class AdminInput(BaseModel):
    password: str


class ModelInput(AdminInput):
    provider: str
    model: str


def api_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def public_run(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": run["id"], "scenario_name": run["scenario_name"],
        "parent_run_id": run["parent_run_id"], "config": run["config_json"],
        "result": run["result_json"], "provider": run["provider"],
        "model": run["model"], "created_at": run["created_at"],
    }


def require_admin(password: str) -> None:
    if not settings.admin_configured:
        raise HTTPException(status_code=503, detail="ضبط ADMIN_PASSWORD في Secrets أولاً.")
    if password != settings.admin_password:
        raise HTTPException(status_code=401, detail="كلمة سر الإدارة غير صحيحة.")


def live_market_for_run(project_id: str, run_id: str | None = None) -> dict[str, Any]:
    project = database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="المشروع غير موجود.")
    runs = database.list_runs(project_id)
    if run_id:
        run = database.get_run(run_id)
        if not run or run["project_id"] != project_id:
            raise HTTPException(status_code=404, detail="التشغيل المحفوظ غير موجود لهذا المشروع.")
    else:
        run = runs[0] if runs else None
    if not run:
        raise HTTPException(status_code=404, detail="ماكانش تشغيل محفوظ. شغّل المشروع أولاً.")
    return build_live_market(project, run, runs=runs)


def demo_live_market(demo_id: str) -> dict[str, Any]:
    cases = demo_catalog()
    if demo_id not in cases:
        raise HTTPException(status_code=404, detail="حالة العرض غير معروفة.")
    project, run, case = demo_project_and_run(demo_id)
    return build_live_market(project, run, seed=case["seed"], runs=[run], demo=True)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/projects/{project_id}/live-market")
def live_market_page(project_id: str) -> FileResponse:
    """SPA route: the browser uses the project id to load the saved run."""
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/demo/{demo_id}/live-market")
def demo_live_market_page(demo_id: str) -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/capabilities")
def capabilities() -> dict[str, Any]:
    provider, model = service.model_config()
    return {
        "simulation": "deterministic",
        "llm_provider": provider,
        "llm_model": model,
        "llm_key_present": settings.deepseek_configured if provider == "deepseek" else settings.huggingface_configured,
        "auth": "local_demo",
        "database": "sqlite",
        "market_data": "documented_context_and_model_assumptions_not_live_prices",
    }


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    return {
        "activities": [
            {"label": label, "key": data["key"], "icon": data["icon"], "defaults": data["defaults"]}
            for label, data in ACTIVITIES.items()
        ],
        "wilayas": WILAYAS, "payment_methods": PAYMENT_METHODS, "providers": PROVIDER_MODELS,
    }


@app.post("/api/session")
def create_session(payload: SessionInput) -> dict[str, Any]:
    try:
        user_id, session_id = database.upsert_user(payload.name, payload.email)
        return {"user_id": user_id, "session_id": session_id, "projects": database.list_projects(user_id)}
    except Exception as exc:
        raise api_error(exc) from exc


@app.get("/api/users/{user_id}/projects")
def list_projects(user_id: str) -> list[dict[str, Any]]:
    return database.list_projects(user_id)


@app.post("/api/projects")
def create_project(payload: ProjectInput) -> dict[str, Any]:
    if payload.activity_label not in ACTIVITIES:
        raise HTTPException(status_code=400, detail="نوع النشاط غير معروف.")
    config = dict(payload.config)
    if payload.activity_label == "مشروع آخر":
        custom_activity = str(config.get("custom_activity", "")).strip()[:80]
        if not custom_activity:
            raise HTTPException(status_code=400, detail="اكتب اسم النشاط الجديد.")
        config["custom_activity"] = custom_activity
    raw_products = config.get("products") or []
    if not isinstance(raw_products, list) or any(not isinstance(item, dict) for item in raw_products):
        raise HTTPException(status_code=400, detail="قائمة المنتجات غير صالحة.")
    products = [item for item in raw_products if str(item.get("name", "")).strip()]
    config["products"] = products
    try:
        prices = [float(item["price_dzd"]) for item in products]
        costs = [float(item["cost_dzd"]) for item in products if item.get("cost_dzd") not in (None, "")]
        if any(price <= 0 for price in prices) or any(cost < 0 for cost in costs):
            raise ValueError
        for field in ("price", "unit_cost", "monthly_fixed_costs", "monthly_reach", "delivery_price", "delivery_cost"):
            if config.get(field) not in (None, "") and float(config[field]) < 0:
                raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="راجع الأسعار والتكاليف: المنتج يحتاج سعراً موجباً، ولا تقبل القيم السالبة.") from exc
    if prices and not config.get("price"):
        config["price"] = round(sum(prices) / len(prices), 2)
    if costs and not config.get("unit_cost"):
        config["unit_cost"] = round(sum(costs) / len(costs), 2)
    try:
        project_id, run_id, final_config, result = service.create_and_run(
            payload.user_id, payload.name, payload.activity_label, config
        )
        return {"project_id": project_id, "run_id": run_id, "config": final_config,
                "result": result, "project": database.get_project(project_id)}
    except Exception as exc:
        raise api_error(exc) from exc


@app.post("/api/brief/parse")
def parse_brief(payload: BriefInput) -> dict[str, Any]:
    """Turn an unstructured founder brief into editable project assumptions."""
    text = payload.text.strip()
    lowered = text.lower()
    label = "مشروع آخر"
    online_words = ("أونلاين", "اونلاين", "online", "e-commerce", "ecommerce", "متجر إلكتروني", "متجر الكتروني", "توصيل للولايات")
    if any(word in lowered for word in online_words):
        label = "متجر إلكتروني"
    for candidate, words in {
        "كافيه": ("كافيه", "قهوة", "coffee", "café"),
        "مطعم / Fast Food": ("مطعم", "ماكلة", "وجبات", "restaurant", "fast food"),
        "متجر ملابس محلي": ("ملابس", "boutique", "vêtement", "قميص", "هودي"),
        "خدمات / Freelance": ("خدمة", "استشارة", "تصميم", "freelance", "agence"),
    }.items():
        if label == "مشروع آخر" and any(word in lowered for word in words):
            label = candidate
            break
    fallback: dict[str, Any] = {
        "project_name": re.split(r"[.،!؟\n]", text, maxsplit=1)[0].strip()[:55] or "مشروع جديد",
        "activity_label": label,
        "config": {"description": text, "source_mode": "quick_brief"},
        "extraction_mode": "rules",
    }
    if label == "مشروع آخر":
        fallback["config"]["custom_activity"] = (
            "نادي رياضي" if "نادي" in lowered and any(word in lowered for word in ("رياض", "لياقة", "fitness"))
            else "منصة تعليمية" if any(word in lowered for word in ("تعليم", "تكوين", "دروس"))
            else re.split(r"[.،!؟\n]", text, maxsplit=1)[0].strip()[:40]
        )
    if any(word in lowered for word in ("نسائي", "نساء", "بنات", "women", "femme")):
        fallback["config"]["target_customer"] = "نساء"
    elif any(word in lowered for word in ("رجالي", "رجال", "hommes", "men")):
        fallback["config"]["target_customer"] = "رجال"
    age_range = re.search(r"(?:من\s*)?(\d{2})\s*(?:إلى|الى|حتى|[-–])\s*(\d{2})\s*سنة", lowered)
    if age_range and int(age_range.group(1)) < int(age_range.group(2)):
        audience = fallback["config"].get("target_customer", "الجمهور")
        fallback["config"]["target_customer"] = f"{audience} {age_range.group(1)}–{age_range.group(2)} سنة"
    detected_wilayas = [wilaya for wilaya in WILAYAS if wilaya.lower() in lowered]
    if detected_wilayas:
        fallback["config"]["wilayas"] = detected_wilayas
    detected_payments = []
    for method, words in {
        "كاش": ("كاش", "cash", "نقد"),
        "الدفع عند الاستلام": ("عند الاستلام", "cod"),
        "بريدي موب": ("بريدي موب", "baridimob"),
        "بطاقة": ("بطاقة", "card", "carte"),
        "تحويل بنكي": ("تحويل بنكي", "virement"),
    }.items():
        if any(re.search(rf"(?<!\w)(?:و)?{re.escape(word)}(?!\w)", lowered) for word in words):
            detected_payments.append(method)
    if detected_payments:
        fallback["config"]["payment_methods"] = detected_payments
    amounts = [float(value.replace(" ", "")) for value in re.findall(r"(\d[\d ]{1,8})\s*(?:دج|da|dzd)", lowered)]
    if amounts:
        fallback["config"]["price"] = amounts[0]
    provider, model = service.model_config()
    provider_ready = settings.deepseek_configured if provider == "deepseek" else settings.huggingface_configured
    if not provider_ready:
        return fallback
    allowed_labels = list(ACTIVITIES)
    prompt = (
        "Extract an Algerian business brief into JSON only. Do not invent missing facts; use null. "
        f"activity_label must be one of {allowed_labels}. Schema: "
        "{project_name, activity_label, config:{description,custom_activity,target_customer,stage,wilayas,price,unit_cost,"
        "monthly_fixed_costs,monthly_reach,delivery_price,delivery_cost,payment_methods,products:[{name,category,price_dzd,cost_dzd,stock}]}}. "
        f"Brief: {text}"
    )
    try:
        result = gateway.complete(
            [{"role": "system", "content": "Return valid JSON only."}, {"role": "user", "content": prompt}],
            provider, model, max_tokens=900, temperature=0, json_mode=True,
        )
        parsed = json.loads(result.text)
        parsed["extraction_mode"] = "llm"
        return parsed
    except Exception:
        return fallback


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> dict[str, Any]:
    project = database.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="المشروع غير موجود.")
    return {"project": project, "runs": [public_run(run) for run in database.list_runs(project_id)]}


@app.get("/api/projects/{project_id}/live-market")
def project_live_market(project_id: str, run_id: str | None = None) -> dict[str, Any]:
    return live_market_for_run(project_id, run_id)


@app.post("/api/projects/{project_id}/live-market/scenario")
def project_live_market_scenario(project_id: str, payload: LiveScenarioInput) -> dict[str, Any]:
    project = database.get_project(project_id)
    baseline = database.get_run(payload.run_id)
    if not project:
        raise HTTPException(status_code=404, detail="المشروع غير موجود.")
    if not baseline or baseline["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="الجلسة الأساسية غير موجودة لهذا المشروع.")
    try:
        run_id, config, result, comparison, changes, explanation = service.run_what_if(
            project_id, payload.run_id, payload.message
        )
        live = live_market_for_run(project_id, run_id)
        baseline_live = build_live_market(project, baseline, runs=database.list_runs(project_id))
        return {
            "run_id": run_id,
            "config": config,
            "result": result,
            "comparison": comparison,
            "changes": changes,
            "explanation": explanation,
            "baseline_preserved": True,
            "live_market": live,
            "before_after": compare_live_markets(baseline_live, live, changes),
        }
    except Exception as exc:
        raise api_error(exc) from exc


@app.post("/api/projects/{project_id}/live-market/chat")
def project_live_market_chat(project_id: str, payload: PersonaChatInput) -> dict[str, Any]:
    live = live_market_for_run(project_id, payload.run_id)
    persona = next((item for item in live["personas"] if int(item["id"]) == payload.persona_id), None)
    if not persona:
        raise HTTPException(status_code=404, detail="الشخصية غير موجودة في هذا التشغيل.")
    return answer_persona(persona, payload.question, live["run"]["config"])


@app.get("/api/demo/{demo_id}")
def demo_detail_api(demo_id: str) -> dict[str, Any]:
    cases = demo_catalog()
    if demo_id not in cases:
        raise HTTPException(status_code=404, detail="حالة العرض غير معروفة.")
    project, run, case = demo_project_and_run(demo_id)
    return {
        "demo": True,
        "project": project,
        "runs": [public_run(run)],
    }


@app.get("/api/demo/{demo_id}/live-market")
def demo_live_market_api(demo_id: str) -> dict[str, Any]:
    return demo_live_market(demo_id)


@app.post("/api/demo/{demo_id}/live-market/scenario")
def demo_live_market_scenario(demo_id: str, payload: LiveScenarioInput) -> dict[str, Any]:
    try:
        project, run, changes, comparison = run_demo_scenario(demo_id, payload.message)
        cases = demo_catalog()
        live = build_live_market(project, run, seed=cases[demo_id]["seed"], runs=[run], demo=True)
        baseline = demo_live_market(demo_id)
        return {
            "run_id": run["id"],
            "scenario_run": public_run(run),
            "baseline_run": public_run(demo_project_and_run(demo_id)[1]),
            "project_detail": project,
            "changes": changes,
            "comparison": comparison,
            "explanation": f"تم إنشاء سيناريو عرضي: {', '.join(changes)}. النتائج تقديرية.",
            "baseline_preserved": True,
            "saved": False,
            "live_market": live,
            "before_after": compare_live_markets(baseline, live, changes),
        }
    except Exception as exc:
        raise api_error(exc) from exc


@app.post("/api/demo/{demo_id}/live-market/chat")
def demo_live_market_chat(demo_id: str, payload: DemoChatInput) -> dict[str, Any]:
    cases = demo_catalog()
    if demo_id not in cases:
        raise HTTPException(status_code=404, detail="حالة العرض غير معروفة.")
    if payload.scenario_message and payload.scenario_message.strip() not in {"", "Baseline"}:
        project, run, _, _ = run_demo_scenario(demo_id, payload.scenario_message)
    else:
        project, run, case = demo_project_and_run(demo_id)
    live = build_live_market(project, run, seed=cases[demo_id]["seed"], runs=[run], demo=True)
    persona = next((item for item in live["personas"] if int(item["id"]) == payload.persona_id), None)
    if not persona:
        raise HTTPException(status_code=404, detail="الشخصية غير موجودة في هذا التشغيل.")
    return answer_persona(persona, payload.question, live["run"]["config"])


@app.post("/api/projects/{project_id}/scenarios")
def run_scenario(project_id: str, payload: ScenarioInput) -> dict[str, Any]:
    try:
        run_id, config, result, comparison, changes, explanation = service.run_what_if(
            project_id, payload.run_id, payload.message
        )
        return {"run_id": run_id, "config": config, "result": result,
                "comparison": comparison, "changes": changes, "explanation": explanation}
    except Exception as exc:
        raise api_error(exc) from exc


@app.post("/api/admin")
def admin_dashboard(payload: AdminInput) -> dict[str, Any]:
    require_admin(payload.password)
    provider, model = service.model_config()
    return {"stats": database.admin_stats(), "provider": provider, "model": model,
            "providers": PROVIDER_MODELS, "deepseek_ready": settings.deepseek_configured,
            "huggingface_ready": settings.huggingface_configured}


@app.post("/api/admin/model")
def save_model(payload: ModelInput) -> dict[str, Any]:
    require_admin(payload.password)
    if payload.provider not in {"deepseek", "huggingface"}:
        raise HTTPException(status_code=400, detail="مزود غير معروف.")
    allowed = PROVIDER_MODELS["DeepSeek الرسمي" if payload.provider == "deepseek" else "Hugging Face Inference"]
    if payload.model not in allowed:
        raise HTTPException(status_code=400, detail="الموديل غير موجود في القائمة المسموحة.")
    database.set_setting("llm_provider", payload.provider)
    database.set_setting("llm_model", payload.model)
    return {"ok": True, "provider": payload.provider, "model": payload.model}


@app.post("/api/admin/model/test")
def test_model(payload: ModelInput) -> dict[str, Any]:
    require_admin(payload.password)
    if payload.provider not in {"deepseek", "huggingface"}:
        raise HTTPException(status_code=400, detail="مزود غير معروف.")
    allowed = PROVIDER_MODELS["DeepSeek الرسمي" if payload.provider == "deepseek" else "Hugging Face Inference"]
    if payload.model not in allowed:
        raise HTTPException(status_code=400, detail="الموديل غير موجود في القائمة المسموحة.")
    result = gateway.test_connection(payload.provider, payload.model)
    return {"ok": True, "latency_ms": result.latency_ms,
            "tokens": result.input_tokens + result.output_tokens, "cost_usd": result.estimated_cost_usd}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
