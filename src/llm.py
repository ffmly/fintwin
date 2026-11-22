from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .db import Database
DEEPSEEK_PEAK_USD_PER_MILLION = {
    "deepseek-flash": {"input": 0.30, "output": 1.20},
    "deepseek-v4-pro": {"input": 1.32, "output": 3.96},
}


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int


class LLMGateway:
    def __init__(self, settings: Settings, database: Database):
        self.settings = settings
        self.database = database

    def _estimate_deepseek_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        prices = DEEPSEEK_PEAK_USD_PER_MILLION.get(model, DEEPSEEK_PEAK_USD_PER_MILLION["deepseek-flash"])
        return round((input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000, 8)

    def complete(
        self,
        messages: list[dict[str, Any]],
        provider: str,
        model: str,
        *,
        max_tokens: int = 700,
        temperature: float = 0.15,
        json_mode: bool = False,
        run_id: str | None = None,
    ) -> LLMResult:
        started = time.perf_counter()
        event = {"run_id": run_id, "provider": provider, "model": model, "status": "error"}
        try:
            if provider == "deepseek":
                raw = self._deepseek(messages, model, max_tokens, temperature, json_mode)
            elif provider == "huggingface":
                raw = self._huggingface(messages, model, max_tokens, temperature, json_mode)
            else:
                raise ValueError(f"Unknown LLM provider: {provider}")
            latency_ms = int((time.perf_counter() - started) * 1000)
            input_tokens = int(raw.get("input_tokens", 0))
            output_tokens = int(raw.get("output_tokens", 0))
            cost = self._estimate_deepseek_cost(model, input_tokens, output_tokens) if provider == "deepseek" else 0.0
            event.update(
                status="ok",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=cost,
                latency_ms=latency_ms,
            )
            self.database.log_llm_event(event)
            return LLMResult(
                text=str(raw["text"]), provider=provider, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                estimated_cost_usd=cost, latency_ms=latency_ms,
            )
        except Exception as exc:
            event.update(latency_ms=int((time.perf_counter() - started) * 1000), error=str(exc)[:500])
            self.database.log_llm_event(event)
            raise

    def _deepseek(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> dict[str, Any]:
        if not self.settings.deepseek_configured:
            raise RuntimeError("DEEPSEEK_API_KEY غير مضبوط في Hugging Face Secrets.")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=120) as client:
            response = client.post(
                "https://api.deepseek.com/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                detail = response.text[:400]
                raise RuntimeError(f"DeepSeek API {response.status_code}: {detail}")
            body = response.json()
        usage = body.get("usage", {})
        return {
            "text": body["choices"][0]["message"].get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

    def _huggingface(
        self,
        messages: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> dict[str, Any]:
        if not self.settings.huggingface_configured:
            raise RuntimeError("HF_TOKEN غير مضبوط في Secrets.")
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        with httpx.Client(timeout=120) as client:
            response = client.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.hf_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Hugging Face API {response.status_code}: {response.text[:400]}")
            body = response.json()
        usage = body.get("usage", {})
        return {
            "text": body["choices"][0]["message"].get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

    def test_connection(self, provider: str, model: str) -> LLMResult:
        return self.complete(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            provider,
            model,
            max_tokens=8,
            temperature=0,
        )

    def parse_scenario(self, message: str, current: dict[str, Any], provider: str, model: str) -> dict[str, Any]:
        allowed = [
            "price", "unit_cost", "monthly_fixed_costs", "monthly_reach", "delivery_price",
            "delivery_cost", "return_rate", "trust_score", "experience_score", "convenience_score",
            "response_minutes", "payment_methods", "free_delivery", "fitting_rooms", "clear_prices",
            "parking", "wifi", "waiting_minutes", "hygiene_score", "online_booking", "delivery",
        ]
        prompt = (
            "You convert Algerian Darija/French/Arabic what-if business requests into a JSON patch. "
            "Return one JSON object only. Preserve DZD units. Use only these keys: "
            f"{allowed}. Current scenario: {json.dumps(current, ensure_ascii=False)}. "
            f"User request: {message}"
        )
        result = self.complete(
            [{"role": "system", "content": "Output valid JSON only."}, {"role": "user", "content": prompt}],
            provider,
            model,
            max_tokens=350,
            temperature=0,
            json_mode=True,
        )
        return json.loads(result.text)

    def explain_comparison(
        self,
        question: str,
        changes: list[str],
        baseline: dict[str, Any],
        scenario: dict[str, Any],
        comparison: dict[str, Any],
        provider: str,
        model: str,
        run_id: str | None = None,
    ) -> str:
        compact = {
            "question": question,
            "changes": changes,
            "baseline": {key: baseline.get(key) for key in comparison},
            "scenario": {key: scenario.get(key) for key in comparison},
            "delta": {key: value["delta"] for key, value in comparison.items()},
            "objections": scenario.get("top_objections", [])[:3],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "أنت محلل FinTech جزائري. جاوب بدارجة جزائرية واضحة ومهنية. "
                    "اشرح النتائج كفرضيات محاكاة، لا تدّعي اليقين، واذكر أثر الربح والسيولة واقترح اختباراً ميدانياً واحداً."
                ),
            },
            {"role": "user", "content": json.dumps(compact, ensure_ascii=False)},
        ]
        return self.complete(messages, provider, model, max_tokens=550, temperature=0.2, run_id=run_id).text

